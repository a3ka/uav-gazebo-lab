#!/usr/bin/env bash
# Phase 0 item 5b — multi-vehicle PX4 SITL smoke (Gazebo Harmonic).
#
# Usage: scripts/smoke-px4-multi.sh [N]    (default 2; tested 2, 5, 10)
#
# Inside-container procedure:
#   1. Start MicroXRCEAgent (UDP 8888)
#   2. Start gz sim with PX4 default.sdf world headless
#   3. Launch N PX4 instances with -i 0..N-1; each spawns model x500_<i>
#      at a different position. PX4_GZ_STANDALONE=1 so they attach to
#      the running gz sim.
#   4. Wait for N sets of /px4_<i>/fmu/out/* ROS2 topics to appear
#   5. Cleanup via trap
#
# Pass: each instance i must publish at least one /px4_<i>/fmu/out/* topic.

set -uo pipefail

N=${1:-2}
echo "=== Multi-vehicle PX4 SITL smoke (N=$N) ==="

declare -a PX4_PIDS=()
CLEAN_DONE=0
cleanup() {
    [[ "$CLEAN_DONE" -eq 1 ]] && return 0
    CLEAN_DONE=1
    echo ""
    echo "--- cleanup ---"
    for pid in "${PX4_PIDS[@]:-}"; do
        [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
    done
    [[ -n "${GZ_PID:-}" ]]    && kill "$GZ_PID"    2>/dev/null || true
    [[ -n "${AGENT_PID:-}" ]] && kill "$AGENT_PID" 2>/dev/null || true
    pkill -u "$(whoami)" -f 'bin/px4'  2>/dev/null || true
    pkill -u "$(whoami)" -f 'gz sim'   2>/dev/null || true
    pkill -u "$(whoami)" -f 'ruby.*gz' 2>/dev/null || true
    sleep 1
    pkill -9 -u "$(whoami)" -f 'bin/px4' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

[[ -z "${ROS_DISTRO:-}" ]] && source /opt/ros/jazzy/setup.bash

PX4_DIR=/workspace/PX4-Autopilot
WORLD="$PX4_DIR/Tools/simulation/gz/worlds/default.sdf"
export GZ_SIM_RESOURCE_PATH="$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}"

[[ -x "$PX4_DIR/build/px4_sitl_default/bin/px4" ]] || { echo "FAIL: PX4 not built"; exit 1; }
[[ -f "$WORLD" ]] || { echo "FAIL: world not found"; exit 1; }

echo "PX4 HEAD: $(git -C "$PX4_DIR" rev-parse --short HEAD)"
echo ""

# Step 1
echo "[1/4] MicroXRCEAgent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/xrce-agent.log 2>&1 &
AGENT_PID=$!
sleep 2
kill -0 "$AGENT_PID" 2>/dev/null || { echo "FAIL: agent"; exit 1; }
echo "  ok"

# Step 2
echo "[2/4] gz sim (headless)..."
gz sim -s -r -v 1 "$WORLD" > /tmp/gz-sim.log 2>&1 &
GZ_PID=$!
sleep 5
gz topic --list 2>/dev/null | grep -q '^/clock$' || { echo "FAIL: gz"; tail /tmp/gz-sim.log; exit 1; }
echo "  ok"

# Step 3 — N PX4 instances. Stagger spawn to avoid model-name collisions
# during gz model insertion.
echo "[3/4] Launching $N PX4 instances..."
cd "$PX4_DIR"
for i in $(seq 0 $((N - 1))); do
    INST_DIR="build/px4_sitl_default/instance_$i"
    mkdir -p "$INST_DIR"
    # Stagger X position so they don't spawn on top of each other.
    # PX4_UXRCE_DDS_NS prefixes ROS2 topics with /px4_<i>/ so multiple
    # instances don't collide on the same uXRCE-DDS namespace. The rcS
    # init script (ROMFS/px4fmu_common/init.d-posix/rcS:297) reads it
    # and passes -n to uxrce_dds_client.
    PX4_GZ_MODEL_POSE="$((i * 5)),0,0.1,0,0,0" \
    PX4_GZ_STANDALONE=1 \
    PX4_SIM_MODEL=gz_x500 \
    PX4_UXRCE_DDS_NS="px4_${i}" \
    HEADLESS=1 \
        ./build/px4_sitl_default/bin/px4 \
        -i "$i" \
        -d \
        ROMFS/px4fmu_common \
        > "/tmp/px4-instance-$i.log" 2>&1 &
    PID=$!
    PX4_PIDS+=("$PID")
    echo "  instance $i: pid $PID, pose=(${i}0,0,0.1)"
    sleep 4   # space out spawns
done
echo "  all $N instances launched"

# Step 4 — boot for N instances scales ~linearly under shared physics
# and uXRCE-DDS load; 180 s covers N up to ~10.
echo "[4/4] Waiting for /px4_<i>/fmu/out/* topics in ROS2..."
TIMEOUT=180
ELAPSED=0
HEALTHY=0
while [[ $ELAPSED -lt $TIMEOUT ]]; do
    TOPIC_LIST=$(ros2 topic list --no-daemon 2>/dev/null || true)
    HEALTHY=0
    for i in $(seq 0 $((N - 1))); do
        if echo "$TOPIC_LIST" | grep -q "^/px4_${i}/fmu/out/"; then
            HEALTHY=$((HEALTHY + 1))
        fi
    done
    echo "  t=${ELAPSED}s healthy=$HEALTHY/$N"
    [[ "$HEALTHY" -ge "$N" ]] && break
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

echo "  healthy instances: $HEALTHY / $N (after ${ELAPSED}s)"
if [[ "$HEALTHY" -lt "$N" ]]; then
    echo "FAIL: not all instances reported topics"
    echo "--- instance status ---"
    for i in $(seq 0 $((N - 1))); do
        COUNT=$(ros2 topic list 2>/dev/null | grep -c "^/px4_${i}/fmu/out/" || true)
        echo "  instance $i: $COUNT topics"
    done
    echo "--- last 20 lines instance 0 log ---"
    tail -20 /tmp/px4-instance-0.log
    exit 1
fi

# Per-instance count
echo ""
for i in $(seq 0 $((N - 1))); do
    COUNT=$(ros2 topic list 2>/dev/null | grep -c "^/px4_${i}/fmu/out/" || true)
    echo "  instance $i: $COUNT /fmu/out/ topics"
done

echo ""
echo "MULTI-PX4 OK (N=$N)"
