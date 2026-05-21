#!/usr/bin/env bash
# Phase 0 item 6 — build the colcon workspace inside the container.
#
# Workspace lives at host /home/nous/research/ros2_ws/ and is bind-
# mounted into the container at /workspace/ros2_ws/. Two packages:
#
#   src/px4_msgs        → ../../px4_msgs        (PX4 ROS2 msg defs)
#   src/uav_swarm_msgs  → ../../uav-gazebo-lab/src/uav_swarm_msgs
#                         (our 4 paper-§IV-B types)
#
# Wall time: ~3-6 min first build (px4_msgs alone has 246 messages).
# Re-runs are incremental thanks to colcon's symlinked install dir.

# `set -u` removed: ROS2 setup scripts + python entrypoints touch
# unbound vars in many places. Keep -e + pipefail for fail-loud behaviour.
set -eo pipefail

WS=/workspace/ros2_ws
cd "$WS"

[[ -d src/px4_msgs ]]        || { echo "FAIL: src/px4_msgs missing"; exit 1; }
[[ -d src/uav_swarm_msgs ]]  || { echo "FAIL: src/uav_swarm_msgs missing"; exit 1; }
[[ -d src/uav_swarm_nodes ]] || { echo "FAIL: src/uav_swarm_nodes missing"; exit 1; }

# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash

JOBS=$(($(nproc) - 1))
[[ $JOBS -lt 1 ]] && JOBS=1

echo "=== Colcon build (jobs=$JOBS) ==="
colcon build --symlink-install \
    --packages-select px4_msgs uav_swarm_msgs uav_swarm_nodes \
    --parallel-workers "$JOBS"

echo ""
echo "=== Verifying installed packages ==="
# shellcheck disable=SC1091
source install/setup.bash

# Collect output first — `ros2 pkg list | grep -q` triggers
# BrokenPipeError in the python entrypoint when grep -q closes the pipe
# early, and pipefail turns that into a false fail.
PKG_LIST=$(ros2 pkg list 2>/dev/null)

# Message packages first
for pkg in px4_msgs uav_swarm_msgs; do
    if ! grep -qx "$pkg" <<<"$PKG_LIST"; then
        echo "FAIL: $pkg not registered with ROS2 after build"
        exit 1
    fi
    # `ros2 interface package <pkg>` lists one interface per line, no
    # indent. (`ros2 interface list` indents every entry by 4 spaces
    # under "Messages:" / "Services:" / "Actions:" headers.)
    PKG_IFACES=$(ros2 interface package "$pkg" 2>/dev/null || true)
    COUNT=$(grep -c '^' <<<"$PKG_IFACES" || true)
    echo "  $pkg: $COUNT interfaces registered"
done

# Node package (no interfaces -- just verify package + entry points
# are registered)
for pkg in uav_swarm_nodes; do
    if ! grep -qx "$pkg" <<<"$PKG_LIST"; then
        echo "FAIL: $pkg not registered with ROS2 after build"
        exit 1
    fi
    EXECS=$(ros2 pkg executables "$pkg" 2>/dev/null || true)
    COUNT=$(grep -c '^' <<<"$EXECS" || true)
    echo "  $pkg: $COUNT executables registered"
done

echo ""
echo "=== uav_swarm_msgs interfaces ==="
ros2 interface package uav_swarm_msgs 2>/dev/null

echo ""
echo "=== Verify schema parse on one uav_swarm_msgs interface ==="
echo "ros2 interface show uav_swarm_msgs/msg/NoisyPose (first 12 lines):"
SHOW_OUT=$(ros2 interface show uav_swarm_msgs/msg/NoisyPose 2>&1)
SHOW_RC=$?
if [[ "$SHOW_RC" -ne 0 ]]; then
    echo "FAIL: schema show errored (rc=$SHOW_RC):"
    echo "$SHOW_OUT"
    exit 1
fi
head -12 <<<"$SHOW_OUT"
echo "(schema parsed OK)"

echo ""
echo "WS BUILD OK"
