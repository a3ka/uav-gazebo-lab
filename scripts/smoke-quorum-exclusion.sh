#!/usr/bin/env bash
# Phase 2 task 2.4 smoke -- quorum_exclusion_node M-voter consensus.
#
# Three sub-tests:
#   A. 3 voters with own R = 0.8 all view target=10 R = 0.1 -> EXCLUDE
#   B. only 2 voters -> NO exclusion (M-1 < M_quorum=3)
#   C. 3 voters but one has own R = 0.5 (below T_quorum=0.6) -> NO exclusion
#
# After test A we expect ExclusionEvent on /phase2/exclusions/u99 with
# 3 voter_ids and voter_min_r >= 0.8. Tests B and C are inverted: we
# wait 4 s then assert NO ExclusionEvent was emitted.

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
    pkill -u "$(whoami)" -f 'uav_swarm_nodes\|smoke_quorum' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

run_subtest() {
    local name="$1"
    local voters_csv="$2"      # "id1:R1 id2:R2 id3:R3"
    local expect="$3"          # EXCLUDE | NO_EXCLUDE

    echo ""
    echo "--- subtest $name (expect $expect) ---"
    pkill -u "$(whoami)" -f 'quorum_exclusion_node\|smoke_quorum' 2>/dev/null || true
    sleep 1

    ros2 run uav_swarm_nodes quorum_exclusion_node \
        --ros-args -p uav_id:=99 -p m_quorum:=3 -p t_reject:=0.20 -p t_quorum:=0.60 \
        > /tmp/quorum.log 2>&1 &
    QPID=$!
    PIDS+=("$QPID")
    sleep 3

    # Start the exclusion-event listener BEFORE injection. ros2 topic
    # echo --once only catches NEW messages after subscription opens;
    # if we start it after the event fires we lose it.
    rm -f /tmp/exclusion_out
    ( timeout 12 ros2 topic echo --once /phase2/exclusions/u99 \
        uav_swarm_msgs/msg/ExclusionEvent > /tmp/exclusion_out 2>&1 ) &
    ECHO_PID=$!
    PIDS+=("$ECHO_PID")
    sleep 1   # let ros2 topic echo subscribe

    # Inject voters + views
    python3 - "$voters_csv" <<'PYEOF' > /tmp/qinject.log 2>&1 &
import sys, time
import rclpy
from rclpy.node import Node
from uav_swarm_msgs.msg import DistilledState, PeerReputationView

rclpy.init()
n = Node('smoke_quorum_injector')
pub_state = n.create_publisher(DistilledState, '/distilled_state', 10)
pub_view = n.create_publisher(PeerReputationView, '/reputation/view', 50)
for _ in range(20):
    rclpy.spin_once(n, timeout_sec=0.05)
    time.sleep(0.05)

# Parse voters spec: "id1:R1 id2:R2 ..."
spec = sys.argv[1]
voters = []
for chunk in spec.split():
    vid, r = chunk.split(':')
    voters.append((int(vid), float(r)))

target = 10
for voter_id, own_r in voters:
    # DistilledState: this voter's own R
    s = DistilledState()
    s.timestamp = int(time.time() * 1_000_000)
    s.position.x = 0.0; s.position.y = 0.0; s.position.z = 50.0
    s.position_covariance = [4.0,0.0,0.0,4.0,0.0,1.0]
    s.reputation = float(own_r)
    s.uav_id = voter_id
    pub_state.publish(s)
    # PeerReputationView: this voter sees target=10 R = 0.10
    v = PeerReputationView()
    v.timestamp = int(time.time() * 1_000_000)
    v.voter_id = voter_id
    v.target_id = target
    v.r_value = 0.10
    pub_view.publish(v)

# Spam a few more times to ensure subscribers pick up
for _ in range(10):
    for voter_id, own_r in voters:
        s = DistilledState()
        s.timestamp = int(time.time() * 1_000_000)
        s.position.x = 0.0; s.position.y = 0.0; s.position.z = 50.0
        s.position_covariance = [4.0,0.0,0.0,4.0,0.0,1.0]
        s.reputation = float(own_r)
        s.uav_id = voter_id
        pub_state.publish(s)
        v = PeerReputationView()
        v.timestamp = int(time.time() * 1_000_000)
        v.voter_id = voter_id
        v.target_id = target
        v.r_value = 0.10
        pub_view.publish(v)
    rclpy.spin_once(n, timeout_sec=0.05)
    time.sleep(0.1)

n.destroy_node()
rclpy.shutdown()
PYEOF
    PIDS+=("$!")
    # Wait for the background echo to finish (it'll exit on first message
    # or its 12 s timeout)
    wait "$ECHO_PID" 2>/dev/null || true
    EV=$(cat /tmp/exclusion_out 2>/dev/null || true)
    if echo "$EV" | grep -q 'target_id: 10'; then
        observed="EXCLUDE"
    else
        observed="NO_EXCLUDE"
    fi
    echo "  observed: $observed"

    if [[ "$observed" == "$expect" ]]; then
        echo "  PASS"
        return 0
    fi
    echo "  FAIL (expected $expect, got $observed)"
    echo "--- quorum log tail ---"
    tail -8 /tmp/quorum.log
    return 1
}

echo "=== Phase 2 quorum_exclusion_node smoke ==="
PASS=1
run_subtest "A: 3 qualified voters"  "1:0.8 2:0.8 3:0.8" "EXCLUDE"    || PASS=0
run_subtest "B: only 2 voters"        "1:0.8 2:0.8"        "NO_EXCLUDE" || PASS=0
run_subtest "C: 3 voters, 1 low-R"    "1:0.8 2:0.8 3:0.5"  "NO_EXCLUDE" || PASS=0

echo ""
if [[ "$PASS" -eq 1 ]]; then
    echo "QUORUM SMOKE OK (3/3 subtests pass)"
else
    echo "FAIL"; exit 1
fi
