param(
    [string]$RepoRoot = "",
    [int]$Port = 8088,
    [string]$TaskName = "SmartHomeServer_Permanent"
)

$ErrorActionPreference = "Continue"
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$extraPaths = @(
    "C:\Users\LENOVO\.local\bin",
    "C:\Program Files\GitHub CLI",
    "C:\Program Files\Tailscale"
)
$env:PATH = ($extraPaths -join ";") + ";" + $env:PATH

$logDir = "C:\Users\LENOVO\.smarthome_server\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$wdLog = Join-Path $logDir "watchdog.log"
if ((Test-Path $wdLog) -and ((Get-Item $wdLog).Length -gt 5242880)) {
    Move-Item -Force -Path $wdLog -Destination "$wdLog.1"
}

function Test-PortHealth {
    param([int]$CheckPort, [int]$TimeoutSec = 5)
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:${CheckPort}/api/health" -TimeoutSec $TimeoutSec
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
$runners = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match '-File\s+["'']?[^"'']*run_server_headless\.ps1' -and $_.CommandLine -match "-Port\s+$Port\b"
} | Sort-Object CreationDate)
if ($runners.Count -gt 1) {
    $extras = @($runners | Select-Object -Skip 1)
    foreach ($ex in $extras) {
        Stop-Process -Id $ex.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Add-Content -Path $wdLog -Value "[$ts] Cleanup: stopped $($extras.Count) duplicate runner(s) on port ${Port}." -Encoding UTF8
}

$healthy = Test-PortHealth -CheckPort $Port -TimeoutSec 5
if (-not $healthy) {
    $startingPy = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match 'uvicorn\s+simulator\.server:app' -and $_.CommandLine -match "--port\s+$Port\b" -and $_.CreationDate -gt (Get-Date).AddSeconds(-40)
    })
    if ($startingPy.Count -gt 0) {
        for ($w = 0; $w -lt 15; $w++) {
            Start-Sleep -Seconds 2
            if (Test-PortHealth -CheckPort $Port -TimeoutSec 3) {
                $healthy = $true
                break
            }
        }
    }
}

if (-not $healthy) {
    Add-Content -Path $wdLog -Value "[$ts] ALERT: health check failed on 127.0.0.1:${Port}; recovering headless service..." -Encoding UTF8
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $listeners) {
        if ($conn.OwningProcess) {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
    $startedViaTask = $false
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        try {
            Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
            for ($w = 0; $w -lt 18; $w++) {
                Start-Sleep -Seconds 2
                if (Test-PortHealth -CheckPort $Port -TimeoutSec 3) {
                    $startedViaTask = $true
                    break
                }
            }
        } catch {
            $startedViaTask = $false
        }
    }
    if (-not $startedViaTask) {
        $runner = Join-Path $RepoRoot "scripts\service\run_server_headless.ps1"
        Start-Process -FilePath "conhost.exe" `
            -ArgumentList @("--headless", "powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", "`"$runner`"", "-RepoRoot", "`"$RepoRoot`"", "-Port", "$Port") `
            -WindowStyle Hidden
    }
} else {
    Add-Content -Path $wdLog -Value "[$ts] OK: 127.0.0.1:${Port}/api/health HTTP 200" -Encoding UTF8
}

# Verify Tailscale Funnel stays bound to 8088
try {
    $funnelText = (& tailscale funnel status 2>&1) | Out-String
    if ($funnelText -notmatch "8088") {
        Add-Content -Path $wdLog -Value "[$ts] Re-applying tailscale funnel --bg $Port" -Encoding UTF8
        & tailscale funnel --bg $Port | Out-Null
    }
} catch {
    Add-Content -Path $wdLog -Value "[$ts] Tailscale funnel check warning: $_" -Encoding UTF8
}
