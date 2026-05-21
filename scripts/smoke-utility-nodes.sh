#!/usr/bin/env bash
# Phase 0 item 7 smoke -- exercise the three utility nodes end-to-end.
#
# Setup:
#   - position_broadcaster_node x2 (uav_id=0 and uav_id=1)
#   - uwb_ranging_simulator_node consuming both, publishing a range
#   - comm_logger_node measuring NoisyPose size + rate
#
# Pass: each of (NoisyPose 0, NoisyPose 1, UWB range) topic appears
#       in ros2 topic list; comm_logger reports >0 messages.

set -eo pipefail

CLEAN_DONE=0
declare -a NODE_PIDS=()
cleanup() {
    [[ "$CLEAN_DONE" -eq 1 ]] && return 0
    CLEAN_DONE=1
    echo ""
    echo "--- cleanup ---"
    for pid in "${NODE_PIDS[@]:-}"; do
        [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
    done
    pkill -u "$(whoami)" -f 'position_broadcaster_node' 2>/dev/null || true
    pkill -u "$(whoami)" -f 'uwb_ranging_simulator_node' 2>/dev/null || true
    pkill -u "$(whoami)" -f 'comm_logger_node' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
# shellcheck disable=SC1091
source /workspace/ros2_ws/install/setup.bash

echo "=== uav_swarm_nodes smoke ==="

echo "[1/4] Spawning 2 position_broadcaster_node instances..."
ros2 run uav_swarm_nodes position_broadcaster_node \
    --ros-args -p uav_id:=0 -p publish_rate:=5.0 -p sigma_inject:=1.0 \
    >/tmp/pb-0.log 2>&1 &
NODE_PIDS+=($!)
ros2 run uav_swarm_nodes position_broadcaster_node \
    --ros-args -p uav_id:=1 -p publish_rate:=5.0 -p sigma_inject:=1.0 \
    >/tmp/pb-1.log 2>&1 &
NODE_PIDS+=($!)
sleep 3

echo "[2/4] Spawning uwb_ranging_simulator_node (pair 0,1)..."
ros2 run uav_swarm_nodes uwb_ranging_simulator_node \
    --ros-args -p uav_id_a:=0 -p uav_id_b:=1 -p sigma_range:=0.1 -p publish_rate:=5.0 \
    >/tmp/uwb.log 2>&1 &
NODE_PIDS+=($!)
sleep 2

echo "[3/4] Spawning comm_logger_node on /uav0/noisy_pose..."
ros2 run uav_swarm_nodes comm_logger_node \
    --ros-args -p topic:=/uav0/noisy_pose \
               -p msg_type:=uav_swarm_msgs/msg/NoisyPose \
               -p report_period:=3.0 \
    >/tmp/comm-logger.log 2>&1 &
NODE_PIDS+=($!)
sleep 5

echo "[4/4] Verifying topics + logger report..."
TOPIC_LIST=$(ros2 topic list --no-daemon 2>/dev/null)
PASS=1
for t in /uav0/noisy_pose /uav1/noisy_pose /uwb/range_0_1; do
    if grep -qx "$t" <<<"$TOPIC_LIST"; then
        echo "  ok -- topic present: $t"
    else
        echo "  MISSING topic: $t"
        PASS=0
    fi
done

# Wait one more report cycle, then check logger said anything meaningful
sleep 4
LOGGER_OUT=$(cat /tmp/comm-logger.log)
if grep -q 'msgs=[1-9]' <<<"$LOGGER_OUT"; then
    LATEST=$(grep 'msgs=' <<<"$LOGGER_OUT" | tail -1)
    echo "  ok -- comm_logger reported: $LATEST"
else
    echo "  MISSING comm_logger msgs>0 report"
    echo "  --- comm-logger.log ---"
    echo "$LOGGER_OUT" | tail -10
    PASS=0
fi

echo ""
if [[ "$PASS" -eq 1 ]]; then
    echo "UTILITY NODES OK"
else
    echo "FAIL"
    exit 1
fi
