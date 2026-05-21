param(
    [string]$ConfigPath = "",
    [int]$CdpPort = 9222,
    [string]$Browser = "msedge",
    [string]$ProfilePath = "$env:LOCALAPPDATA\Elpis\quikstrike-browser-profile",
    [string]$ProfileDirectory = "",
    [string]$StartUrl = "https://cmegroup-sso.quikstrike.net//User/QuikStrikeView.aspx?mode=",
    [int]$WaitSeconds = 900,
    [int]$PollSeconds = 5,
    [string]$CaptureSession = "",
    [double]$XauUsdSpotReference = 0,
    [double]$GcFuturesReference = 0,
    [double]$SessionOpenPrice = 0,
    [double]$RealizedVolatility = 0,
    [switch]$SkipBrowserLaunch,
    [switch]$ManualPrompts,
    [switch]$ForceCreate,
    [switch]$KeepBrowserOpen,
    [switch]$CloseBrowser
)

$ErrorActionPreference = "Stop"

function New-DefaultRunnerConfig {
    param(
        [string]$Path,
        [int]$DefaultCdpPort,
        [string]$DefaultBrowser,
        [string]$DefaultProfilePath,
        [string]$DefaultProfileDirectory,
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
        "QUIKSTRIKE_PROFILE_DIRECTORY=$DefaultProfileDirectory",
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

function Resolve-LocalPath {
    param(
        [string]$Path,
        [string]$BasePath
    )
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $Path))
}

function Assert-ProfilePathOutsideRepo {
    param(
        [string]$Path,
        [string]$RepoRoot
    )
    $profileFullPath = Resolve-LocalPath -Path $Path -BasePath $RepoRoot
    $repoFullPath = [System.IO.Path]::GetFullPath($RepoRoot)
    if (-not $repoFullPath.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $repoFullPath = "$repoFullPath$([System.IO.Path]::DirectorySeparatorChar)"
    }
    if ($profileFullPath.StartsWith($repoFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "ProfilePath must stay outside the repo because browser profiles contain cookies/session cache. Keep only the runner config in the workspace."
    }
}

function Get-QuikStrikeBrowserProcesses {
    param(
        [int]$Port,
        [string]$ProfilePath
    )
    $profileFullPath = [System.IO.Path]::GetFullPath($ProfilePath).ToLowerInvariant()
    $debugArg = "--remote-debugging-port=$Port".ToLowerInvariant()
    Get-CimInstance Win32_Process | Where-Object {
        if (-not $_.CommandLine) {
            return $false
        }
        $commandLine = $_.CommandLine.ToLowerInvariant()
        return $commandLine.Contains($debugArg) -and $commandLine.Contains($profileFullPath)
    }
}

function Get-BrowserProfileProcesses {
    param([string]$ProfilePath)
    $profileFullPath = [System.IO.Path]::GetFullPath($ProfilePath).ToLowerInvariant()
    Get-CimInstance Win32_Process | Where-Object {
        if (-not $_.CommandLine) {
            return $false
        }
        $commandLine = $_.CommandLine.ToLowerInvariant()
        return $commandLine.Contains($profileFullPath)
    }
}

function Test-IsSharedEdgeProfile {
    param([string]$ProfilePath)
    $profileFullPath = [System.IO.Path]::GetFullPath($ProfilePath).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $defaultEdgeProfile = [System.IO.Path]::GetFullPath(
        (Join-Path $env:LOCALAPPDATA "Microsoft\Edge\User Data")
    ).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    return $profileFullPath.Equals($defaultEdgeProfile, [System.StringComparison]::OrdinalIgnoreCase)
}

function Stop-QuikStrikeBrowser {
    param(
        [int]$Port,
        [string]$ProfilePath
    )
    $processes = @(Get-QuikStrikeBrowserProcesses -Port $Port -ProfilePath $ProfilePath)
    if (-not $processes.Count) {
        Write-Host "No matching QuikStrike CDP browser process remained open."
        return
    }
    foreach ($processInfo in $processes) {
        try {
            $process = Get-Process -Id $processInfo.ProcessId -ErrorAction Stop
            if ($process.MainWindowHandle -ne 0) {
                [void]$process.CloseMainWindow()
            }
        }
        catch {
            continue
        }
    }
    Start-Sleep -Seconds 2
    foreach ($processInfo in @(Get-QuikStrikeBrowserProcesses -Port $Port -ProfilePath $ProfilePath)) {
        try {
            Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction Stop
        }
        catch {
            continue
        }
    }
    Write-Host "Closed QuikStrike CDP browser for profile:"
    Write-Host "  $ProfilePath"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $repoRoot ".quikstrike-runner.local.env"
}
$ConfigPath = Resolve-LocalPath -Path $ConfigPath -BasePath $repoRoot

New-DefaultRunnerConfig `
    -Path $ConfigPath `
    -DefaultCdpPort $CdpPort `
    -DefaultBrowser $Browser `
    -DefaultProfilePath $ProfilePath `
    -DefaultProfileDirectory $ProfileDirectory `
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
if (-not $PSBoundParameters.ContainsKey("ProfileDirectory") -and $runnerConfig.ContainsKey("QUIKSTRIKE_PROFILE_DIRECTORY")) {
    $ProfileDirectory = $runnerConfig["QUIKSTRIKE_PROFILE_DIRECTORY"]
}
if (-not $PSBoundParameters.ContainsKey("WaitSeconds") -and $runnerConfig.ContainsKey("QUIKSTRIKE_WAIT_SECONDS")) {
    $WaitSeconds = [int]$runnerConfig["QUIKSTRIKE_WAIT_SECONDS"]
}
if (-not $PSBoundParameters.ContainsKey("PollSeconds") -and $runnerConfig.ContainsKey("QUIKSTRIKE_POLL_SECONDS")) {
    $PollSeconds = [int]$runnerConfig["QUIKSTRIKE_POLL_SECONDS"]
}

Assert-ProfilePathOutsideRepo -Path $ProfilePath -RepoRoot $repoRoot
$isSharedEdgeProfile = Test-IsSharedEdgeProfile -ProfilePath $ProfilePath

Write-Host "Using QuikStrike runner config:"
Write-Host "  $ConfigPath"
Write-Host "Using local browser profile:"
Write-Host "  $ProfilePath"
if ($ProfileDirectory) {
    Write-Host "Using Edge profile directory:"
    Write-Host "  $ProfileDirectory"
}

if (-not $SkipBrowserLaunch -and -not (Test-CdpPort -Port $CdpPort)) {
    if ($isSharedEdgeProfile -and @(Get-BrowserProfileProcesses -ProfilePath $ProfilePath).Count) {
        throw (
            "The normal Edge profile is already open without local CDP on port $CdpPort. " +
            "Close normal Edge first, or start Edge yourself with --remote-debugging-port=$CdpPort " +
            "and rerun with -SkipBrowserLaunch."
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
    if ($ForceCreate) {
        $pythonArgs += @("--force-create")
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
    if ($CloseBrowser -and -not $SkipBrowserLaunch) {
        Stop-QuikStrikeBrowser -Port $CdpPort -ProfilePath $ProfilePath
    }
    elseif ($isSharedEdgeProfile -and -not $SkipBrowserLaunch) {
        Write-Host "Leaving normal Edge profile open to avoid closing your working browser."
    }
    elseif (-not $SkipBrowserLaunch -and -not $KeepBrowserOpen) {
        Stop-QuikStrikeBrowser -Port $CdpPort -ProfilePath $ProfilePath
    }
    elseif ($SkipBrowserLaunch) {
        Write-Host "Leaving browser open because -SkipBrowserLaunch was used."
    }
    elseif ($KeepBrowserOpen) {
        Write-Host "Leaving browser open because -KeepBrowserOpen was used."
    }
}
