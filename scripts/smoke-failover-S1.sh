#!/usr/bin/env bash
# Phase 4 task 4.5 -- scenario S1 (sudden anchor death) smoke test.
#
# Setup:
#   anchor 0 (pos 0,0,50) -- target_capacity=5
#   anchor 1 (pos 50,0,50) -- target_capacity=5
#   follower 0 attached initially to anchor 0
#
# Timeline:
#   t=0   launch agents
#   t=3   steady-state achieved (DistilledState 0 flowing to follower 0)
#   t=10  kill anchor 0 process (SIGKILL) -- "S1 Sudden death"
#   t=10-20  follower 0 watchdog fires at t=15 (5 s timeout); F2-F5
#            should complete within 10 s of detection
#   t=25  verify switching_time < 10 s on /phase4/timing/f0
#
# Pass: at least one switching_time value on /phase4/timing/f0 with
#       value < 10.0.

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
    pkill -u "$(whoami)" -f 'uav_swarm_nodes' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
# shellcheck disable=SC1091
source /workspace/ros2_ws/install/setup.bash

echo "=== Phase 4 smoke S1 (sudden anchor death) ==="

echo "[1/5] Launch 2 anchors (setsid -> own process group so SIGKILL kills the child too)..."
setsid ros2 run uav_swarm_nodes anchor_node \
    --ros-args -p anchor_id:=0 -p initial_position:='[0.0, 0.0, 50.0]' \
               -p target_capacity:=5 -p reputation:=0.8 -p publish_rate:=10.0 \
    >/tmp/a0.log 2>&1 &
A0_PID=$!
PIDS+=("$A0_PID")
setsid ros2 run uav_swarm_nodes anchor_node \
    --ros-args -p anchor_id:=1 -p initial_position:='[50.0, 0.0, 50.0]' \
               -p target_capacity:=5 -p reputation:=0.8 -p publish_rate:=10.0 \
    >/tmp/a1.log 2>&1 &
A1_PID=$!
PIDS+=("$A1_PID")
sleep 4   # DDS discovery + initial DistilledState flow

echo "[2/5] Launch follower 0 (attached to anchor 0)..."
ros2 run uav_swarm_nodes follower_node \
    --ros-args -p follower_id:=0 -p initial_anchor_id:=0 \
               -p known_anchor_ids:='[0, 1]' -p t_timeout:=5.0 \
               -p t_offer_window:=1.0 \
    >/tmp/f0.log 2>&1 &
F0_PID=$!
PIDS+=("$F0_PID")
sleep 3

# Verify steady-state: DistilledState topic from anchor 0 visible
TOPICS=$(ros2 topic list --no-daemon 2>/dev/null)
for t in /anchor0/distilled_state /anchor1/distilled_state /reassign/request; do
    if grep -qx "$t" <<<"$TOPICS"; then
        echo "  ok -- $t present"
    else
        echo "  MISSING $t"
        exit 1
    fi
done

echo "[3/5] Steady-state OK. Sleeping 5 s then killing anchor 0..."
sleep 5
T_DEATH=$(date +%s.%N)
# setsid put anchor 0 in its own process group with PGID == A0_PID.
# Kill the whole group so the actual python child dies (ros2 run is a
# wrapper; SIGKILL on $A0_PID alone leaves the child running).
kill -KILL -- -"$A0_PID" 2>/dev/null
echo "  anchor 0 process group killed at $T_DEATH"

echo "[4/5] Listening on /phase4/timing/f0 for up to 20 s..."
# Use ros2 topic echo to capture the first Float64 sample.
# Time it out after 20 s (5s watchdog + 10s budget + slack).
TIMING_OUT=$(timeout 20 ros2 topic echo --once /phase4/timing/f0 \
                std_msgs/msg/Float64 2>&1 || true)
echo "$TIMING_OUT"

# Extract data field
SWITCH_T=$(grep '^data:' <<<"$TIMING_OUT" | awk '{print $2}' | head -1)
if [[ -z "$SWITCH_T" ]]; then
    echo "[5/5] FAIL: no switching time reported by follower 0"
    echo "--- follower log tail ---"
    tail -30 /tmp/f0.log
    echo "--- anchor 1 log tail ---"
    tail -20 /tmp/a1.log
    exit 1
fi

echo "[5/5] Switching time = ${SWITCH_T}s"
# bash float compare via awk
if awk -v t="$SWITCH_T" 'BEGIN{exit !(t < 10.0)}'; then
    echo ""
    echo "S1 FAILOVER OK (switching_time=${SWITCH_T}s < 10.0s)"
else
    echo "S1 FAILOVER FAIL (switching_time=${SWITCH_T}s >= 10.0s)"
    exit 1
fi
