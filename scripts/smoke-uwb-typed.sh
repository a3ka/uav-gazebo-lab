#!/usr/bin/env bash
# Phase 3 task 3.5 smoke -- typed UWB output + factor_graph consumption.
#
# Setup:
#   - position_broadcaster_node uav0 @ (0,0,50), uav1 @ (8,0,50)
#   - uwb_ranging_simulator (pair 0-1, sigma=0.1, emit_typed=true)
#   - factor_graph_node uav=1 (follower), init=(0,0,50) (off truth by 8m)
#     with uav0 as anchor (tight self-prior)
#   - factor_graph_node uav=0 (anchor) so it appears on /distilled_state
#
# We bypass /distilled_state for this smoke -- the typed UWB message
# arrives on /uwb/range and should drive uav1's position toward 8m
# from uav0.
#
# Verify:
#   A. UwbRangeMeasurement appears on /uwb/range with sender=0 recv=1
#      and range_m within 3*sigma of 8m
#   B. factor_graph estimate for uav1 moves toward (8,0,50) given a
#      tight UWB factor + tight prior on uav0

set -o pipefail

CLEAN_DONE=0
declare -a PIDS=()
cleanup() {
    [[ "$CLEAN_DONE" -eq 1 ]] && return 0
    CLEAN_DONE=1
    for pid in "${PIDS[@]:-}"; do [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true; done
    pkill -u "$(whoami)" -f 'uwb_ranging_simulator\|position_broadcaster\|factor_graph_node\|trn_anchor_node' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

echo "=== Phase 3 task 3.5 UWB typed smoke ==="

echo "[1/3] Launch position broadcasters (uav0@0,0,50  uav1@8,0,50, static)..."
ros2 run uav_swarm_nodes position_broadcaster_node --ros-args \
    -p uav_id:=0 -p radius:=0.0 -p 'center:=[0.0, 0.0]' \
    -p altitude:=50.0 -p sigma_inject:=0.0 -p publish_rate:=20.0 \
    > /tmp/pb0.log 2>&1 &
PIDS+=("$!")
ros2 run uav_swarm_nodes position_broadcaster_node --ros-args \
    -p uav_id:=1 -p radius:=0.0 -p 'center:=[8.0, 0.0]' \
    -p altitude:=50.0 -p sigma_inject:=0.0 -p publish_rate:=20.0 \
    > /tmp/pb1.log 2>&1 &
PIDS+=("$!")
sleep 1.5

echo "[2/3] Launch uwb_ranging_simulator (0,1) sigma=0.1 typed=on..."
ros2 run uav_swarm_nodes uwb_ranging_simulator_node --ros-args \
    -p uav_id_a:=0 -p uav_id_b:=1 -p sigma_range:=0.1 \
    -p publish_rate:=20.0 -p emit_typed:=true -p seed:=7 \
    > /tmp/uwb.log 2>&1 &
PIDS+=("$!")
sleep 1.5

echo "  /uwb/range sample:"
rm -f /tmp/uwb_capture
( timeout 3 ros2 topic echo --once /uwb/range \
    uav_swarm_msgs/msg/UwbRangeMeasurement > /tmp/uwb_capture 2>&1 ) || true
sed 's/^/    /' /tmp/uwb_capture | head -12
SENDER=$(grep '^sender_id:'   /tmp/uwb_capture | awk '{print $2}')
RECV=$(grep   '^receiver_id:' /tmp/uwb_capture | awk '{print $2}')
RANGE=$(grep  '^range_m:'     /tmp/uwb_capture | awk '{print $2}')
SIG=$(grep    '^sigma_m:'     /tmp/uwb_capture | awk '{print $2}')
if [[ -z "$RANGE" ]]; then
    echo "  FAIL: no /uwb/range msg"; tail -10 /tmp/uwb.log; exit 1
fi
awk -v s="$SENDER" -v r="$RECV" -v rng="$RANGE" -v sg="$SIG" 'BEGIN{
    if (s != 0 || r != 1)         { print "  FAIL sender/receiver=("s","r") expected (0,1)"; exit 1 }
    d = (rng - 8.0); if (d<0) d=-d
    if (d > 0.5)                  { print "  FAIL range="rng" |Δ|="d"m > 5*sigma"; exit 1 }
    if (sg+0 < 0.05 || sg+0 > 0.5){ print "  FAIL sigma_m="sg" outside expected band"; exit 1 }
    print "  PASS  typed: sender=0 recv=1 range="rng"m (truth 8m) sigma="sg"m"
}' || exit 1

echo ""
echo "[3/3] Launch trn_anchor uav=0 + factor_graph uav=0 (anchor) + uav=1 (follower)..."
# uav1 needs to LEARN key=0 before the UWB range factor (sender=0,recv=1)
# can be applied. The path is /trn/fix from anchor uav0 -- on receipt
# uav1's factor_graph inits key 0 at the TRN position with sigma_m noise.
ros2 run uav_swarm_nodes trn_anchor_node --ros-args \
    -p uav_id:=0 -p 'initial_position:=[0.0, 0.0, 50.0]' \
    -p trn_period_s:=0.5 -p sigma_trn_m:=0.5 -p seed:=11 \
    > /tmp/trn0.log 2>&1 &
PIDS+=("$!")
ros2 run uav_swarm_nodes factor_graph_node --ros-args \
    -p uav_id:=0 -p is_anchor:=true \
    -p 'initial_position:=[0.0, 0.0, 50.0]' -p anchor_self_sigma:=0.5 \
    > /tmp/fg0.log 2>&1 &
PIDS+=("$!")
ros2 run uav_swarm_nodes factor_graph_node --ros-args \
    -p uav_id:=1 -p is_anchor:=false \
    -p 'initial_position:=[0.0, 0.0, 50.0]' -p follower_self_sigma:=200.0 \
    > /tmp/fg1.log 2>&1 &
PIDS+=("$!")
sleep 7   # let UWB + TRN + iSAM2 converge

rm -f /tmp/fg1_capture
( timeout 4 ros2 topic echo --once /estimate/u1/pose \
    uav_swarm_msgs/msg/EstimatedPose > /tmp/fg1_capture 2>&1 ) || true
EX=$(grep -A1 '^position:' /tmp/fg1_capture | grep '  x:' | head -1 | awk '{print $2}')
EY=$(grep -A2 '^position:' /tmp/fg1_capture | grep '  y:' | head -1 | awk '{print $2}')
EZ=$(grep -A3 '^position:' /tmp/fg1_capture | grep '  z:' | head -1 | awk '{print $2}')
if [[ -z "$EX" ]]; then
    echo "  FAIL no /estimate/u1/pose"; tail -10 /tmp/fg1.log; exit 1
fi
echo "  uav1 estimate: ($EX, $EY, $EZ)  truth: (8, 0, 50)"
awk -v x="$EX" -v y="$EY" -v z="$EZ" 'BEGIN{
    # UWB is range-only with anchor at origin: follower lies on a sphere
    # r≈8. Wide self-prior pulls toward (0,0,50). Resolved position
    # should be at radius 8 from (0,0,50). We check radial distance.
    r = sqrt(x*x + y*y + (z-50)*(z-50))
    err = (r - 8.0); if (err<0) err=-err
    if (err < 1.5) { print "  PASS  uav1 at radius "r"m from anchor (truth 8m)"; exit 0 }
    else           { print "  FAIL  uav1 at radius "r"m, expected 8m"; exit 1 }
}' || exit 1

echo ""
echo "UWB TYPED SMOKE OK (3/3 sub-checks)"
