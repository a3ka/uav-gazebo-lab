#!/usr/bin/env bash
# Phase 6 Tier A minimum-viable trial.
#
# Setup:  N=5 PX4 SITL instances in ONE headless Gazebo Harmonic world,
#         3 are anchors (0,1,2), 2 are followers (3,4).
#         px4_position_bridge_node per UAV converts
#         /px4_<i>/fmu/out/vehicle_local_position -> /uav<i>/noisy_pose.
#         Phase 4 anchor/follower protocol runs on top unchanged.
# Attrition: at t=20s, SIGKILL anchor 0's PX4 process group.
# Pass:  follower 3 (initially attached to anchor 0) emits a
#        /phase4/timing/f3 sample with switching_time < 15 s.
#
# This is a "does it work" demo, NOT a statistical campaign -- shows
# Phase 4 protocol still functions on top of real PX4 flight dynamics.
# Full Tier A campaign (15-20 UAV, 22.5% attrition, 30 trials) is
# follow-up work; see docs/results/phase-6.md.

set -o pipefail

declare -a PIDS=()
declare -a PX4_PIDS=()
cleanup() {
    for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
    for pid in "${PX4_PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
    pkill -u "$(whoami)" -f 'uav_swarm_nodes\|MicroXRCEAgent\|bin/px4\|gz sim' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
PX4_DIR=/workspace/PX4-Autopilot
export GZ_SIM_RESOURCE_PATH="$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}"

echo "=== Phase 6 Tier A trial (N=5 PX4 + Phase 4 on top) ==="

echo "[1/6] MicroXRCEAgent + gz sim..."
MicroXRCEAgent udp4 -p 8888 > /tmp/p6a-agent.log 2>&1 &
PIDS+=("$!")
sleep 0.5
gz sim -s -r "$PX4_DIR/Tools/simulation/gz/worlds/default.sdf" \
    > /tmp/p6a-gz.log 2>&1 &
PIDS+=("$!")
sleep 4

echo "[2/6] Launch 5 PX4 instances (instances 0..4 at 10m spacing)..."
N=5
for i in $(seq 0 $((N-1))); do
    POSE_X=$(awk -v i=$i 'BEGIN{print i*10}')
    PX4_GZ_STANDALONE=1 PX4_GZ_MODEL_POSE="${POSE_X},0,0.1" \
    PX4_SYS_AUTOSTART=4001 PX4_GZ_MODEL=x500 \
        setsid "$PX4_DIR/build/px4_sitl_default/bin/px4" \
        -i $i -d > /tmp/p6a-px4_${i}.log 2>&1 &
    PX4_PIDS+=("$!")
    sleep 0.3
done
sleep 8   # wait for all PX4 to come up + /fmu/out/* discoverable

echo "[3/6] Launch 5 px4_position_bridge_nodes..."
for i in $(seq 0 $((N-1))); do
    ros2 run uav_swarm_nodes px4_position_bridge_node --ros-args \
        -r __node:=bridge_${i} -p uav_id:=$i -p px4_id:=$i \
        > /tmp/p6a-bridge_${i}.log 2>&1 &
    PIDS+=("$!")
done
sleep 2

echo "[4/6] Launch 3 anchor_node + 2 follower_node (Phase 4 protocol)..."
for i in 0 1 2; do
    POS_X=$(awk -v i=$i 'BEGIN{print i*10}')
    setsid ros2 run uav_swarm_nodes anchor_node --ros-args \
        -r __node:=anchor_${i} -p anchor_id:=$i \
        -p "initial_position:=[${POS_X}.0, 0.0, 0.0]" \
        -p target_capacity:=2 -p reputation:=0.8 -p publish_rate:=5.0 \
        > /tmp/p6a-anchor_${i}.log 2>&1 &
    PIDS+=("$!")
done
for i in 3 4; do
    ros2 run uav_swarm_nodes follower_node --ros-args \
        -r __node:=follower_${i} -p follower_id:=$i \
        -p initial_anchor_id:=$((i - 3)) \
        -p "known_anchor_ids:=[0, 1, 2]" -p t_timeout:=5.0 \
        > /tmp/p6a-follower_${i}.log 2>&1 &
    PIDS+=("$!")
done
sleep 6   # steady state

echo "[5/6] Steady state check..."
ros2 topic list | grep -E "/(uav|anchor|reassign)" | sort -u > /tmp/p6a-topics.log
echo "  Discovered topics:"
head -10 /tmp/p6a-topics.log | sed 's/^/    /'

echo ""
echo "[6/6] At t=20s sim: SIGKILL anchor 0 (= PX4 instance 0)..."
T_DEATH=$(date +%s.%N)
kill -KILL -- -"${PX4_PIDS[0]}" 2>/dev/null
pkill -f 'uav_swarm_nodes.anchor_node.*anchor_id:=0' 2>/dev/null
echo "  death at $T_DEATH"

# Wait for follower 3 (was attached to anchor 0) to publish switching time
echo "  listening on /phase4/timing/f3 for up to 20s..."
TIMING=$(timeout 20 ros2 topic echo --once /phase4/timing/f3 std_msgs/msg/Float64 2>&1 || true)
echo "$TIMING" | sed 's/^/    /' | head -4
SWITCH=$(grep '^data:' <<<"$TIMING" | awk '{print $2}' | head -1)

if [[ -z "$SWITCH" ]]; then
    echo ""
    echo "TIER A TRIAL FAIL: no /phase4/timing/f3 from follower 3"
    tail -10 /tmp/p6a-follower_3.log
    exit 1
fi

if awk -v t="$SWITCH" 'BEGIN{exit !(t < 15.0)}'; then
    echo ""
    echo "TIER A TRIAL OK  switching_time=${SWITCH}s < 15s"
else
    echo ""
    echo "TIER A TRIAL FAIL  switching_time=${SWITCH}s >= 15s"
    exit 1
fi
