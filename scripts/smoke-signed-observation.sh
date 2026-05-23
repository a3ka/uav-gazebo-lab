#!/usr/bin/env bash
# Phase 2 task 2.5 smoke -- signed_observation_publisher_node.
#
# Two subtests in parallel (different uav_ids):
#   A. honest publisher (uav_id=11) emits OBS with descriptors from
#      tile at its own position
#   B. byzantine publisher (uav_id=12) emits OBS with descriptors from
#      tile ~3000 m away (but claims own position)
# Inject pose for both, wait ~3 s (period=2 s so 1+ obs per publisher).
# Verify both publish on /signed_observation; expect:
#   - both have desc_floats == 20 * 256 = 5120
#   - byzantine OBS claims own position but descriptors mismatch verifier
#     check (verifier_node smoke-tested separately in task 2.2)

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
    pkill -u "$(whoami)" -f 'uav_swarm_nodes\|smoke_obs' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

echo "=== Phase 2 signed_observation_publisher smoke ==="

echo "[1/4] Launch honest publisher (uav_id=11) + byzantine (uav_id=12)..."
ros2 run uav_swarm_nodes signed_observation_publisher_node \
    --ros-args -p uav_id:=11 -p mode:=honest -p publish_period_s:=2.0 \
               -p position_topic:=/uav11/noisy_pose \
               -p dataset_dir:=/datasets/zurich-z16 \
    > /tmp/obs_honest.log 2>&1 &
PIDS+=("$!")
ros2 run uav_swarm_nodes signed_observation_publisher_node \
    --ros-args -p uav_id:=12 -p mode:=byzantine -p publish_period_s:=2.0 \
               -p position_topic:=/uav12/noisy_pose \
               -p dataset_dir:=/datasets/zurich-z16 \
               -p byzantine_offset_x:=3000.0 \
    > /tmp/obs_byz.log 2>&1 &
PIDS+=("$!")
sleep 4

echo "[2/4] Inject pose for both UAVs..."
python3 - <<'PYEOF' > /tmp/pose_inject.log 2>&1 &
import time
import rclpy
from rclpy.node import Node
from uav_swarm_msgs.msg import NoisyPose

rclpy.init()
n = Node('smoke_pose')
p11 = n.create_publisher(NoisyPose, '/uav11/noisy_pose', 10)
p12 = n.create_publisher(NoisyPose, '/uav12/noisy_pose', 10)
for _ in range(20): rclpy.spin_once(n, timeout_sec=0.05); time.sleep(0.05)

def make(uid, x):
    m = NoisyPose()
    m.timestamp = int(time.time() * 1_000_000)
    m.uav_id = uid; m.position.x = float(x); m.position.y = 0.0; m.position.z = 50.0
    m.sigma = 1.0
    return m

for _ in range(60):
    p11.publish(make(11, 5.0))
    p12.publish(make(12, 7.0))
    rclpy.spin_once(n, timeout_sec=0.05); time.sleep(0.1)
n.destroy_node(); rclpy.shutdown()
PYEOF
PIDS+=("$!")

echo "[3/4] Listen for SignedObservation messages (collect 4 over ~6 s)..."
rm -f /tmp/obs_capture.log
# Default yaml-style output -- much easier to grep for uav_id than CSV
# of 5161 fields (5120 descriptor floats + 41 other fields).
# --no-arr suppresses the giant descriptor array from output.
( timeout 10 ros2 topic echo --no-arr /signed_observation \
    uav_swarm_msgs/msg/SignedObservation > /tmp/obs_capture.log 2>&1 ) &
CAP_PID=$!
PIDS+=("$CAP_PID")
sleep 8
kill "$CAP_PID" 2>/dev/null || true
wait "$CAP_PID" 2>/dev/null || true

HONEST_COUNT=$(grep -c '^uav_id: 11$' /tmp/obs_capture.log || true)
BYZ_COUNT=$(grep -c '^uav_id: 12$' /tmp/obs_capture.log || true)
echo "  honest (uav=11) messages captured: $HONEST_COUNT"
echo "  byzantine (uav=12) messages captured: $BYZ_COUNT"

echo ""
echo "[4/4] Verdict..."
if [[ "$HONEST_COUNT" -ge 1 ]] && [[ "$BYZ_COUNT" -ge 1 ]]; then
    echo "OBS PUBLISHER OK -- both modes emitting"
else
    echo "FAIL: honest=$HONEST_COUNT byzantine=$BYZ_COUNT (expected each >= 1)"
    echo "--- honest log ---"; tail -8 /tmp/obs_honest.log
    echo "--- byz log ---"; tail -8 /tmp/obs_byz.log
    exit 1
fi
