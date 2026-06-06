param(
    [int]$CdpPort = 9222,
    [string]$Browser = "msedge",
    [string]$ProfilePath = "$env:LOCALAPPDATA\Elpis\quikstrike-browser-profile",
    [string]$ProfileDirectory = "",
    [string]$StartUrl = "https://cmegroup-sso.quikstrike.net//User/QuikStrikeView.aspx?mode=",
    [switch]$AutoLogin,
    [string]$EnvFile = ".env"
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

function Get-BrowserProfileProcesses {
    param([string]$Path)
    $profileFullPath = [System.IO.Path]::GetFullPath($Path).ToLowerInvariant()
    Get-CimInstance Win32_Process | Where-Object {
        if (-not $_.CommandLine) {
            return $false
        }
        return $_.CommandLine.ToLowerInvariant().Contains($profileFullPath)
    }
}

if (Test-CdpPort -Port $CdpPort) {
    Write-Host "QuikStrike CDP browser is already available on port $CdpPort."
    if ($AutoLogin) {
        Push-Location (Split-Path -Parent $PSScriptRoot)
        try {
            Push-Location "backend"
            python scripts/quikstrike_browser_login.py `
                --cdp-url "http://127.0.0.1:$CdpPort" `
                --start-url $StartUrl `
                --env-file $EnvFile
        }
        finally {
            Pop-Location
            Pop-Location
        }
    }
    Write-Host "Use this for fast snapshots:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\run_daily_xau_quikstrike_snapshot.ps1 -Fast"
    exit 0
}

if (@(Get-BrowserProfileProcesses -Path $ProfilePath).Count) {
    throw (
        "The QuikStrike profile is already open without CDP on port $CdpPort. " +
        "Close that browser first, then rerun this session launcher."
    )
}

New-Item -ItemType Directory -Force -Path $ProfilePath | Out-Null
$browserPath = Resolve-BrowserPath -BrowserName $Browser
$browserArgs = @(
    "--remote-debugging-port=$CdpPort",
    "`"--user-data-dir=$ProfilePath`"",
    "--disable-sync",
    "--no-first-run",
    "--no-default-browser-check",
    $StartUrl
)
if ($ProfileDirectory) {
    $browserArgs = @(
        "--remote-debugging-port=$CdpPort",
        "`"--user-data-dir=$ProfilePath`"",
        "--profile-directory=$ProfileDirectory",
        "--disable-sync",
        "--no-first-run",
        "--no-default-browser-check",
        $StartUrl
    )
}

Start-Process -FilePath $browserPath -ArgumentList $browserArgs | Out-Null
Write-Host "Opened $Browser with local CDP on port ${CdpPort}:"
Write-Host "  $ProfilePath"
if ($AutoLogin) {
    Start-Sleep -Seconds 3
    Push-Location (Split-Path -Parent $PSScriptRoot)
    try {
        Push-Location "backend"
        python scripts/quikstrike_browser_login.py `
            --cdp-url "http://127.0.0.1:$CdpPort" `
            --start-url $StartUrl `
            --env-file $EnvFile
    }
    finally {
        Pop-Location
        Pop-Location
    }
}
Write-Host "Log in once in this browser, keep it open, then run:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\run_daily_xau_quikstrike_snapshot.ps1 -Fast"
