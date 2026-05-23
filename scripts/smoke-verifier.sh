#!/usr/bin/env bash
# Phase 2 task 2.2 smoke -- exercise verifier_node end-to-end.
#
# Setup:
#   - verifier_node (id=0) running in uav-lab:gpu container (torch+lightglue
#     present; falls back to CPU inference when no NVIDIA driver)
#   - inject one honest-style SignedObservation (target=1) with random
#     256-D descriptors near verifier's position
#   - inject NoisyPose so verifier sees itself in range
# Pass: verifier publishes a ReputationUpdate on /reputation/update/u1
# (whether VERIFIED or UNVERIFIED is fine for smoke -- we're testing
# the plumbing, not the verdict accuracy; that was Phase 1's job).

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
    pkill -u "$(whoami)" -f 'uav_swarm_nodes\|smoke_verifier' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

echo "=== Phase 2 verifier_node smoke ==="

echo "[1/4] Launch verifier_node (id=0, lazy-loads SuperPoint on first verify)..."
ros2 run uav_swarm_nodes verifier_node \
    --ros-args -p verifier_id:=0 -p position_topic:=/uav0/noisy_pose \
               -p dataset_dir:=/datasets/zurich-z16 \
               -p r_verify:=500.0 -p t_verify:=0.30 \
    > /tmp/verifier.log 2>&1 &
VERIFIER_PID=$!
PIDS+=("$VERIFIER_PID")
sleep 4
if ! kill -0 "$VERIFIER_PID" 2>/dev/null; then
    echo "FAIL: verifier_node died on startup:"
    cat /tmp/verifier.log
    exit 1
fi
echo "  ok -- verifier alive"

echo "[2/4] Inject mock SignedObservation (target=1) + NoisyPose for verifier..."
python3 - <<'PYEOF' > /tmp/injector.log 2>&1 &
import random, time
import rclpy
from rclpy.node import Node
from uav_swarm_msgs.msg import SignedObservation, NoisyPose

rclpy.init()
n = Node('smoke_injector')
pub_obs = n.create_publisher(SignedObservation, '/signed_observation', 10)
pub_pose = n.create_publisher(NoisyPose, '/uav0/noisy_pose', 10)
# Let DDS discover subscribers
for _ in range(20):
    rclpy.spin_once(n, timeout_sec=0.05)
    time.sleep(0.05)

# Mock observation: target=1, position (5,0,50), K=20 random descriptors (256-D)
obs = SignedObservation()
obs.timestamp = int(time.time() * 1_000_000)
obs.position.x, obs.position.y, obs.position.z = 5.0, 0.0, 50.0
obs.hash_sha256 = [0] * 32
obs.ransac_inlier_ratio = 0.85
obs.uav_id = 1
obs.signature_ed25519 = [0] * 64
random.seed(0)
obs.descriptors = [random.gauss(0.0, 0.1) for _ in range(20 * 256)]
pub_obs.publish(obs)
n.get_logger().info(f'published obs target_id=1 at (5,0,50)')

# Pose: verifier within r_verify (500 m) of obs
pose = NoisyPose()
pose.timestamp = int(time.time() * 1_000_000)
pose.uav_id = 0
pose.position.x, pose.position.y, pose.position.z = 10.0, 0.0, 50.0
pose.sigma = 1.0
for _ in range(5):
    pub_pose.publish(pose)
    rclpy.spin_once(n, timeout_sec=0.1)
    time.sleep(0.1)
n.get_logger().info('published 5 poses')

# Drain for 30 s so verifier's tick can pick up
for _ in range(60):
    rclpy.spin_once(n, timeout_sec=0.5)
n.destroy_node()
rclpy.shutdown()
PYEOF
INJ_PID=$!
PIDS+=("$INJ_PID")
sleep 2

echo "[3/4] Listening on /reputation/update/u1 for up to 60 s..."
OUT=$(timeout 60 ros2 topic echo --once /reputation/update/u1 uav_swarm_msgs/msg/ReputationUpdate 2>&1)
echo "$OUT"

echo ""
echo "[4/4] Check verifier emitted a verdict..."
if grep -qE "reporter_id: 0" <<<"$OUT" && grep -qE "target_id: 1" <<<"$OUT"; then
    echo "VERIFIER SMOKE OK -- ReputationUpdate published with reporter=0 target=1"
else
    echo "FAIL: no matching ReputationUpdate received"
    echo "--- verifier log tail ---"
    tail -30 /tmp/verifier.log
    echo "--- injector log tail ---"
    tail -10 /tmp/injector.log
    exit 1
fi
