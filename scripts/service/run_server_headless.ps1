param(
    [string]$RepoRoot = "",
    [string]$EnvFile = "C:\Users\LENOVO\.smarthome_server\.env.production",
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8088
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

function Import-EnvProduction {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    foreach ($raw in Get-Content -Path $Path -Encoding UTF8) {
        $line = $raw.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) { continue }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { continue }
        $k = $line.Substring(0, $idx).Trim()
        $v = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
        if ($v -eq "[SENSITIVE]") { continue }
        if (-not [string]::IsNullOrWhiteSpace($k)) {
            [Environment]::SetEnvironmentVariable($k, $v, "Process")
        }
    }
}

Import-EnvProduction -Path $EnvFile

if ([string]::IsNullOrWhiteSpace($env:SMARTHOME_STATE_BACKEND)) {
    [Environment]::SetEnvironmentVariable("SMARTHOME_STATE_BACKEND", "sqlite", "Process")
}
if ([string]::IsNullOrWhiteSpace($env:SMARTHOME_SQLITE_PATH)) {
    [Environment]::SetEnvironmentVariable("SMARTHOME_SQLITE_PATH", "C:\Users\LENOVO\.smarthome_server\data\smarthome.db", "Process")
}
[Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "Process")
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "Process")

$logDir = if ($env:SMARTHOME_LOG_DIR) { $env:SMARTHOME_LOG_DIR } else { "C:\Users\LENOVO\.smarthome_server\logs" }
$dataDir = if ($env:SMARTHOME_DATA_DIR) { $env:SMARTHOME_DATA_DIR } else { "C:\Users\LENOVO\.smarthome_server\data" }
$backupDir = if ($env:SMARTHOME_BACKUP_DIR) { $env:SMARTHOME_BACKUP_DIR } else { "C:\Users\LENOVO\.smarthome_server\backups" }
New-Item -ItemType Directory -Force -Path $logDir, $dataDir, $backupDir | Out-Null

$runnerLog = Join-Path $logDir "runner_lifecycle.log"
$svcLog = Join-Path $logDir "uvicorn_stdout.log"
$svcErrLog = Join-Path $logDir "uvicorn_stderr.log"
$lockPidFile = Join-Path $logDir "runner.pid"

$mutexName = "Local\SmartHomeServerRunner_${Port}"
$createdNew = $false
$runnerMutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$createdNew)
if (-not $createdNew) {
    $tsDup = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
    Add-Content -Path $runnerLog -Value "[$tsDup] Duplicate runner detected for port ${Port} (PID=$PID); exiting cleanly." -Encoding UTF8
    $runnerMutex.Dispose()
    exit 0
}
Set-Content -Path $lockPidFile -Value "$PID" -Encoding UTF8

function Rotate-LogIfLarge {
    param([string]$FilePath, [long]$MaxBytes = 10485760)
    if (Test-Path $FilePath) {
        $len = (Get-Item $FilePath).Length
        if ($len -ge $MaxBytes) {
            for ($i = 4; $i -ge 1; $i--) {
                $older = "$FilePath.$i"
                $newer = "$FilePath.$($i + 1)"
                if (Test-Path $older) { Move-Item -Force -Path $older -Destination $newer }
            }
            Move-Item -Force -Path $FilePath -Destination "$FilePath.1"
        }
    }
}

$preferredPy = "C:\Users\LENOVO\miniconda3\python.exe"
$pythonExe = if (Test-Path $preferredPy) { $preferredPy } else { (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $pythonExe) { $pythonExe = "python" }

Set-Location $RepoRoot

try {
    while ($true) {
        Rotate-LogIfLarge -FilePath $runnerLog
        Rotate-LogIfLarge -FilePath $svcLog
        Rotate-LogIfLarge -FilePath $svcErrLog

        # Free port cleanly if an orphaned python/uvicorn holds it without this loop
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $listeners) {
            if ($conn.OwningProcess -and $conn.OwningProcess -ne $PID) {
                Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }

        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
        Add-Content -Path $runnerLog -Value "[$ts] Starting SmartHome headless uvicorn ($RepoRoot) on ${ListenHost}:${Port}" -Encoding UTF8

        $proc = Start-Process -FilePath $pythonExe `
            -ArgumentList @("-m", "uvicorn", "simulator.server:app", "--host", $ListenHost, "--port", "$Port", "--ws-ping-interval", "20", "--ws-ping-timeout", "20", "--timeout-keep-alive", "65", "--log-level", "info") `
            -WorkingDirectory $RepoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $svcLog `
            -RedirectStandardError $svcErrLog `
            -PassThru

        Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
        $code = $proc.ExitCode
        $tsEnd = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
        Add-Content -Path $runnerLog -Value "[$tsEnd] uvicorn exited with code $code; restarting in 2s..." -Encoding UTF8
        Start-Sleep -Seconds 2
    }
} finally {
    if ($runnerMutex) {
        try { $runnerMutex.ReleaseMutex() } catch {}
        $runnerMutex.Dispose()
    }
}
