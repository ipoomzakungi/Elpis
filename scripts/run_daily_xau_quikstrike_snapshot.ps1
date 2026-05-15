param(
    [string]$ConfigPath = "$env:LOCALAPPDATA\Elpis\quikstrike-runner.env",
    [int]$CdpPort = 9222,
    [string]$Browser = "msedge",
    [string]$ProfilePath = "$env:LOCALAPPDATA\Elpis\quikstrike-browser-profile",
    [string]$StartUrl = "https://cmegroup-sso.quikstrike.net//User/QuikStrikeView.aspx?mode=",
    [int]$WaitSeconds = 900,
    [int]$PollSeconds = 5,
    [string]$CaptureSession = "",
    [double]$XauUsdSpotReference = 0,
    [double]$GcFuturesReference = 0,
    [double]$SessionOpenPrice = 0,
    [double]$RealizedVolatility = 0,
    [switch]$SkipBrowserLaunch,
    [switch]$ManualPrompts
)

$ErrorActionPreference = "Stop"

function New-DefaultRunnerConfig {
    param(
        [string]$Path,
        [int]$DefaultCdpPort,
        [string]$DefaultBrowser,
        [string]$DefaultProfilePath,
        [int]$DefaultWaitSeconds,
        [int]$DefaultPollSeconds
    )
    if (Test-Path -LiteralPath $Path) {
        return
    }
    $parent = Split-Path -Parent $Path
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $lines = @(
        "# Local non-secret QuikStrike daily runner settings.",
        "# Do not put credentials, cookies, headers, tokens, sessions, HAR, or viewstate here.",
        "QUIKSTRIKE_CDP_PORT=$DefaultCdpPort",
        "QUIKSTRIKE_BROWSER=$DefaultBrowser",
        "QUIKSTRIKE_PROFILE_PATH=$DefaultProfilePath",
        "QUIKSTRIKE_WAIT_SECONDS=$DefaultWaitSeconds",
        "QUIKSTRIKE_POLL_SECONDS=$DefaultPollSeconds"
    )
    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
}

function Read-RunnerConfig {
    param([string]$Path)
    $config = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $config
    }
    $forbiddenKeyPattern = "AUTH|COOKIE|CREDENTIAL|HEADER|HAR|PASSWORD|SECRET|SESSION|TOKEN|USERNAME|VIEWSTATE"
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($key -match $forbiddenKeyPattern) {
            throw "Runner config contains forbidden credential/session key: $key"
        }
        $config[$key] = $value
    }
    return $config
}

function Test-CdpPort {
    param([int]$Port)
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Resolve-BrowserPath {
    param([string]$BrowserName)
    $candidates = @()
    if ($BrowserName -eq "chrome") {
        $candidates += "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
        $candidates += "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
    }
    else {
        $candidates += "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
        $candidates += "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }
    throw "Could not find $BrowserName. Pass -Browser chrome or install Edge/Chrome."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"

New-DefaultRunnerConfig `
    -Path $ConfigPath `
    -DefaultCdpPort $CdpPort `
    -DefaultBrowser $Browser `
    -DefaultProfilePath $ProfilePath `
    -DefaultWaitSeconds $WaitSeconds `
    -DefaultPollSeconds $PollSeconds

$runnerConfig = Read-RunnerConfig -Path $ConfigPath
if (-not $PSBoundParameters.ContainsKey("CdpPort") -and $runnerConfig.ContainsKey("QUIKSTRIKE_CDP_PORT")) {
    $CdpPort = [int]$runnerConfig["QUIKSTRIKE_CDP_PORT"]
}
if (-not $PSBoundParameters.ContainsKey("Browser") -and $runnerConfig.ContainsKey("QUIKSTRIKE_BROWSER")) {
    $Browser = $runnerConfig["QUIKSTRIKE_BROWSER"]
}
if (-not $PSBoundParameters.ContainsKey("ProfilePath") -and $runnerConfig.ContainsKey("QUIKSTRIKE_PROFILE_PATH")) {
    $ProfilePath = $runnerConfig["QUIKSTRIKE_PROFILE_PATH"]
}
if (-not $PSBoundParameters.ContainsKey("WaitSeconds") -and $runnerConfig.ContainsKey("QUIKSTRIKE_WAIT_SECONDS")) {
    $WaitSeconds = [int]$runnerConfig["QUIKSTRIKE_WAIT_SECONDS"]
}
if (-not $PSBoundParameters.ContainsKey("PollSeconds") -and $runnerConfig.ContainsKey("QUIKSTRIKE_POLL_SECONDS")) {
    $PollSeconds = [int]$runnerConfig["QUIKSTRIKE_POLL_SECONDS"]
}

Write-Host "Using QuikStrike runner config:"
Write-Host "  $ConfigPath"
Write-Host "Using local browser profile:"
Write-Host "  $ProfilePath"

if (-not $SkipBrowserLaunch -and -not (Test-CdpPort -Port $CdpPort)) {
    New-Item -ItemType Directory -Force -Path $ProfilePath | Out-Null
    $browserPath = Resolve-BrowserPath -BrowserName $Browser
    $browserArgs = @(
        "--remote-debugging-port=$CdpPort",
        "--user-data-dir=$ProfilePath",
        "--disable-sync",
        $StartUrl
    )
    Start-Process -FilePath $browserPath -ArgumentList $browserArgs
    Write-Host "Opened $Browser with local CDP on port $CdpPort and non-sync profile:"
    Write-Host "  $ProfilePath"
}
elseif (Test-CdpPort -Port $CdpPort) {
    Write-Host "Reusing existing local CDP browser on port $CdpPort."
}

Push-Location $backendDir
try {
    $pythonArgs = @(
        "scripts/xau_daily_quikstrike_snapshot.py",
        "--cdp-url", "http://127.0.0.1:$CdpPort",
        "--wait-seconds", "$WaitSeconds",
        "--poll-seconds", "$PollSeconds"
    )
    if (-not $ManualPrompts) {
        $pythonArgs += @("--no-prompt")
    }
    if ($CaptureSession) {
        $pythonArgs += @("--capture-session", $CaptureSession)
    }
    if ($XauUsdSpotReference -gt 0) {
        $pythonArgs += @("--xauusd-spot-reference", "$XauUsdSpotReference")
    }
    if ($GcFuturesReference -gt 0) {
        $pythonArgs += @("--gc-futures-reference", "$GcFuturesReference")
    }
    if ($SessionOpenPrice -gt 0) {
        $pythonArgs += @("--session-open-price", "$SessionOpenPrice")
    }
    if ($RealizedVolatility -gt 0) {
        $pythonArgs += @("--realized-volatility", "$RealizedVolatility")
    }
    python @pythonArgs
}
finally {
    Pop-Location
}
