param(
    [string]$From = "2024-01-01",
    [string]$To = "now",
    [string]$Instrument = "xauusd",
    [string]$Timeframe = "m1",
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

New-Item -ItemType Directory -Force -Path ".\data\raw\dukascopy" | Out-Null

if ($Install) {
    npm install
}

npx dukascopy-node -i $Instrument -from $From -to $To -t $Timeframe -p bid -f csv -dir ./data/raw/dukascopy -fn xauusd_m1_bid_2024_to_now.csv
if ((Test-Path ".\data\raw\dukascopy\xauusd_m1_bid_2024_to_now.csv.csv") -and -not (Test-Path ".\data\raw\dukascopy\xauusd_m1_bid_2024_to_now.csv")) {
    Move-Item ".\data\raw\dukascopy\xauusd_m1_bid_2024_to_now.csv.csv" ".\data\raw\dukascopy\xauusd_m1_bid_2024_to_now.csv"
}
npx dukascopy-node -i $Instrument -from $From -to $To -t $Timeframe -p ask -f csv -dir ./data/raw/dukascopy -fn xauusd_m1_ask_2024_to_now.csv
if ((Test-Path ".\data\raw\dukascopy\xauusd_m1_ask_2024_to_now.csv.csv") -and -not (Test-Path ".\data\raw\dukascopy\xauusd_m1_ask_2024_to_now.csv")) {
    Move-Item ".\data\raw\dukascopy\xauusd_m1_ask_2024_to_now.csv.csv" ".\data\raw\dukascopy\xauusd_m1_ask_2024_to_now.csv"
}
