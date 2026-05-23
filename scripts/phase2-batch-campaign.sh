#!/usr/bin/env bash
# Phase 2 production campaign -- runs the full 6-cell sweep on the
# vast.ai GPU instance. 30 trials total (5 per cell), ~300 s each,
# total wall ~2.5 hr at paper-faithful publish_period_s=45.
#
# Output: workspaces/phase2-batch/m{M}f{f}-trial{N}.{exclusions,rep_events}.csv
#
# Re-runnable: skips trials whose exclusions.csv already exists.

set -eo pipefail

OUT_DIR=/workspace/uav-gazebo-lab/workspaces/phase2-batch
DATASET=/workspace/uav-gazebo-lab/datasets/staged/zurich-z16
DURATION=300
TRIALS_PER_CELL=5
PERIOD_S=45    # paper-faithful nu_verify^-1
mkdir -p "$OUT_DIR"

# (M, f, n_honest, n_byzantine)
CELLS=(
    "3 1 6 1"
    "3 2 5 2"
    "5 2 6 2"
    "5 3 5 3"
    "7 3 6 3"
    "7 4 5 4"
)

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

cd /workspace/uav-gazebo-lab

CELL_IDX=0
for cell in "${CELLS[@]}"; do
    CELL_IDX=$((CELL_IDX + 1))
    read -r M F NH NB <<<"$cell"
    echo ""
    echo "###################################################"
    echo "### Cell $CELL_IDX/${#CELLS[@]}: M=$M f=$F  (N_honest=$NH N_byz=$NB)"
    echo "###################################################"
    for TRIAL in $(seq 0 $((TRIALS_PER_CELL - 1))); do
        TAG="m${M}f${F}-trial${TRIAL}"
        OUT="$OUT_DIR/$TAG.exclusions.csv"
        if [[ -f "$OUT" ]]; then
            echo "  [skip] $TAG already done"
            continue
        fi
        echo "  --- $TAG ---"
        python3 scripts/phase2-scenario-runner.py \
            --n-honest "$NH" --n-byzantine "$NB" --m-quorum "$M" \
            --duration-s "$DURATION" \
            --dataset-dir "$DATASET" \
            --output "$OUT_DIR/$TAG.csv" 2>&1 | tail -12
        # Clean lingering processes before next trial (each spawn=4N
        # ros2 procs that should self-cleanup via the trap, but be safe)
        pkill -u "$(whoami)" -f 'uav_swarm_nodes' 2>/dev/null || true
        sleep 5
    done
done

echo ""
echo "###################################################"
echo "### BATCH COMPLETE -- $(ls "$OUT_DIR"/*.exclusions.csv 2>/dev/null | wc -l) trials done"
echo "###################################################"
ls -lh "$OUT_DIR"

echo ""
echo "Aggregate analysis (run from local after scp-ing CSVs):"
echo "  python3 scripts/phase2-analyze.py \\"
echo "    --csv workspaces/phase2-batch/*.exclusions.csv \\"
echo "    --n-honest <NH> --n-byzantine <NB> --nu-verify-s $PERIOD_S"
echo ""
echo "(Per-cell analysis needs per-cell n_honest/n_byzantine; analyzer"
echo "currently takes one classification at a time -- iterate per cell)"
