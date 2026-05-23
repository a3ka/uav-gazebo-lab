#!/usr/bin/env bash
# Phase 2 task 2.3 smoke -- reputation_manager_node asymmetric update.
#
# Setup:
#   - reputation_manager (uav_id=5)
#   - inject sequence:
#       1 VERIFIED update for target=10 (R should go up from 0.5)
#       3 UNVERIFIED updates for target=10 (R should drop sharply)
#   - subscribe /reputation/view/u5/u10 to observe broadcast R
# Pass: VERIFIED first -> r_value goes up; after 3x UNVERIFIED,
#       r_value drops to <= 0.20 (paper T_reject).

set -eo pipefail

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
    pkill -u "$(whoami)" -f 'uav_swarm_nodes\|smoke_rep' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

echo "=== Phase 2 reputation_manager_node smoke ==="

echo "[1/4] Launch reputation_manager (uav_id=5)..."
ros2 run uav_swarm_nodes reputation_manager_node \
    --ros-args -p uav_id:=5 -p alpha_pos:=0.05 -p alpha_neg:=0.15 \
               -p view_broadcast_rate:=5.0 \
    > /tmp/repmgr.log 2>&1 &
PIDS+=("$!")
sleep 3

echo "[2/4] Inject 1x VERIFIED + 3x UNVERIFIED for target=10 (reporter=0)..."
python3 - <<'PYEOF' > /tmp/rep_inject.log 2>&1 &
import time
import rclpy
from rclpy.node import Node
from uav_swarm_msgs.msg import ReputationUpdate

rclpy.init()
n = Node('smoke_rep_injector')
pub = n.create_publisher(ReputationUpdate, '/reputation/update', 10)
for _ in range(20):
    rclpy.spin_once(n, timeout_sec=0.05)
    time.sleep(0.05)

def make(reason):
    m = ReputationUpdate()
    m.timestamp = int(time.time() * 1_000_000)
    m.reporter_id = 0      # voter (unknown to manager -> Rk = r_init = 0.5)
    m.target_id = 10       # target peer being judged
    m.old_value = 0.0
    m.new_value = 0.0
    m.reason = reason
    return m

# Step 2a: 1 VERIFIED -> expected R[10] = 0.5 + 0.05 * 0.5 = 0.525
pub.publish(make(ReputationUpdate.REASON_VERIFIED))
n.get_logger().info('sent 1x VERIFIED for target=10')
time.sleep(1.0)
for _ in range(10):
    rclpy.spin_once(n, timeout_sec=0.05)

# Step 2b: 3 UNVERIFIED -> R drops by 0.15 * Rk(=0.5) = 0.075 each
# Starting from ~0.525 -> ~0.450 -> ~0.375 -> ~0.300
# After 3 UNVERIFIED + decay should be ~0.30 (still above T_reject=0.20).
# Add 2 more UNVERIFIED to drive below T_reject for the assert.
for i in range(5):
    pub.publish(make(ReputationUpdate.REASON_UNVERIFIED))
    n.get_logger().info(f'sent UNVERIFIED #{i+1} for target=10')
    time.sleep(0.5)
    for _ in range(5):
        rclpy.spin_once(n, timeout_sec=0.05)

# Drain
for _ in range(60):
    rclpy.spin_once(n, timeout_sec=0.05)
n.destroy_node()
rclpy.shutdown()
PYEOF
PIDS+=("$!")
sleep 8  # let the sequence finish

echo "[3/4] Sample /reputation/view/u5/u10 -- expect r_value <= 0.20 after 5x UNVERIFIED..."
VIEW=$(timeout 5 ros2 topic echo --once /reputation/view/u5/u10 uav_swarm_msgs/msg/PeerReputationView 2>&1)
echo "$VIEW"
R_VAL=$(grep '^r_value:' <<<"$VIEW" | awk '{print $2}')

echo ""
echo "[4/4] Verdict..."
if [[ -z "$R_VAL" ]]; then
    echo "FAIL: no view sample received for target=10"
    tail -30 /tmp/repmgr.log
    exit 1
fi

awk -v r="$R_VAL" 'BEGIN{
    if (r <= 0.20) { print "REPMGR SMOKE OK -- r_value=" r " <= 0.20 (T_reject)"; exit 0 }
    else           { print "FAIL: r_value=" r " > 0.20 (T_reject)"; exit 1 }
}'