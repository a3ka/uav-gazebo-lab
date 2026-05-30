#!/usr/bin/env bash
# Phase 9 — same-region forgery campaign orchestrator (vast.ai entry point).
#
# Single-command end-to-end execution: acquisition -> trials -> analyze.
# Designed to run inside the uav-lab:gpu Docker container or any
# vast.ai instance with CUDA torch + lightglue + GDAL / rasterio.
#
# Required environment:
#   CDSE_USERNAME, CDSE_PASSWORD  (Copernicus Data Space Ecosystem credentials)
#
# Outputs:
#   workspaces/phase9-acquisition/<tile_id>/dt_YYYYMMDD.png  (gitignored)
#   workspaces/phase9-acquisition-manifest.csv               (committed)
#   workspaces/phase9-sweep/forgery_trials.csv               (gitignored; committed summary in docs/results/phase-9.md)
#   workspaces/phase9-sweep/figures/*.png                    (gitignored)
#   docs/results/phase-9.md                                  (populated)
#
# Usage:
#   ./scripts/phase9-campaign.sh

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==[ Phase 9 — same-region forgery campaign ]=="
date -u +"started: %Y-%m-%dT%H:%M:%SZ"

if [[ -z "${CDSE_USERNAME:-}" || -z "${CDSE_PASSWORD:-}" ]]; then
    echo "FAIL: set CDSE_USERNAME and CDSE_PASSWORD env vars first." >&2
    exit 1
fi

echo
echo "--[ step 1/3: Sentinel-2 multi-temporal acquisition ]--"
python3 scripts/phase9-acquisition.py \
    --out workspaces/phase9-acquisition

echo
echo "--[ step 2/3: forgery trials (Mode A) ]--"
python3 scripts/phase9-forgery-trials.py \
    --acquisition workspaces/phase9-acquisition \
    --out workspaces/phase9-sweep/forgery_trials.csv \
    --n-honest 500 \
    --n-wrong 500 \
    --n-same 500 \
    --t-verify 0.30 \
    --seed 42

echo
echo "--[ step 3/3: analyse + write docs/results/phase-9.md ]--"
python3 scripts/phase9-analyze.py \
    --csv workspaces/phase9-sweep/forgery_trials.csv \
    --figdir workspaces/phase9-sweep/figures \
    --out docs/results/phase-9.md

echo
date -u +"finished: %Y-%m-%dT%H:%M:%SZ"
echo "==[ Phase 9 DONE — review docs/results/phase-9.md ]=="
