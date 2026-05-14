param(
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
    [switch]$SkipBrowserLaunch
)

$ErrorActionPreference = "Stop"

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

Push-Location $backendDir
try {
    $pythonArgs = @(
        "scripts/xau_daily_quikstrike_snapshot.py",
        "--cdp-url", "http://127.0.0.1:$CdpPort",
        "--wait-seconds", "$WaitSeconds",
        "--poll-seconds", "$PollSeconds"
    )
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
