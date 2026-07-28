[CmdletBinding()]
param(
    [string]$SessionDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$CdpUrl = "http://127.0.0.1:9222",
    [string]$BrokerQuoteFile = "",
    [switch]$SkipFetch,
    [switch]$DoNotStartBrowser
)

$ErrorActionPreference = "Stop"
$backendRoot = Split-Path -Parent $PSScriptRoot
$parsedCdp = [Uri]$CdpUrl
$cdpPort = $parsedCdp.Port
$dukascopyDateTo = ([datetime]::ParseExact(
    $SessionDate,
    "yyyy-MM-dd",
    [Globalization.CultureInfo]::InvariantCulture
)).AddDays(1).ToString("yyyy-MM-dd")

Push-Location $backendRoot
try {
    if (-not $SkipFetch) {
        $cdpReady = $false
        try {
            Invoke-RestMethod -Uri "$CdpUrl/json/version" -TimeoutSec 2 | Out-Null
            $cdpReady = $true
        }
        catch {
            if (-not $DoNotStartBrowser) {
                & "$PSScriptRoot/start_vol2vol_cdp_browser.ps1" -Port $cdpPort
                Invoke-RestMethod -Uri "$CdpUrl/json/version" -TimeoutSec 2 | Out-Null
                $cdpReady = $true
            }
        }
        if (-not $cdpReady) {
            throw "Authenticated Vol2Vol CDP browser is unavailable at $CdpUrl"
        }

        python scripts/collect_vol2vol_browser_history.py `
            --session-date $SessionDate `
            --cdp-url $CdpUrl `
            --refresh `
            --include-current-incomplete-session
        if ($LASTEXITCODE -ne 0) {
            throw "Exact-date Vol2Vol collection failed with exit code $LASTEXITCODE"
        }

        python scripts/fetch_xau_dukascopy_range.py `
            --date-from $SessionDate `
            --date-to $dukascopyDateTo `
            --append
        if ($LASTEXITCODE -ne 0) {
            throw "Dukascopy XAUUSD collection failed with exit code $LASTEXITCODE"
        }
    }

    $arguments = @(
        "scripts/run_xau_ft2_candidate.py",
        "--session-date-from", "2026-05-31",
        "--session-date-to", $SessionDate,
        "--as-of-date", $SessionDate
    )
    if ($BrokerQuoteFile) {
        $arguments += @("--broker-quote-file", $BrokerQuoteFile)
    }
    python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "FT2 candidate run failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
