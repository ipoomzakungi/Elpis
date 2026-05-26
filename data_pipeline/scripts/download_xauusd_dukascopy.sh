#!/usr/bin/env bash
set -euo pipefail

FROM="${FROM:-2024-01-01}"
TO="${TO:-now}"
INSTRUMENT="${INSTRUMENT:-xauusd}"
TIMEFRAME="${TIMEFRAME:-m1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

mkdir -p ./data/raw/dukascopy

if [[ "${1:-}" == "--install" ]]; then
  npm install
fi

npx dukascopy-node -i "${INSTRUMENT}" -from "${FROM}" -to "${TO}" -t "${TIMEFRAME}" -p bid -f csv -dir ./data/raw/dukascopy -fn xauusd_m1_bid_2024_to_now.csv
if [[ -f ./data/raw/dukascopy/xauusd_m1_bid_2024_to_now.csv.csv && ! -f ./data/raw/dukascopy/xauusd_m1_bid_2024_to_now.csv ]]; then
  mv ./data/raw/dukascopy/xauusd_m1_bid_2024_to_now.csv.csv ./data/raw/dukascopy/xauusd_m1_bid_2024_to_now.csv
fi
npx dukascopy-node -i "${INSTRUMENT}" -from "${FROM}" -to "${TO}" -t "${TIMEFRAME}" -p ask -f csv -dir ./data/raw/dukascopy -fn xauusd_m1_ask_2024_to_now.csv
if [[ -f ./data/raw/dukascopy/xauusd_m1_ask_2024_to_now.csv.csv && ! -f ./data/raw/dukascopy/xauusd_m1_ask_2024_to_now.csv ]]; then
  mv ./data/raw/dukascopy/xauusd_m1_ask_2024_to_now.csv.csv ./data/raw/dukascopy/xauusd_m1_ask_2024_to_now.csv
fi
