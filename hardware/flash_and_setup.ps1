<#
.SYNOPSIS
    Turnkey USB firmware flash and runtime Wi-Fi setup for NodeMCU ESP8266 v2 (nodemcuv2).
.DESCRIPTION
    Audits PlatformIO toolchain, checks CP210x/CH340 driver status (read-only),
    enumerates COM ports, compiles firmware/esp8266_smarthome, and (unless -DryRun
    or -CompileOnly is specified) uploads over USB, provisions runtime Wi-Fi config
    over Serial (never printing passwords or API keys), and runs SELF_TEST + WIFI_STATUS.
.PARAMETER Port
    Optional explicit COM port (e.g. COM3). Auto-detected if omitted.
.PARAMETER DryRun
    Audit toolchain, drivers, COM ports, and compile firmware only. Never flashes a board.
.PARAMETER CompileOnly
    Same safety guarantee as -DryRun: compile and audit only, never flashes a board.
.PARAMETER ConfigFile
    Optional path to a git-ignored JSON file (e.g. hardware/wifi_local.json) containing
    ssid, password, server_ip, and optional server_port, mqtt_server, mqtt_port, hardware_api_key.
.PARAMETER Baud
    Serial baud rate for runtime provisioning and self-test. Default: 115200.
.PARAMETER SkipWifiSetup
    Flash firmware and run SELF_TEST + WIFI_STATUS without overwriting stored Wi-Fi config.
#>
[CmdletBinding()]
param(
    [string]$Port = "",
    [switch]$DryRun,
    [switch]$CompileOnly,
    [string]$ConfigFile = "",
    [int]$Baud = 115200,
    [switch]$SkipWifiSetup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    Write-Host "[INFO] $Message"
}

function Write-Warn([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Resolve-PioExecutable {
    $cmd = Get-Command pio -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
        return $cmd.Source
    }
    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\pio.exe"),
        (Join-Path $env:USERPROFILE ".platformio\penv\Scripts\pio.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }
    return $null
}

function Get-UsbSerialDriverAudit {
    $cp210Detected = $false
    $ch340Detected = $false
    $sources = @()

    try {
        $pnpItems = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -match 'CP210|Silicon Labs|CH340|CH341|USB-SERIAL' -or
            $_.Manufacturer -match 'Silicon Labs|wch\.cn|WCH'
        }
        foreach ($item in $pnpItems) {
            if ($item.Name -match 'CP210|Silicon Labs' -or $item.Manufacturer -match 'Silicon Labs') {
                $cp210Detected = $true
                $sources += "PnP:$($item.Name)"
            }
            if ($item.Name -match 'CH340|CH341|USB-SERIAL' -or $item.Manufacturer -match 'wch\.cn|WCH') {
                $ch340Detected = $true
                $sources += "PnP:$($item.Name)"
            }
        }
    } catch {
        Write-Warn "Unable to query Win32_PnPEntity for driver check: $($_.Exception.Message)"
    }

    try {
        $pnpUtilOut = (& pnputil.exe /enum-drivers 2>&1 | Out-String)
        if ($pnpUtilOut -match 'silabser|cp210x|Silicon Labs') {
            $cp210Detected = $true
            $sources += "DriverStore:CP210x"
        }
        if ($pnpUtilOut -match 'ch341ser|ch340|wch\.cn') {
            $ch340Detected = $true
            $sources += "DriverStore:CH340/CH341"
        }
    } catch {
        Write-Warn "Unable to query pnputil driver store: $($_.Exception.Message)"
    }

    return [pscustomobject]@{
        CP210xInstalled = $cp210Detected
        CH340Installed  = $ch340Detected
        Evidence        = ($sources | Select-Object -Unique)
    }
}

function Get-DetectedComPorts {
    $results = New-Object System.Collections.Generic.List[object]
    $seen = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::OrdinalIgnoreCase)

    try {
        $pnpPorts = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object {
            ($_.PNPClass -eq 'Ports') -or ($_.Name -match '\(COM\d+\)')
        }
        foreach ($item in $pnpPorts) {
            if ($item.Name -match '\((COM\d+)\)') {
                $comName = $Matches[1].ToUpperInvariant()
                if ($seen.Add($comName)) {
                    $combined = "$($item.Name) $($item.Manufacturer) $($item.DeviceID)"
                    $isUsb = $combined -match 'CP210|CH340|CH341|Silicon Labs|WCH|USB-SERIAL|UART|FTDI|VID_10C4|VID_1A86|VID_0403'
                    $results.Add([pscustomobject]@{
                        PortName     = $comName
                        Description  = [string]$item.Name
                        Manufacturer = [string]$item.Manufacturer
                        DeviceId     = [string]$item.DeviceID
                        Status       = [string]$item.Status
                        IsUsbSerial  = [bool]$isUsb
                    })
                }
            }
        }
    } catch {
        Write-Warn "Win32_PnPEntity COM scan warning: $($_.Exception.Message)"
    }

    try {
        foreach ($rawPort in [System.IO.Ports.SerialPort]::GetPortNames()) {
            $comName = $rawPort.Trim().ToUpperInvariant()
            if ($comName -match '^COM\d+$' -and $seen.Add($comName)) {
                $results.Add([pscustomobject]@{
                    PortName     = $comName
                    Description  = "Serial Port ($comName)"
                    Manufacturer = "Unknown"
                    DeviceId     = ""
                    Status       = "Detected"
                    IsUsbSerial  = $false
                })
            }
        }
    } catch {
        # Ignore if SerialPort enumeration is unavailable.
    }

    return @($results.ToArray() | Sort-Object PortName)
}

function Get-SuggestedLocalIpv4 {
    try {
        $addrs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
            $_.IPAddress -notmatch '^127\.' -and
            $_.IPAddress -notmatch '^169\.254\.' -and
            $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback|Docker|VirtualBox|VMware'
        }
        $preferred = $addrs | Where-Object {
            $_.IPAddress -match '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)'
        } | Select-Object -First 1
        if ($preferred -and $preferred.IPAddress) {
            return [string]$preferred.IPAddress
        }
        $fallback = $addrs | Select-Object -First 1
        if ($fallback -and $fallback.IPAddress) {
            return [string]$fallback.IPAddress
        }
    } catch {
        # Fall back to default placeholder IP.
    }
    return "192.168.1.100"
}

function ConvertFrom-SecureStringToPlainText([System.Security.SecureString]$SecureValue) {
    if ($null -eq $SecureValue) {
        return ""
    }
    $bstr = [System.IntPtr]::Zero
    try {
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        if ($bstr -ne [System.IntPtr]::Zero) {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

function Get-JsonPropValue([object]$Obj, [string]$Name, $Default = $null) {
    if ($null -ne $Obj -and ($Obj.PSObject.Properties.Name -contains $Name)) {
        return $Obj.$Name
    }
    return $Default
}

function Read-ConfigFromJsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Config file not found: $Path"
    }
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $obj = $raw | ConvertFrom-Json

    $ssidRaw = Get-JsonPropValue $obj "ssid" ""
    $pwdRaw = Get-JsonPropValue $obj "password" $null
    $ipRaw = Get-JsonPropValue $obj "server_ip" ""
    $portRaw = Get-JsonPropValue $obj "server_port" 8088
    $mqttSrvRaw = Get-JsonPropValue $obj "mqtt_server" ""
    $mqttPortRaw = Get-JsonPropValue $obj "mqtt_port" 1883
    $keyRaw = Get-JsonPropValue $obj "hardware_api_key" ""

    if ($null -eq $pwdRaw) { throw "Config file field 'password' is required (use empty string for open Wi-Fi)." }

    $ssid = [string]$ssidRaw
    $password = [string]$pwdRaw
    $serverIp = [string]$ipRaw
    $serverPort = [int]$portRaw
    $mqttServer = if (-not [string]::IsNullOrWhiteSpace([string]$mqttSrvRaw)) { [string]$mqttSrvRaw } else { $serverIp }
    $mqttPort = [int]$mqttPortRaw
    $apiKey = if ($null -ne $keyRaw) { [string]$keyRaw } else { "" }

    if ([string]::IsNullOrWhiteSpace($ssid)) { throw "Config file field 'ssid' is required." }
    if ([string]::IsNullOrWhiteSpace($serverIp)) { throw "Config file field 'server_ip' is required." }
    if ($serverPort -lt 1 -or $serverPort -gt 65535) { throw "Config file field 'server_port' must be 1..65535." }
    if ($mqttPort -lt 1 -or $mqttPort -gt 65535) { throw "Config file field 'mqtt_port' must be 1..65535." }

    return [ordered]@{
        ssid             = $ssid.Trim()
        password         = $password
        server_ip        = $serverIp.Trim()
        server_port      = $serverPort
        mqtt_server      = $mqttServer.Trim()
        mqtt_port        = $mqttPort
        hardware_api_key = $apiKey
    }
}

function Read-ConfigInteractive {
    $suggestedIp = Get-SuggestedLocalIpv4
    Write-Info "Enter runtime Wi-Fi settings (passwords and keys are masked and never printed)."

    $ssid = (Read-Host "Wi-Fi SSID (2.4GHz required)").Trim()
    if ([string]::IsNullOrWhiteSpace($ssid)) {
        throw "Wi-Fi SSID cannot be empty."
    }

    $secPwd = Read-Host "Wi-Fi Password (hidden)" -AsSecureString
    $password = ConvertFrom-SecureStringToPlainText -SecureValue $secPwd

    $ipInput = (Read-Host "Laptop Backend Server IP [$suggestedIp]").Trim()
    $serverIp = if ([string]::IsNullOrWhiteSpace($ipInput)) { $suggestedIp } else { $ipInput }

    $portInput = (Read-Host "Backend Server Port [8088]").Trim()
    $serverPort = 8088
    if (-not [string]::IsNullOrWhiteSpace($portInput)) {
        if (-not [int]::TryParse($portInput, [ref]$serverPort) -or $serverPort -lt 1 -or $serverPort -gt 65535) {
            throw "Invalid server port: $portInput"
        }
    }

    $secKey = Read-Host "Hardware API Key (optional, hidden, Enter to skip)" -AsSecureString
    $apiKey = ConvertFrom-SecureStringToPlainText -SecureValue $secKey

    return [ordered]@{
        ssid             = $ssid
        password         = $password
        server_ip        = $serverIp
        server_port      = $serverPort
        mqtt_server      = $serverIp
        mqtt_port        = 1883
        hardware_api_key = $apiKey
    }
}

function Read-SerialUntilPattern {
    param(
        [System.IO.Ports.SerialPort]$SerialPort,
        [string]$Pattern,
        [int]$TimeoutMs = 5000
    )
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $matchedLine = $null
    while ($sw.ElapsedMilliseconds -lt $TimeoutMs) {
        try {
            $line = $SerialPort.ReadLine()
            if ($null -ne $line) {
                $clean = $line.Trim()
                if ($clean.Length -gt 0) {
                    if ($clean -match $Pattern) {
                        $matchedLine = $clean
                        break
                    }
                }
            }
        } catch [System.TimeoutException] {
            # Continue waiting until TimeoutMs elapses.
        }
    }
    return $matchedLine
}

function Invoke-SerialProvisionAndSelfTest {
    param(
        [string]$ComPort,
        [int]$BaudRate,
        [System.Collections.IDictionary]$WifiConfig,
        [switch]$NoWifiPush
    )

    $sp = New-Object System.IO.Ports.SerialPort($ComPort, $BaudRate, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
    $sp.NewLine = "`n"
    $sp.ReadTimeout = 500
    $sp.WriteTimeout = 2000
    $sp.DtrEnable = $false
    $sp.RtsEnable = $false

    $configOk = $NoWifiPush.IsPresent
    $selfTestLine = $null
    $statusLine = $null

    try {
        Write-Info "Opening serial port $ComPort at $BaudRate baud..."
        $sp.Open()
        Start-Sleep -Milliseconds 1800
        $sp.DiscardInBuffer()

        if (-not $NoWifiPush) {
            if ($null -eq $WifiConfig) {
                throw "Runtime Wi-Fi config is missing."
            }
            Write-Info "Sending runtime WIFI_CONFIG for SSID '$($WifiConfig.ssid)' -> server $($WifiConfig.server_ip):$($WifiConfig.server_port) (secrets masked)..."
            $jsonPayload = ($WifiConfig | ConvertTo-Json -Compress)
            $sp.WriteLine("WIFI_CONFIG $jsonPayload")
            $jsonPayload = $null

            $cfgResp = Read-SerialUntilPattern -SerialPort $sp -Pattern '^(WIFI_CONFIG_OK|WIFI_CONFIG_ERR)\b' -TimeoutMs 5000
            if (-not $cfgResp) {
                Write-Err "No WIFI_CONFIG response from ESP8266 on $ComPort."
                return $false
            }
            Write-Info "Board response: $cfgResp"
            if ($cfgResp -notmatch '^WIFI_CONFIG_OK\b') {
                return $false
            }
            $configOk = $true
            Start-Sleep -Milliseconds 2500
        }

        Write-Info "Running SELF_TEST on $ComPort..."
        $sp.DiscardInBuffer()
        $sp.WriteLine("SELF_TEST")
        $selfTestLine = Read-SerialUntilPattern -SerialPort $sp -Pattern '^SELF_TEST_PASS\b' -TimeoutMs 4000
        if (-not $selfTestLine) {
            Write-Err "SELF_TEST failed or timed out on $ComPort."
            return $false
        }
        Write-Info "Board response: $selfTestLine"

        Write-Info "Checking WIFI_STATUS on $ComPort..."
        $sp.DiscardInBuffer()
        $sp.WriteLine("WIFI_STATUS")
        $statusLine = Read-SerialUntilPattern -SerialPort $sp -Pattern '^WIFI_STATUS_OK\b' -TimeoutMs 4000
        if ($statusLine -and $statusLine -match 'connected=0') {
            Start-Sleep -Milliseconds 2500
            $sp.DiscardInBuffer()
            $sp.WriteLine("WIFI_STATUS")
            $retryStatus = Read-SerialUntilPattern -SerialPort $sp -Pattern '^WIFI_STATUS_OK\b' -TimeoutMs 4000
            if ($retryStatus) {
                $statusLine = $retryStatus
            }
        }
        if (-not $statusLine) {
            Write-Err "WIFI_STATUS failed or timed out on $ComPort."
            return $false
        }
        Write-Info "Board response: $statusLine"
        if ($statusLine -match 'connected=0') {
            Write-Warn "Board is still connecting to Wi-Fi (verify 2.4GHz SSID/password if it does not connect within 15s)."
        }

        return ($configOk -and ($null -ne $selfTestLine) -and ($null -ne $statusLine))
    } finally {
        if ($sp.IsOpen) {
            $sp.Close()
        }
        $sp.Dispose()
    }
}

# ---------------- MAIN EXECUTION ----------------
$repoRoot = Split-Path -Parent $PSScriptRoot
$firmwareDir = Join-Path $repoRoot "firmware\esp8266_smarthome"
$pioIniPath = Join-Path $firmwareDir "platformio.ini"
$inoPath = Join-Path $firmwareDir "esp8266_smarthome.ino"
$defaultLocalCfg = Join-Path $repoRoot "hardware\wifi_local.json"
$isDryMode = $DryRun.IsPresent -or $CompileOnly.IsPresent

Write-Host "============================================================"
Write-Host " Smart Home Voice AI - ESP8266 USB Flash & Wi-Fi Setup"
Write-Host "============================================================"
Write-Info "Repository: $repoRoot"
Write-Info "Firmware  : $firmwareDir"
Write-Info "Mode      : $(if ($isDryMode) { 'DRY-RUN / COMPILE-ONLY (no upload)' } else { 'FLASH + RUNTIME SETUP' })"

if (-not (Test-Path -LiteralPath $pioIniPath) -or -not (Test-Path -LiteralPath $inoPath)) {
    Write-Err "Firmware files not found under $firmwareDir"
    Write-Host "RESULT: FAIL"
    exit 1
}

# 1. Toolchain audit
$pioExe = Resolve-PioExecutable
if (-not $pioExe) {
    Write-Err "PlatformIO (pio) was not found in PATH or $env:USERPROFILE\.local\bin\pio.exe."
    Write-Host "RESULT: FAIL"
    exit 1
}
$pioVer = (& $pioExe --version 2>&1 | Out-String).Trim()
Write-Info "PlatformIO: $pioExe ($pioVer)"

$pioCoreDir = if (-not [string]::IsNullOrWhiteSpace($env:PLATFORMIO_CORE_DIR)) { $env:PLATFORMIO_CORE_DIR } else { Join-Path $env:USERPROFILE ".platformio" }
$esptoolDir = Join-Path $pioCoreDir "packages\tool-esptoolpy"
if (Test-Path -LiteralPath $esptoolDir) {
    Write-Info "esptool   : $esptoolDir"
} else {
    Write-Warn "tool-esptoolpy not yet cached; PlatformIO downloads it automatically during build/upload."
}

# 2. Read-only driver audit
$driverAudit = Get-UsbSerialDriverAudit
Write-Info "Driver CP210x (NodeMCU v2 Amica) : $(if ($driverAudit.CP210xInstalled) { 'INSTALLED' } else { 'NOT DETECTED' })"
Write-Info "Driver CH340/CH341 (NodeMCU v3)  : $(if ($driverAudit.CH340Installed) { 'INSTALLED' } else { 'NOT DETECTED' })"
if (-not $driverAudit.CP210xInstalled -and -not $driverAudit.CH340Installed) {
    Write-Warn "Neither CP210x nor CH340 driver detected in Windows Driver Store (read-only check)."
    Write-Warn "Install Silicon Labs CP210x or WCH CH341SER before flashing if Windows does not assign a COM port."
    Write-Warn "See docs/phan_cung/HUONG_DAN_NAP_FIRMWARE_USB.md for instructions."
}

# 3. Read-only COM port enumeration
$comPorts = @(Get-DetectedComPorts)
if ($comPorts.Count -eq 0) {
    Write-Info "Detected COM ports: NONE"
} else {
    Write-Info "Detected COM ports ($($comPorts.Count)):"
    foreach ($p in $comPorts) {
        $usbTag = if ($p.IsUsbSerial) { "USB-SERIAL" } else { "OTHER" }
        Write-Host ("  - {0} [{1}] {2} ({3})" -f $p.PortName, $usbTag, $p.Description, $p.Manufacturer)
    }
}

# 4. Pre-validate ConfigFile early if supplied
$loadedConfig = $null
if (-not $isDryMode -and -not $SkipWifiSetup -and -not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    try {
        $resolvedCfg = if ([System.IO.Path]::IsPathRooted($ConfigFile)) { $ConfigFile } else { Join-Path $repoRoot $ConfigFile }
        $loadedConfig = Read-ConfigFromJsonFile -Path $resolvedCfg
        Write-Info "Loaded Wi-Fi config from $ConfigFile (SSID='$($loadedConfig.ssid)', server=$($loadedConfig.server_ip):$($loadedConfig.server_port); secrets hidden)."
    } catch {
        Write-Err "Invalid -ConfigFile: $($_.Exception.Message)"
        Write-Host "RESULT: FAIL"
        exit 1
    }
}

# 5. Compile firmware (always executed in both dry-run and flash mode)
Write-Info "Compiling ESP8266 firmware (nodemcuv2) via PlatformIO..."
& $pioExe run -d $firmwareDir
if ($LASTEXITCODE -ne 0) {
    Write-Err "PlatformIO compilation failed with exit code $LASTEXITCODE."
    Write-Host "RESULT: FAIL"
    exit 1
}
Write-Info "Firmware compilation succeeded."

# 6. Stop here in DryRun / CompileOnly mode (NEVER flash a board!)
if ($isDryMode) {
    Write-Info "DRY-RUN / COMPILE-ONLY active: skipping USB upload and serial provisioning (no board flashed)."
    Write-Host "RESULT: PASS"
    exit 0
}

# 7. Select target COM port for real upload
$targetPort = ""
if (-not [string]::IsNullOrWhiteSpace($Port)) {
    $candidate = $Port.Trim().ToUpperInvariant()
    if ($candidate -notmatch '^COM\d+$') {
        Write-Err "Invalid -Port value '$Port'. Expected format like COM3."
        Write-Host "RESULT: FAIL"
        exit 1
    }
    $targetPort = $candidate
} else {
    $usbPorts = @($comPorts | Where-Object { $_.IsUsbSerial })
    if ($usbPorts.Count -eq 1) {
        $targetPort = $usbPorts[0].PortName
        Write-Info "Auto-selected USB-Serial port: $targetPort ($($usbPorts[0].Description))"
    } elseif ($usbPorts.Count -gt 1) {
        Write-Err "Multiple USB-Serial COM ports detected. Re-run with -Port COMx."
        Write-Host "RESULT: FAIL"
        exit 1
    } elseif ($comPorts.Count -eq 1) {
        $targetPort = $comPorts[0].PortName
        Write-Warn "Auto-selected single COM port: $targetPort ($($comPorts[0].Description))"
    } else {
        Write-Err "No COM port detected. Check Micro-USB data cable and CP210x/CH340 driver."
        Write-Host "RESULT: FAIL"
        exit 1
    }
}

# 8. Upload firmware over USB
Write-Info "Uploading firmware to $targetPort via PlatformIO..."
& $pioExe run -d $firmwareDir -t upload --upload-port $targetPort
if ($LASTEXITCODE -ne 0) {
    Write-Err "Upload to $targetPort failed with exit code $LASTEXITCODE."
    Write-Err "Check port access (close Serial Monitor), Micro-USB cable, and boot-strap pins D3/D4/D8."
    Write-Host "RESULT: FAIL"
    exit 1
}
Write-Info "Firmware upload to $targetPort succeeded."

# 9. Gather runtime Wi-Fi config if not skipped and not already loaded
if (-not $SkipWifiSetup -and $null -eq $loadedConfig) {
    if (Test-Path -LiteralPath $defaultLocalCfg) {
        $ans = (Read-Host "Found git-ignored hardware/wifi_local.json. Use it? [Y/n]").Trim()
        if ([string]::IsNullOrWhiteSpace($ans) -or $ans -match '^(y|yes)$') {
            try {
                $loadedConfig = Read-ConfigFromJsonFile -Path $defaultLocalCfg
                Write-Info "Loaded hardware/wifi_local.json (SSID='$($loadedConfig.ssid)'; secrets hidden)."
            } catch {
                Write-Err "Failed to read hardware/wifi_local.json: $($_.Exception.Message)"
                Write-Host "RESULT: FAIL"
                exit 1
            }
        }
    }
    if ($null -eq $loadedConfig) {
        try {
            $loadedConfig = Read-ConfigInteractive
        } catch {
            Write-Err "Wi-Fi config input failed: $($_.Exception.Message)"
            Write-Host "RESULT: FAIL"
            exit 1
        }
    }
}

# 10. Provision Wi-Fi and run serial self-test
try {
    $ok = Invoke-SerialProvisionAndSelfTest -ComPort $targetPort -BaudRate $Baud -WifiConfig $loadedConfig -NoWifiPush:$SkipWifiSetup
    if ($ok) {
        Write-Host "RESULT: PASS"
        exit 0
    } else {
        Write-Host "RESULT: FAIL"
        exit 1
    }
} catch {
    Write-Err "Serial provisioning/self-test error: $($_.Exception.Message)"
    Write-Host "RESULT: FAIL"
    exit 1
}
