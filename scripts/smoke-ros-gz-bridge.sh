#!/usr/bin/env bash
# Phase 0 item 2 — ros_gz_bridge smoke test.
#
# Runs entirely inside the uav-lab:cpu container.
#
# Procedure:
#   1. Launch `gz sim` headless against an empty world
#   2. Launch `parameter_bridge` for /clock (Gazebo -> ROS2)
#   3. Subscribe to /clock from ROS2 and verify at least one message arrives
#   4. Clean up
#
# Pass criterion: exit 0 with "BRIDGE OK" printed. Anything else = fail.

set -eo pipefail

cleanup() {
    local rc=$?
    echo "--- cleanup ---"
    [[ -n "${GZ_PID:-}" ]] && kill "$GZ_PID" 2>/dev/null || true
    [[ -n "${BRIDGE_PID:-}" ]] && kill "$BRIDGE_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    exit $rc
}
trap cleanup EXIT INT TERM

# Source ROS2 if not already sourced
if [[ -z "${ROS_DISTRO:-}" ]]; then
    # shellcheck disable=SC1091
    source /opt/ros/jazzy/setup.bash
fi

echo "=== ros_gz_bridge smoke test ==="
echo "ROS_DISTRO: ${ROS_DISTRO}"
echo "GZ version: $(gz sim --version 2>&1 | head -1)"
echo ""

# Step 1: start gz sim headless against the empty world
echo "[1/4] Launching gz sim (headless, empty world)..."
gz sim -s -r empty.sdf > /tmp/gz-sim.log 2>&1 &
GZ_PID=$!
sleep 3

# Verify gz sim is publishing /clock
if ! gz topic --list 2>/dev/null | grep -q '^/clock$'; then
    echo "FAIL: gz sim did not publish /clock topic"
    cat /tmp/gz-sim.log
    exit 1
fi
echo "  ok — gz sim is running, /clock topic visible to gz transport"

# Step 2: launch the parameter_bridge
echo "[2/4] Launching ros_gz parameter_bridge for /clock..."
ros2 run ros_gz_bridge parameter_bridge \
    /clock@rosgraph_msgs/msg/Clock\[gz.msgs.Clock \
    > /tmp/ros-gz-bridge.log 2>&1 &
BRIDGE_PID=$!
sleep 2

if ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
    echo "FAIL: parameter_bridge did not stay alive"
    cat /tmp/ros-gz-bridge.log
    exit 1
fi
echo "  ok — parameter_bridge running (PID $BRIDGE_PID)"

# Step 3: verify ROS2 sees /clock messages
echo "[3/4] Subscribing to /clock from ROS2..."
if timeout 10 ros2 topic echo --once --timeout 8 /clock > /tmp/ros-clock.log 2>&1; then
    echo "  ok — received at least one /clock message from Gazebo via the bridge:"
    sed 's/^/    /' /tmp/ros-clock.log | head -5
else
    echo "FAIL: did not receive /clock messages in ROS2"
    echo "--- bridge log ---"
    cat /tmp/ros-gz-bridge.log
    echo "--- gz log ---"
    cat /tmp/gz-sim.log
    exit 1
fi

# Step 4: clean shutdown handled by trap
echo "[4/4] Smoke test passed."
echo ""
echo "BRIDGE OK"
