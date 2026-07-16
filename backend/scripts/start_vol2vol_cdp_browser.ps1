[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 9222,

    [switch]$FreshProfile,

    [string]$ProfileRoot = (Join-Path $env:LOCALAPPDATA "Elpis")
)

$ErrorActionPreference = "Stop"

$edgeCandidates = @(@(
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
    (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) })

if (-not $edgeCandidates) {
    throw "Microsoft Edge was not found in the standard installation paths."
}

$profileName = if ($FreshProfile) {
    "quikstrike-browser-profile-{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")
} else {
    "quikstrike-browser-profile"
}
$profilePath = Join-Path $ProfileRoot $profileName
$resolvedRoot = [System.IO.Path]::GetFullPath($ProfileRoot)
$resolvedProfile = [System.IO.Path]::GetFullPath($profilePath)
if (-not $resolvedProfile.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Resolved profile path is outside ProfileRoot."
}

New-Item -ItemType Directory -Path $resolvedProfile -Force | Out-Null

$debugEndpoint = "http://127.0.0.1:$Port/json/version"
try {
    Invoke-RestMethod -Uri $debugEndpoint -TimeoutSec 1 | Out-Null
    throw "CDP port $Port is already active. Reuse it or choose another port."
} catch {
    if ($_.Exception.Message -like "CDP port*") {
        throw
    }
}

$arguments = @(
    "--remote-debugging-port=$Port"
    "--user-data-dir=$resolvedProfile"
    "--no-first-run"
    "--no-default-browser-check"
    "https://www.vol2vol.com/"
)
$edgePath = [string]$edgeCandidates[0]
if (-not (Test-Path -LiteralPath $edgePath -PathType Leaf)) {
    throw "Resolved Microsoft Edge executable is invalid: $edgePath"
}
Start-Process -FilePath $edgePath -ArgumentList $arguments

$ready = $false
foreach ($attempt in 1..20) {
    Start-Sleep -Milliseconds 500
    try {
        Invoke-RestMethod -Uri $debugEndpoint -TimeoutSec 1 | Out-Null
        $ready = $true
        break
    } catch {
        # Edge may need several seconds to create a new profile.
    }
}
if (-not $ready) {
    throw "Edge started, but CDP port $Port did not become ready."
}

Write-Host "Vol2Vol CDP browser ready."
Write-Host "Profile: $resolvedProfile"
Write-Host "CDP URL: http://127.0.0.1:$Port"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Use Vol2Vol's supported 24-hour server-support link in this profile."
Write-Host "2. Close the external support tab and return to Vol2Vol."
Write-Host "3. Run:"
Write-Host "   python scripts/collect_vol2vol_browser_history.py --all-available --include-current-incomplete-session --refresh --cdp-url http://127.0.0.1:$Port"
