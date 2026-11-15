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

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
$healthy = $false
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:${Port}/api/health" -TimeoutSec 5
    if ($resp.StatusCode -eq 200) {
        $healthy = $true
    }
} catch {
    $healthy = $false
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
            Start-Sleep -Seconds 3
            try {
                $r2 = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:${Port}/api/health" -TimeoutSec 4
                if ($r2.StatusCode -eq 200) {
                    $startedViaTask = $true
                }
            } catch {
                $startedViaTask = $false
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
