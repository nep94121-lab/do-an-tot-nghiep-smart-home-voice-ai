param(
    [string]$RepoRoot = "",
    [int]$Port = 8088,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$runnerScript = Join-Path $RepoRoot "scripts\service\run_server_headless.ps1"
$watchdogScript = Join-Path $RepoRoot "scripts\service\watchdog_headless.ps1"
$backupScript = Join-Path $RepoRoot "scripts\service\backup_daily_headless.ps1"

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

function Register-HeadlessTask {
    param(
        [string]$TaskName,
        [string]$Arguments,
        $PrimaryTriggers,
        $FallbackTriggers,
        $Settings,
        [bool]$AllowSystemBoot = $true
    )
    $action = New-ScheduledTaskAction -Execute "conhost.exe" -Argument $Arguments
    if ($AllowSystemBoot) {
        try {
            $principalSystem = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest
            Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $PrimaryTriggers -Settings $Settings -Principal $principalSystem -Force -ErrorAction Stop | Out-Null
            return "SYSTEM"
        } catch {
        }
    }
    try {
        $principalS4U = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType S4U -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $PrimaryTriggers -Settings $Settings -Principal $principalS4U -Force -ErrorAction Stop | Out-Null
        return "S4U"
    } catch {
        $principalInteractive = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $FallbackTriggers -Settings $Settings -Principal $principalInteractive -Force -ErrorAction Stop | Out-Null
        return "Interactive"
    }
}

$svcArgs = "--headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runnerScript`" -RepoRoot `"$RepoRoot`" -Port $Port"
$svcPrimaryTriggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -AtLogOn -User $currentUser)
)
$svcFallbackTriggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)
)
$svcSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -Hidden

$svcMode = Register-HeadlessTask -TaskName "SmartHomeServer_Permanent" -Arguments $svcArgs -PrimaryTriggers $svcPrimaryTriggers -FallbackTriggers $svcFallbackTriggers -Settings $svcSettings -AllowSystemBoot $false

# Belt-and-suspenders HKCU Run entry so headless service auto-starts cleanly on user logon even without Admin S4U rights
try {
    $hkcuRun = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    if (Test-Path $hkcuRun) {
        Set-ItemProperty -Path $hkcuRun -Name "SmartHomeServer_Permanent" -Value "conhost.exe $svcArgs"
    }
} catch {
}

$wdArgs = "--headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchdogScript`" -RepoRoot `"$RepoRoot`" -Port $Port"
$wdTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 3650)
$wdSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew `
    -Hidden

$wdMode = Register-HeadlessTask -TaskName "SmartHomeServer_Watchdog" -Arguments $wdArgs -PrimaryTriggers $wdTrigger -FallbackTriggers $wdTrigger -Settings $wdSettings -AllowSystemBoot $false

$bkArgs = "--headless powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$backupScript`" -RepoRoot `"$RepoRoot`""
$bkTrigger = New-ScheduledTaskTrigger -Daily -At "03:15"
$bkSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew `
    -Hidden

$bkMode = Register-HeadlessTask -TaskName "SmartHomeServer_DailyBackup" -Arguments $bkArgs -PrimaryTriggers $bkTrigger -FallbackTriggers $bkTrigger -Settings $bkSettings -AllowSystemBoot $false

if ($StartNow) {
    Start-ScheduledTask -TaskName "SmartHomeServer_Permanent"
}

$startupWithoutLogin = ($svcMode -eq "S4U" -or $svcMode -eq "SYSTEM")
$tasks = @(Get-ScheduledTask -TaskName "SmartHomeServer_*" | Select-Object TaskName, @{ Name = 'State'; Expression = { $_.State.ToString() } })
[PSCustomObject]@{
    ok = $true
    startup_without_login = $startupWithoutLogin
    elevation_required_for_boot = (-not $startupWithoutLogin)
    modes = @{
        SmartHomeServer_Permanent = $svcMode
        SmartHomeServer_Watchdog = $wdMode
        SmartHomeServer_DailyBackup = $bkMode
    }
    tasks = $tasks
} | ConvertTo-Json -Depth 4 -Compress
