#!/usr/bin/env bash
# Phase 4 task 4.5 -- per-scenario smoke wrapping the scenario runner.
#
# Runs S1, S2, S3, S5 each as a single trial with 2 anchors + 1
# follower. S4 (partial partition) deferred (needs CAP_NET_ADMIN for
# iptables). For multi-follower / batch statistics, use
# phase4-batch-sweep.py via phase4-campaign.sh.
#
# Pass: every scenario's runner exits 0 (n_pass == n_total).

set -o pipefail

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

cd /workspace/uav-gazebo-lab

LOG_DIR=/tmp/p4-smoke-all
rm -rf "$LOG_DIR" && mkdir -p "$LOG_DIR"

OK_COUNT=0
FAIL_COUNT=0
echo "=== Phase 4 task 4.5 -- smoke all scenarios ==="
for SC in S1 S2 S3 S5; do
    OUT="$LOG_DIR/$SC.json"
    echo ""
    echo "--- $SC ---"
    if python3 scripts/phase4-scenario-runner.py \
        --scenario "$SC" --n-anchors 2 --n-followers 1 --victim-anchor-id 0 \
        --t-steady-s 4 --t-pass-budget-s 10 --t-timeout-s 5 \
        --out "$OUT" --log-dir "$LOG_DIR/${SC}_logs" 2>&1 | tail -1; then
        OK_COUNT=$((OK_COUNT + 1))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

echo ""
echo "=================================="
echo "Phase 4 smoke-all summary"
echo "=================================="
for SC in S1 S2 S3 S5; do
    if [[ -f "$LOG_DIR/$SC.json" ]]; then
        python3 -c "
import json
m = json.load(open('$LOG_DIR/$SC.json'))
t = m.get('switching_time_median_s')
n = m.get('n_pass'); tot = m.get('n_total')
print(f'  $SC: n_pass={n}/{tot}  median={t}s  (threshold {m[\"pass_threshold_s\"]}s)')
"
    else
        echo "  $SC: NO RESULT"
    fi
done

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    echo ""
    echo "SMOKE FAIL: $FAIL_COUNT/$((OK_COUNT + FAIL_COUNT)) scenarios failed"
    exit 1
fi
echo ""
echo "ALL FAILOVER SMOKES OK ($OK_COUNT/$((OK_COUNT + FAIL_COUNT)))"
