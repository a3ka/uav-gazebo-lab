#!/usr/bin/env bash
# Phase 3 task 3.3 smoke -- factor_graph_node end-to-end.
#
# Two subtests:
#   A. Anchor self-prior keeps estimate pinned: launch uav_id=10 as
#      anchor at (0,0,50), wait for EstimatedPose, assert |est - init|
#      under 5 m.
#   B. Follower converges from UWB + reputation prior: launch uav=20
#      as anchor at (0,0,50) AND uav=21 as follower with init_pos
#      (5,0,50) but truth (10,0,50). Inject DistilledState for 20
#      (anchor at (0,0,50), R=1.0) AND UwbRangeMeasurement
#      (sender=20 receiver=21, range=10 m). Expect 21's estimate
#      converges towards (10,0,50) (radial error < 3 m).
#
# Each subtest 10 s + 3 s settle.

set -o pipefail   # not -e (grep returns 1 on empty); not -u (ROS2 setup.bash touches unset vars)

CLEAN_DONE=0
declare -a PIDS=()
cleanup() {
    [[ "$CLEAN_DONE" -eq 1 ]] && return 0
    CLEAN_DONE=1
    echo ""
    echo "--- cleanup ---"
    for pid in "${PIDS[@]:-}"; do
        [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
    done
    pkill -u "$(whoami)" -f 'factor_graph_node\|smoke_fg' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

echo "=== Phase 3 factor_graph_node smoke ==="

#
# Subtest A: anchor self-prior
#
echo ""
echo "--- subtest A: anchor self-prior ---"
ros2 run uav_swarm_nodes factor_graph_node \
    --ros-args -p uav_id:=10 -p is_anchor:=true \
               -p 'initial_position:=[0.0, 0.0, 50.0]' \
    > /tmp/fg_anchor.log 2>&1 &
PIDS+=("$!")
sleep 6  # gtsam lazy-load on first callback; we need a tick to fire

rm -f /tmp/fg_a_out
( timeout 8 ros2 topic echo --once /estimate/u10/pose \
    uav_swarm_msgs/msg/EstimatedPose > /tmp/fg_a_out 2>&1 ) || true
echo "received:"
cat /tmp/fg_a_out

# Pull x/y/z out -- accept inline or block yaml
X=$(grep -A1 '^position:' /tmp/fg_a_out | grep '  x:' | head -1 | awk '{print $2}')
Y=$(grep -A2 '^position:' /tmp/fg_a_out | grep '  y:' | head -1 | awk '{print $2}')
Z=$(grep -A3 '^position:' /tmp/fg_a_out | grep '  z:' | head -1 | awk '{print $2}')

if [[ -z "$X" || -z "$Y" || -z "$Z" ]]; then
    echo "FAIL: no estimate received"
    tail -15 /tmp/fg_anchor.log; exit 1
fi

if awk -v x="$X" -v y="$Y" -v z="$Z" 'BEGIN{
    r = sqrt(x*x + y*y + (z-50)*(z-50))
    if (r < 5) { print "  PASS  anchor estimate at (" x "," y "," z ") within 5m of init"; exit 0 }
    else      { print "  FAIL  anchor estimate at (" x "," y "," z ") drifted r=" r "m"; exit 1 }
}'; then
    : # passed
else
    exit 1
fi

# Clean before subtest B
pkill -u "$(whoami)" -f 'factor_graph_node' 2>/dev/null || true
sleep 2

#
# Subtest B: follower converges via UWB + reputation prior
#
echo ""
echo "--- subtest B: follower converges via UWB + reputation prior ---"
# anchor at (0,0,50)
ros2 run uav_swarm_nodes factor_graph_node \
    --ros-args -p uav_id:=20 -p is_anchor:=true \
               -p 'initial_position:=[0.0, 0.0, 50.0]' \
    > /tmp/fg_anchor20.log 2>&1 &
PIDS+=("$!")
# follower at (5,0,50) initial (truth = (10,0,50) -- 5m off)
ros2 run uav_swarm_nodes factor_graph_node \
    --ros-args -p uav_id:=21 -p is_anchor:=false \
               -p 'initial_position:=[5.0, 0.0, 50.0]' \
    > /tmp/fg_follower21.log 2>&1 &
PIDS+=("$!")
sleep 5

python3 - <<'PYEOF' > /tmp/fg_inject.log 2>&1 &
import time, rclpy
from rclpy.node import Node
from uav_swarm_msgs.msg import DistilledState, UwbRangeMeasurement

rclpy.init()
n = Node('smoke_fg_inject')
ps = n.create_publisher(DistilledState, '/distilled_state', 10)
pr = n.create_publisher(UwbRangeMeasurement, '/uwb/range', 50)
for _ in range(20): rclpy.spin_once(n, timeout_sec=0.05); time.sleep(0.05)

def state(uid, x, R):
    m = DistilledState(); m.timestamp = int(time.time()*1e6)
    m.position.x = x; m.position.y = 0.0; m.position.z = 50.0
    m.position_covariance = [4.0,0.0,0.0,4.0,0.0,1.0]
    m.reputation = R; m.uav_id = uid
    return m

def rng(sender, receiver, r):
    m = UwbRangeMeasurement(); m.timestamp = int(time.time()*1e6)
    m.sender_id = sender; m.receiver_id = receiver
    m.range_m = float(r); m.sigma_m = 0.1
    return m

# spam for 8 seconds so iSAM2 settles
for i in range(80):
    ps.publish(state(20, 0.0, 1.0))
    ps.publish(state(21, 10.0, 0.7))    # follower's own broadcast (R 0.7)
    pr.publish(rng(20, 21, 10.0))       # UWB measurement: 10m from anchor
    rclpy.spin_once(n, timeout_sec=0.05); time.sleep(0.1)

n.destroy_node(); rclpy.shutdown()
PYEOF
PIDS+=("$!")
sleep 11

rm -f /tmp/fg_b_out
( timeout 5 ros2 topic echo --once /estimate/u21/pose \
    uav_swarm_msgs/msg/EstimatedPose > /tmp/fg_b_out 2>&1 ) || true
echo "received (follower 21):"
cat /tmp/fg_b_out

X=$(grep -A1 '^position:' /tmp/fg_b_out | grep '  x:' | head -1 | awk '{print $2}')
Y=$(grep -A2 '^position:' /tmp/fg_b_out | grep '  y:' | head -1 | awk '{print $2}')

if [[ -z "$X" || -z "$Y" ]]; then
    echo "FAIL: no follower estimate received"
    tail -15 /tmp/fg_follower21.log; exit 1
fi

awk -v x="$X" -v y="$Y" 'BEGIN{
    r = sqrt((x-10)*(x-10) + y*y)
    if (r < 3) { print "  PASS  follower converged to (" x "," y ") within 3m of truth (10,0)"; exit 0 }
    else      { print "  FAIL  follower at (" x "," y ") radial error " r "m from truth (10,0)"; exit 1 }
}'

echo ""
echo "FG SMOKE OK (2/2 subtests pass)"
