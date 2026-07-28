param(
    [string]$SessionDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$CdpUrl = "http://127.0.0.1:9222",
    [string]$BrokerQuoteFile = "",
    [switch]$SkipFetch
)

$ErrorActionPreference = "Stop"
$backendRoot = Split-Path -Parent $PSScriptRoot
$DukascopyDateTo = ([datetime]::ParseExact(
    $SessionDate,
    "yyyy-MM-dd",
    [Globalization.CultureInfo]::InvariantCulture
)).AddDays(1).ToString("yyyy-MM-dd")
Push-Location $backendRoot
try {
    if (-not $SkipFetch) {
        python scripts/collect_vol2vol_browser_history.py `
            --session-date $SessionDate `
            --cdp-url $CdpUrl `
            --refresh `
            --include-current-incomplete-session
        if ($LASTEXITCODE -ne 0) {
            throw "Vol2Vol refresh failed with exit code $LASTEXITCODE"
        }

        python scripts/fetch_xau_dukascopy_range.py `
            --date-from $SessionDate `
            --date-to $DukascopyDateTo `
            --append
        if ($LASTEXITCODE -ne 0) {
            throw "Dukascopy XAUUSD refresh failed with exit code $LASTEXITCODE"
        }
    }

    $arguments = @(
        "scripts/run_xau_tiered_manual_signal.py",
        "--session-date-from", "2026-05-31",
        "--session-date-to", $SessionDate,
        "--as-of-date", $SessionDate
    )
    if ($BrokerQuoteFile) {
        $arguments += @("--broker-quote-file", $BrokerQuoteFile)
    }
    python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Tiered manual-signal run failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
