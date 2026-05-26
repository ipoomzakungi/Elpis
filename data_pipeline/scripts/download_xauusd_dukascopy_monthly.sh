#!/usr/bin/env bash
set -euo pipefail

FROM="${FROM:-2024-01-01}"
TO="${TO:-now}"
INSTRUMENT="${INSTRUMENT:-xauusd}"
TIMEFRAME="${TIMEFRAME:-m1}"
FORCE="${FORCE:-0}"
NO_COMBINE="${NO_COMBINE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

RAW_DIR="./data/raw/dukascopy"
MONTHLY_DIR="${RAW_DIR}/monthly"
mkdir -p "${MONTHLY_DIR}"

if [[ "${1:-}" == "--install" ]]; then
  npm install
fi

normalize_csv_name() {
  local expected="$1"
  if [[ -f "${expected}.csv" && ! -f "${expected}" ]]; then
    mv "${expected}.csv" "${expected}"
  fi
}

date_to_epoch() {
  date -u -d "$1" +%s
}

month_add_one() {
  date -u -d "$1 +1 month" +%Y-%m-01
}

download_month_side() {
  local side="$1"
  local chunk_start="$2"
  local chunk_end="$3"
  local month_label
  month_label="$(date -u -d "${chunk_start}" +%Y-%m)"
  local filename="xauusd_m1_${side}_${month_label}.csv"
  local expected_path="${MONTHLY_DIR}/${filename}"
  normalize_csv_name "${expected_path}"

  if [[ -s "${expected_path}" && "${FORCE}" != "1" ]]; then
    echo "Skipping existing ${side} ${month_label} ($(wc -c < "${expected_path}") bytes)"
    return
  fi

  echo "Downloading ${side} ${chunk_start} -> ${chunk_end}"
  npx dukascopy-node -i "${INSTRUMENT}" -from "${chunk_start}" -to "${chunk_end}" -t "${TIMEFRAME}" -p "${side}" -f csv -dir ./data/raw/dukascopy/monthly -fn "${filename}"
  normalize_csv_name "${expected_path}"
}

combine_side() {
  local side="$1"
  local output="${RAW_DIR}/xauusd_m1_${side}_2024_to_now.csv"
  local first=1
  : > "${output}"
  shopt -s nullglob
  for file in "${MONTHLY_DIR}"/xauusd_m1_"${side}"_*.csv; do
    if [[ "${first}" == "1" ]]; then
      cat "${file}" >> "${output}"
      first=0
    else
      tail -n +2 "${file}" >> "${output}"
    fi
  done
  shopt -u nullglob
  if [[ ! -s "${output}" ]]; then
    echo "No monthly ${side} CSV files found under ${MONTHLY_DIR}" >&2
    exit 1
  fi
  echo "Combined ${side} monthly files -> ${output} ($(wc -c < "${output}") bytes)"
}

TO_IS_NOW=0
if [[ "${TO}" == "now" ]]; then
  TO_IS_NOW=1
  TO_DATE="$(date -u +%Y-%m-%d)"
else
  TO_DATE="${TO}"
fi

current="${FROM}"
while [[ "$(date_to_epoch "${current}")" -lt "$(date_to_epoch "${TO_DATE}")" ]]; do
  next_month="$(month_add_one "${current}")"
  if [[ "$(date_to_epoch "${next_month}")" -lt "$(date_to_epoch "${TO_DATE}")" ]]; then
    chunk_end="${next_month}"
  else
    if [[ "${TO_IS_NOW}" == "1" ]]; then
      chunk_end="now"
    else
      chunk_end="${TO_DATE}"
    fi
  fi
  download_month_side "bid" "${current}" "${chunk_end}"
  download_month_side "ask" "${current}" "${chunk_end}"
  if [[ "${chunk_end}" == "now" ]]; then
    current="${TO_DATE}"
  else
    current="${chunk_end}"
  fi
done

if [[ "${NO_COMBINE}" != "1" ]]; then
  combine_side "bid"
  combine_side "ask"
fi
