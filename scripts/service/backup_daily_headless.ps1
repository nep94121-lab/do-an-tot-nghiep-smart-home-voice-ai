param(
    [string]$RepoRoot = "",
    [string]$EnvFile = "C:\Users\LENOVO\.smarthome_server\.env.production"
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

if (Test-Path $EnvFile) {
    foreach ($raw in Get-Content -Path $EnvFile -Encoding UTF8) {
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

$logDir = "C:\Users\LENOVO\.smarthome_server\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$backupLog = Join-Path $logDir "backup.log"

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
$out = & python (Join-Path $RepoRoot "scripts\backup_sqlite.py") 2>&1 | Out-String
Add-Content -Path $backupLog -Value "[$ts] $out" -Encoding UTF8
