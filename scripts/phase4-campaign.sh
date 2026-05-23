#!/usr/bin/env bash
# Phase 4 production campaign — runs the full failover sweep.
#
# Defaults: S1, S2, S3, S5 (S4 deferred — needs CAP_NET_ADMIN for
# iptables partial-partition rule) × 30 trials × 10 followers per
# trial. Each trial wall ~30 s; total at JOBS=1 ≈ 60 min,
# at JOBS=4 ≈ 15 min.
#
# Output:
#   workspaces/phase4-prod/results.csv      (one row per follower)
#   workspaces/phase4-prod/manifest.json
#   workspaces/phase4-prod/analysis.json
#   workspaces/phase4-prod/switching_distributions.png
#
# Runs inside the uav-lab:cpu container; see vast-bootstrap.sh for the
# host-side launcher.

set -o pipefail

RUN_ID="${RUN_ID:-phase4-prod}"
SCENARIOS_VAR="${SCENARIOS:-S1 S2 S3 S5}"
TRIALS="${TRIALS:-30}"
N_ANCHORS="${N_ANCHORS:-3}"
N_FOLLOWERS="${N_FOLLOWERS:-10}"
T_STEADY="${T_STEADY:-5.0}"
T_PASS_BUDGET="${T_PASS_BUDGET:-10.0}"
T_TIMEOUT="${T_TIMEOUT:-5.0}"
JOBS="${JOBS:-1}"

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

cd /workspace/uav-gazebo-lab

echo "###################################################"
echo "### Phase 4 production campaign"
echo "### run_id     = $RUN_ID"
echo "### scenarios  = $SCENARIOS_VAR"
echo "### trials/sc  = $TRIALS"
echo "### anchors    = $N_ANCHORS"
echo "### followers  = $N_FOLLOWERS"
echo "### t_steady   = $T_STEADY s"
echo "### budget     = $T_PASS_BUDGET s (post-watchdog)"
echo "### t_timeout  = $T_TIMEOUT s (watchdog silence)"
echo "### jobs       = $JOBS"
echo "###################################################"
date -u

python3 scripts/phase4-batch-sweep.py \
    --scenarios $SCENARIOS_VAR \
    --trials-per-scenario "$TRIALS" \
    --n-anchors "$N_ANCHORS" --n-followers "$N_FOLLOWERS" \
    --t-steady-s "$T_STEADY" \
    --t-pass-budget-s "$T_PASS_BUDGET" \
    --t-timeout-s "$T_TIMEOUT" \
    --run-id "$RUN_ID" \
    --jobs "$JOBS"

echo ""
echo "###################################################"
echo "### Analyzing sweep"
echo "###################################################"
python3 scripts/phase4-analyze.py \
    --csv "workspaces/$RUN_ID/results.csv" \
    --out "workspaces/$RUN_ID/analysis.json" \
    --plot "workspaces/$RUN_ID/switching_distributions.png"

echo ""
echo "###################################################"
echo "### Phase 4 campaign DONE"
echo "###################################################"
date -u
ls -la "workspaces/$RUN_ID/"
