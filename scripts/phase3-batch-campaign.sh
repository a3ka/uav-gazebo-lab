#!/usr/bin/env bash
# Phase 3 production campaign — runs the full CEP-vs-hops sweep.
#
# Defaults: k ∈ {0,1,2,3,5} × 200 trials = 1000 trials.
# Each trial: 20s warmup + 30s collection ≈ 50s wall.
# Single-process: ~14 hr.   With --jobs 4: ~3.5 hr.
#
# Output:
#   workspaces/phase3-prod/sweep.csv      (one row per trial)
#   workspaces/phase3-prod/manifest.json  (run config + completion %)
#   workspaces/phase3-prod/analysis.json  (after the analyzer)
#   workspaces/phase3-prod/cep_vs_hops.png
#
# Environment:
#   This script assumes it runs INSIDE the uav-lab:cpu (or :gpu) docker
#   container with /workspace/uav-gazebo-lab and /workspace/ros2_ws
#   mounted. The host-side launch wrapper is:
#
#     docker run --rm --net=host --ipc=host \
#       -v $PWD:/workspace/uav-gazebo-lab \
#       -v $PWD/../px4_msgs:/workspace/px4_msgs \
#       -v $PWD/../ros2_ws:/workspace/ros2_ws \
#       -w /workspace/uav-gazebo-lab \
#       uav-lab:cpu \
#       bash scripts/phase3-batch-campaign.sh
#
# Re-runnable: sweep.csv is OVERWRITTEN at startup; per-trial JSONs are
# cleaned up unless --keep-topologies is passed. To resume a partial
# run, use a different --run-id or remove the workspace dir first.

set -o pipefail

RUN_ID="${RUN_ID:-phase3-prod}"
K_LIST="${K_LIST:-0 1 2 3 5}"
TRIALS_PER_K="${TRIALS_PER_K:-200}"
WARMUP_S="${WARMUP_S:-20.0}"
TRIAL_S="${TRIAL_S:-30.0}"
SIGMA_UWB="${SIGMA_UWB:-0.1}"
SIGMA_TRN="${SIGMA_TRN:-5.0}"
TRN_PERIOD="${TRN_PERIOD:-10.0}"
JOBS="${JOBS:-1}"

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

cd /workspace/uav-gazebo-lab

echo "###################################################"
echo "### Phase 3 production campaign"
echo "### run_id     = $RUN_ID"
echo "### k_list     = $K_LIST"
echo "### trials/k   = $TRIALS_PER_K  (total = $((TRIALS_PER_K * $(echo $K_LIST | wc -w))))"
echo "### warmup_s   = $WARMUP_S"
echo "### trial_s    = $TRIAL_S"
echo "### sigma_uwb  = $SIGMA_UWB m"
echo "### sigma_trn  = $SIGMA_TRN m"
echo "### trn_period = $TRN_PERIOD s"
echo "### jobs       = $JOBS"
echo "###################################################"
date -u

python3 scripts/phase3-batch-sweep.py \
    --k-list $K_LIST \
    --trials-per-k "$TRIALS_PER_K" \
    --warmup-s "$WARMUP_S" \
    --trial-s "$TRIAL_S" \
    --sigma-uwb-m "$SIGMA_UWB" \
    --sigma-trn-m "$SIGMA_TRN" \
    --trn-period-s "$TRN_PERIOD" \
    --run-id "$RUN_ID" \
    --jobs "$JOBS"

echo ""
echo "###################################################"
echo "### Analyzing sweep"
echo "###################################################"

python3 scripts/phase3-analyze.py \
    --csv "workspaces/$RUN_ID/sweep.csv" \
    --out "workspaces/$RUN_ID/analysis.json" \
    --plot "workspaces/$RUN_ID/cep_vs_hops.png"

echo ""
echo "###################################################"
echo "### Phase 3 campaign DONE"
echo "###################################################"
date -u
ls -la "workspaces/$RUN_ID/"
