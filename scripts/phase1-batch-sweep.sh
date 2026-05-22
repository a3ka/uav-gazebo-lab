#!/usr/bin/env bash
# Phase 1 batch sweep -- runs 11 trial configurations back-to-back on GPU.
# Each run = 500 honest + 500 byzantine trials (~5-8 min on RTX 3090/4090).
# Total wall time: ~60-90 min. Total cost @ $0.30/hr: ~$0.30-0.50.
#
# All CSVs land in workspaces/phase1-sweep/<variant>.csv .

set -euo pipefail

OUT_DIR=/workspace/uav-gazebo-lab/workspaces/phase1-sweep
DATASET=/workspace/uav-gazebo-lab/datasets/staged/zurich-z16
SCRIPT=/workspace/uav-gazebo-lab/scripts/phase1-poo-trials.py
mkdir -p "$OUT_DIR"

run_variant() {
    local name="$1"; shift
    local out="$OUT_DIR/$name.csv"
    if [[ -f "$out" ]]; then
        echo "[skip] $name (already exists)"; return
    fi
    echo ""
    echo "===================================================================="
    echo "=== $name ==="
    echo "===================================================================="
    python3 "$SCRIPT" --dataset "$DATASET" --out "$out" \
        --n-honest 500 --n-byzantine 500 --seed 42 "$@"
}

# 1-3. Perturbation envelope -- 3 grids from paper-faithful to extreme
run_variant baseline-paper       --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0
run_variant baseline-aggressive  --sun-shifts=-30,0,30 --blur-sigmas=0,2 --occl-fracs=0,0.10
run_variant baseline-extreme     --sun-shifts=-45,0,45 --blur-sigmas=0,4 --occl-fracs=0,0.20

# 4-6. K (Mode A descriptor count) sweep -- on baseline-paper conditions
run_variant k10  --k-modea=10  --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0
run_variant k20  --k-modea=20  --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0
run_variant k40  --k-modea=40  --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0

# 7-9. N (top-keypoints) sweep -- on baseline-paper conditions, K stays default 20
run_variant n25  --n-top=25  --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0
run_variant n50  --n-top=50  --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0
run_variant n100 --n-top=100 --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0

# 10-11. Lowe ratio tau sweep -- on baseline-paper conditions
run_variant tau06 --lowe-tau=0.6 --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0
run_variant tau08 --lowe-tau=0.8 --sun-shifts=-15,0,15 --blur-sigmas=0,1 --occl-fracs=0

echo ""
echo "===================================================================="
echo "BATCH DONE -- 11 CSVs in $OUT_DIR"
ls -lh "$OUT_DIR"
