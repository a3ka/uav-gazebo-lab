#!/usr/bin/env bash
# Phase 5 production campaign — GNSS spoofing detection sweep.
#
# Defaults: N=20 UAVs (region 200 m), F=2 spoofed per trial,
# 30 trials × ~12 s wall ≈ 6 min total at JOBS=1, ~3 min at JOBS=2.
#
# N=20 (not paper's N=50) — see docs/results/phase-5.md scope-limit
# section. The central Python detector + per-pair UWB publishers DDS-
# overload at N=50: detection rate drops to ~50% and false positives
# appear, even with multi_uwb_simulator + QoS depth 2000 + greedy
# peeling. Algorithm itself is sound; scaling to N=50 needs C-level
# detector implementation deferred to Phase 7 integration.
#
# Output:
#   workspaces/phase5-prod/results.csv      (one row per spoofed victim)
#   workspaces/phase5-prod/manifest.json
#   workspaces/phase5-prod/analysis.json
#   workspaces/phase5-prod/detect_dist.png

set -o pipefail

RUN_ID="${RUN_ID:-phase5-prod}"
TRIALS="${TRIALS:-30}"
N_UAVS="${N_UAVS:-20}"
N_SPOOFED="${N_SPOOFED:-2}"
REGION_M="${REGION_M:-200.0}"
T_STEADY="${T_STEADY:-4.0}"
T_OBSERVE="${T_OBSERVE:-8.0}"
WINDOW="${WINDOW:-3.0}"
M_SUSPECT="${M_SUSPECT:-3}"
SPOOF_OFFSET="${SPOOF_OFFSET:-120.0}"
T_SPOOF_M="${T_SPOOF_M:-20.0}"
T_PASS_BUDGET="${T_PASS_BUDGET:-5.0}"
JOBS="${JOBS:-1}"

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
cd /workspace/uav-gazebo-lab

echo "###################################################"
echo "### Phase 5 production campaign"
echo "### run_id    = $RUN_ID"
echo "### trials    = $TRIALS"
echo "### N         = $N_UAVS (F=$N_SPOOFED in region $REGION_M m)"
echo "### window    = $WINDOW s   m_suspect = $M_SUSPECT"
echo "### spoof off = $SPOOF_OFFSET m,  T_spoof = $T_SPOOF_M m"
echo "### budget    = $T_PASS_BUDGET s (paper Pillar 5)"
echo "### jobs      = $JOBS"
echo "###################################################"
date -u

python3 scripts/phase5-batch-sweep.py \
    --trials "$TRIALS" \
    --n-uavs "$N_UAVS" --n-spoofed "$N_SPOOFED" --region-m "$REGION_M" \
    --t-steady-s "$T_STEADY" --t-observe-s "$T_OBSERVE" \
    --window-s "$WINDOW" --m-suspect "$M_SUSPECT" \
    --spoof-offset-m "$SPOOF_OFFSET" --t-spoof-m "$T_SPOOF_M" \
    --t-pass-budget-s "$T_PASS_BUDGET" \
    --run-id "$RUN_ID" --jobs "$JOBS"

echo ""
echo "###################################################"
echo "### Analyzing sweep"
echo "###################################################"
python3 scripts/phase5-analyze.py \
    --csv "workspaces/$RUN_ID/results.csv" \
    --out "workspaces/$RUN_ID/analysis.json" \
    --plot "workspaces/$RUN_ID/detect_dist.png"

echo ""
echo "###################################################"
echo "### Phase 5 campaign DONE"
echo "###################################################"
date -u
ls -la "workspaces/$RUN_ID/"
