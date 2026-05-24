#!/usr/bin/env bash
# Phase 8 production comparison campaign.
#
# Runs N trials of both protocols (ours = Phase 4 anchor death,
# baseline = Raft leader election) at matched scale (M=N anchors /
# raft members, 1 victim each). Compares median switching time.
#
# Env (optional):
#   TRIALS  default 10
#   N       default 5  (anchors / raft members)
#
# Output:
#   workspaces/phase8-prod/
#     ours-results.json  raft-results.json  comparison.json

set -o pipefail

TRIALS="${TRIALS:-10}"
N="${N:-5}"

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
cd /workspace/uav-gazebo-lab

RUN_DIR=workspaces/phase8-prod
mkdir -p "$RUN_DIR"

echo "###################################################"
echo "### Phase 8 — SwarmRaft baseline comparison"
echo "### trials=$TRIALS  N=$N"
echo "###################################################"
date -u

# --- Raft baseline trials -----------------------------------------------
RAFT_TIMES=()
for t in $(seq 0 $((TRIALS - 1))); do
    echo ""
    echo "--- RAFT trial $t/$((TRIALS - 1)) ---"
    bash scripts/phase8-raft-trial.sh "$N" 7 "$RUN_DIR/raft_t${t}.json" 2>&1 | tail -3
done

# --- Ours: Phase 4 S1 scenario (same N anchors, 1 killed) ---------------
OURS_TIMES=()
for t in $(seq 0 $((TRIALS - 1))); do
    echo ""
    echo "--- OURS trial $t/$((TRIALS - 1)) ---"
    python3 scripts/phase4-scenario-runner.py \
        --scenario S1 \
        --n-anchors "$N" --n-followers 1 --victim-anchor-id 0 \
        --t-steady-s 4 --t-pass-budget-s 10 --t-timeout-s 5 \
        --out "$RUN_DIR/ours_t${t}.json" \
        --log-dir "$RUN_DIR/ours_t${t}.logs" 2>&1 | tail -1
done

# --- Aggregate ---
python3 << PYEOF
import json, statistics, glob
from pathlib import Path
rd = Path("$RUN_DIR")

# Raft
raft_times = []
for fp in sorted(rd.glob("raft_t*.json")):
    m = json.loads(fp.read_text())
    if m.get('recovery_s') is not None:
        raft_times.append(float(m['recovery_s']))

# Ours: phase4 metrics.per_follower[0].switching_time_s
ours_times = []
for fp in sorted(rd.glob("ours_t*.json")):
    m = json.loads(fp.read_text())
    for r in m.get('per_follower', []):
        t = r.get('switching_time_s')
        if t is not None:
            ours_times.append(float(t))

def stats(xs):
    if not xs: return {'n': 0}
    xs2 = sorted(xs)
    return {
        'n': len(xs),
        'min': round(min(xs), 4),
        'median': round(xs2[len(xs2)//2], 4),
        'mean': round(statistics.fmean(xs), 4),
        'max': round(max(xs), 4),
    }
out = {
    'raft':  stats(raft_times),
    'ours':  stats(ours_times),
    'n_members': $N,
    'trials_per_protocol': $TRIALS,
}
(rd / 'comparison.json').write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
PYEOF

date -u
ls -la "$RUN_DIR/"
