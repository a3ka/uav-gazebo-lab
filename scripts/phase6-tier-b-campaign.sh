#!/usr/bin/env bash
# Phase 6 Tier B production campaign — 200-UAV Python MC sweep.
#
# Defaults: N=200 (M=10 anchors, 190 followers), 3 anchors killed
# staggered every 30s during a 120s mission, 10 trials.
# Wall time at JOBS=1: ~25 min;  at JOBS=2: ~13 min.
#
# Output:
#   workspaces/phase6-tier-b-prod/results.csv
#   workspaces/phase6-tier-b-prod/manifest.json

set -o pipefail

RUN_ID="${RUN_ID:-phase6-tier-b-prod}"
TRIALS="${TRIALS:-10}"
N_UAVS="${N_UAVS:-200}"
M_ANCHORS="${M_ANCHORS:-10}"
REGION_M="${REGION_M:-400.0}"
N_VICTIMS="${N_VICTIMS:-3}"
T_FIRST="${T_FIRST:-30.0}"
T_STEP="${T_STEP:-30.0}"
T_WARMUP="${T_WARMUP:-8.0}"
T_MISSION="${T_MISSION:-120.0}"
JOBS="${JOBS:-1}"

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

cd /workspace/uav-gazebo-lab

echo "###################################################"
echo "### Phase 6 Tier B (Python MC, no Gazebo)"
echo "### N=$N_UAVS M=$M_ANCHORS victims=$N_VICTIMS"
echo "### trials=$TRIALS  jobs=$JOBS"
echo "###################################################"
date -u

python3 scripts/phase6-tier-b-sweep.py \
    --trials "$TRIALS" \
    --n-uavs "$N_UAVS" --m-anchors "$M_ANCHORS" \
    --region-m "$REGION_M" \
    --n-victims "$N_VICTIMS" \
    --t-first-event-s "$T_FIRST" --t-step-s "$T_STEP" \
    --t-warmup-s "$T_WARMUP" --t-mission-s "$T_MISSION" \
    --run-id "$RUN_ID" --jobs "$JOBS"

echo ""
echo "=== Summary ==="
python3 << PYEOF
import csv, json, statistics
with open("workspaces/$RUN_ID/results.csv") as f:
    rows = list(csv.DictReader(f))
trials = len(rows)
passed = sum(1 for r in rows if r['pass_trial'].lower() == 'true')
survived = sum(1 for r in rows if r['mission_survived'].lower() == 'true')
def fnum(s):
    try: return float(s) if s not in ('','None') else None
    except: return None
rebal_max = [fnum(r['rebal_latency_max']) for r in rows]
oc_max = [fnum(r['over_cap_interval_max']) for r in rows]
rebal_max = [x for x in rebal_max if x is not None]
oc_max = [x for x in oc_max if x is not None]
summary = {
  'trials': trials,
  'pass_trial': passed,
  'mission_survived': survived,
  'rebal_latency_max_median': round(statistics.median(rebal_max), 3) if rebal_max else None,
  'rebal_latency_max_max':    round(max(rebal_max), 3) if rebal_max else None,
  'over_cap_interval_max_median': round(statistics.median(oc_max), 3) if oc_max else None,
  'over_cap_interval_max_max':    round(max(oc_max), 3) if oc_max else None,
}
print(json.dumps(summary, indent=2))
with open("workspaces/$RUN_ID/analysis.json", 'w') as f:
    json.dump({'summary': summary, 'rows': rows}, f, indent=2)
PYEOF

date -u
ls -la "workspaces/$RUN_ID/"
