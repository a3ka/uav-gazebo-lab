#!/usr/bin/env bash
# Phase 3 task 3.4 smoke -- trn_anchor_node + factor_graph_node integration.
#
# Setup:
#   - trn_anchor_node uav_id=30, gt=(100,200,50), sigma_trn=2.0, period=1.0s
#   - factor_graph_node uav_id=30 as anchor, init at (95,205,55) (off truth)
# Verify:
#   A. /trn/fix publishes TrnAbsoluteFix near (100,200,50) within ~3*sigma
#   B. factor_graph_node EstimatedPose pulls TOWARDS (100,200,50)
#      from init (95,205,55) -- tight TRN prior should dominate over
#      wide anchor self-prior

set -o pipefail

CLEAN_DONE=0
declare -a PIDS=()
cleanup() {
    [[ "$CLEAN_DONE" -eq 1 ]] && return 0
    CLEAN_DONE=1
    for pid in "${PIDS[@]:-}"; do
        [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
    done
    pkill -u "$(whoami)" -f 'trn_anchor_node\|factor_graph_node\|smoke_trn' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

echo "=== Phase 3 trn_anchor_node smoke ==="

echo "[1/3] Launch trn_anchor (uav=30, gt=100,200,50, sigma=2) + factor_graph (uav=30 anchor, init=95,205,55)..."
ros2 run uav_swarm_nodes trn_anchor_node \
    --ros-args -p uav_id:=30 \
               -p 'initial_position:=[100.0, 200.0, 50.0]' \
               -p trn_period_s:=1.0 -p sigma_trn_m:=2.0 -p seed:=42 \
    > /tmp/trn.log 2>&1 &
PIDS+=("$!")
ros2 run uav_swarm_nodes factor_graph_node \
    --ros-args -p uav_id:=30 -p is_anchor:=true \
               -p 'initial_position:=[95.0, 205.0, 55.0]' \
               -p anchor_self_sigma:=50.0 \
    > /tmp/fg_for_trn.log 2>&1 &
PIDS+=("$!")
sleep 8   # 5+ TRN fixes + factor-graph settling

echo "[2/3] Verify /trn/fix..."
rm -f /tmp/trn_capture
( timeout 4 ros2 topic echo --once /trn/fix \
    uav_swarm_msgs/msg/TrnAbsoluteFix > /tmp/trn_capture 2>&1 ) || true
echo "  /trn/fix sample:"
sed 's/^/    /' /tmp/trn_capture | head -10
TX=$(grep -A1 '^position:' /tmp/trn_capture | grep '  x:' | head -1 | awk '{print $2}')
TY=$(grep -A2 '^position:' /tmp/trn_capture | grep '  y:' | head -1 | awk '{print $2}')
if [[ -z "$TX" || -z "$TY" ]]; then
    echo "  FAIL: no /trn/fix received"; tail -10 /tmp/trn.log; exit 1
fi
awk -v x="$TX" -v y="$TY" 'BEGIN{
    r = sqrt((x-100)*(x-100) + (y-200)*(y-200))
    if (r < 10) { print "  PASS  TRN fix at (" x "," y ") within 10m of gt (100,200) (3*sigma=6m + slack)"; exit 0 }
    else        { print "  FAIL  TRN fix at (" x "," y ") radial " r "m from gt"; exit 1 }
}' || exit 1

echo ""
echo "[3/3] Verify factor_graph estimate pulls toward TRN fix..."
rm -f /tmp/fg_capture
( timeout 4 ros2 topic echo --once /estimate/u30/pose \
    uav_swarm_msgs/msg/EstimatedPose > /tmp/fg_capture 2>&1 ) || true
EX=$(grep -A1 '^position:' /tmp/fg_capture | grep '  x:' | head -1 | awk '{print $2}')
EY=$(grep -A2 '^position:' /tmp/fg_capture | grep '  y:' | head -1 | awk '{print $2}')
if [[ -z "$EX" || -z "$EY" ]]; then
    echo "  FAIL: no /estimate/u30/pose"; tail -10 /tmp/fg_for_trn.log; exit 1
fi
echo "  factor_graph est: ($EX, $EY)"
awk -v x="$EX" -v y="$EY" 'BEGIN{
    # init (95,205) is 7m from gt (100,200); pass if estimate within 10m of gt
    # (TRN fixes with sigma=2 should pull strongly)
    r = sqrt((x-100)*(x-100) + (y-200)*(y-200))
    if (r < 10) { print "  PASS  factor_graph at (" x "," y ") within 10m of gt (100,200)"; exit 0 }
    else        { print "  FAIL  factor_graph at (" x "," y ") radial " r "m from gt"; exit 1 }
}' || exit 1

echo ""
echo "TRN SMOKE OK (3/3 sub-checks pass)"
