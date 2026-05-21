#!/usr/bin/env bash
# Phase 0 item 5a — single-vehicle PX4 SITL + Gazebo Harmonic smoke test.
#
# Inside-container procedure (explicit two-step per PX4 main docs):
#   1. Start MicroXRCEAgent on UDP 8888
#   2. Start `gz sim` with PX4's default world headless
#   3. Start PX4 with PX4_GZ_STANDALONE=1 so it attaches to the running
#      gz sim, spawns the x500 model, and brings up the gz_bridge module
#   4. Wait for ROS2 to see at least one /fmu/out/* topic
#   5. Cleanup
#
# Pass: exit 0 + "PX4 SITL OK".

set -euo pipefail

CLEAN_DONE=0
cleanup() {
    [[ "$CLEAN_DONE" -eq 1 ]] && return 0
    CLEAN_DONE=1
    echo ""
    echo "--- cleanup ---"
    [[ -n "${PX4_PID:-}" ]]   && kill "$PX4_PID"   2>/dev/null || true
    [[ -n "${GZ_PID:-}" ]]    && kill "$GZ_PID"    2>/dev/null || true
    [[ -n "${AGENT_PID:-}" ]] && kill "$AGENT_PID" 2>/dev/null || true
    pkill -f 'bin/px4'  2>/dev/null || true
    pkill -f 'gz sim'   2>/dev/null || true
    pkill -f 'ruby.*gz' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ -z "${ROS_DISTRO:-}" ]]; then
    # shellcheck disable=SC1091
    source /opt/ros/jazzy/setup.bash
fi

PX4_DIR=/workspace/PX4-Autopilot
if [[ ! -x "$PX4_DIR/build/px4_sitl_default/bin/px4" ]]; then
    echo "FAIL: PX4 binary not built — run scripts/build-px4.sh first" >&2
    exit 1
fi

# Locate the default Gazebo world PX4 ships
WORLD="$PX4_DIR/Tools/simulation/gz/worlds/default.sdf"
if [[ ! -f "$WORLD" ]]; then
    echo "FAIL: default world not found at $WORLD" >&2
    exit 1
fi

# Tell gz sim where to find PX4 models
export GZ_SIM_RESOURCE_PATH="$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}"

echo "=== Single-vehicle PX4 SITL smoke ==="
echo "ROS_DISTRO: ${ROS_DISTRO}"
echo "PX4 HEAD:   $(git -C "$PX4_DIR" rev-parse --short HEAD)"
echo "World:      $WORLD"
echo ""

# Step 1: MicroXRCEAgent
echo "[1/4] Starting MicroXRCEAgent (UDP4 port 8888)..."
MicroXRCEAgent udp4 -p 8888 > /tmp/xrce-agent.log 2>&1 &
AGENT_PID=$!
sleep 2
kill -0 "$AGENT_PID" 2>/dev/null || { echo "FAIL: agent died"; cat /tmp/xrce-agent.log; exit 1; }
echo "  ok — agent PID $AGENT_PID"

# Step 2: gz sim headless with PX4's default world
echo "[2/4] Starting gz sim (headless, default.sdf)..."
gz sim -s -r -v 1 "$WORLD" > /tmp/gz-sim.log 2>&1 &
GZ_PID=$!
sleep 5
if ! gz topic --list 2>/dev/null | grep -q '^/clock$'; then
    echo "FAIL: gz sim not publishing /clock"; tail -20 /tmp/gz-sim.log; exit 1
fi
echo "  ok — gz sim PID $GZ_PID, /clock visible"

# Step 3: PX4 SITL connecting to running gz sim
echo "[3/4] Launching PX4 SITL (PX4_GZ_STANDALONE=1, attaching to gz sim)..."
cd "$PX4_DIR"
PX4_GZ_STANDALONE=1 PX4_SYS_AUTOSTART=4001 PX4_SIM_MODEL=gz_x500 \
    HEADLESS=1 \
    ./build/px4_sitl_default/bin/px4 \
    -d ROMFS/px4fmu_common \
    > /tmp/px4-sitl.log 2>&1 &
PX4_PID=$!
echo "  PX4 PID $PX4_PID — waiting for /fmu/out/* topics..."

# Step 4: wait for ROS2 to see PX4 topics
TIMEOUT=90
ELAPSED=0
SAW_TOPIC=""
while [[ $ELAPSED -lt $TIMEOUT ]]; do
    if ros2 topic list 2>/dev/null | grep -q '^/fmu/out/'; then
        SAW_TOPIC=$(ros2 topic list 2>/dev/null | grep '^/fmu/out/' | head -1)
        break
    fi
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done

if [[ -z "$SAW_TOPIC" ]]; then
    echo "FAIL: no /fmu/out/* ROS2 topics after ${TIMEOUT}s"
    echo "--- PX4 log tail ---"
    tail -30 /tmp/px4-sitl.log
    echo "--- agent log tail ---"
    tail -10 /tmp/xrce-agent.log
    exit 1
fi
echo "  ok — first PX4 topic seen: $SAW_TOPIC (after ${ELAPSED}s)"

# Step 4b: confirm PX4 is publishing a healthy set of topics.
# We can't `ros2 topic echo` / `topic hz` without the px4_msgs ROS2
# package (separate Phase 0 item 6 — Python introspection needs the msg
# schema). For smoke purpose, the presence of a healthy topic set is
# enough evidence the full Gazebo ↔ PX4 ↔ uXRCE-DDS ↔ ROS2 pipeline
# is alive. PX4 default config publishes 20+ /fmu/out/* topics.
echo "[4/4] Counting /fmu/out/* topics..."
COUNT=$(ros2 topic list 2>/dev/null | grep -c '^/fmu/out/' || true)
echo "  /fmu/out/* topics published: $COUNT"
if [[ "$COUNT" -lt 5 ]]; then
    echo "FAIL: expected >=5 /fmu/out/* topics, got $COUNT"
    echo "--- /fmu/out/ topics ---"
    ros2 topic list 2>/dev/null | grep '^/fmu/out/' || true
    exit 1
fi
echo "  ok — full topic set is being published; pipeline alive"

echo ""
echo "PX4 SITL OK"
echo "Topics flowing: Gazebo ↔ PX4 ↔ uXRCE-DDS ↔ ROS2"
