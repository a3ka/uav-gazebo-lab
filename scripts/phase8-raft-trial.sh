#!/usr/bin/env bash
# Phase 8 minimal-Raft single trial.
#
# Args:  N node_count  T_kill_s  OUT_JSON
#
# Procedure:
#   1. Spawn N raft_nodes via setsid (own pgid for SIGKILL).
#   2. Wait T_kill_s while the cluster elects an initial leader.
#   3. Capture initial leader id from /raft/leader_change/n* (one
#      sample per leader-elect from ANY node).
#   4. SIGKILL the leader's process group.
#   5. Wait up to 30 s for the NEXT leader-change message from a
#      DIFFERENT node and compute t_recover = t_new_leader - t_kill.
#   6. Cleanup + emit OUT_JSON.

set -o pipefail

N="${1:-5}"
T_KILL="${2:-7}"
OUT="${3:-/tmp/raft_trial.json}"

declare -a PIDS=()
cleanup() {
    for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
    pkill -u "$(whoami)" -f 'raft_node' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

echo "[1] launching $N raft_nodes..."
for i in $(seq 0 $((N - 1))); do
    setsid ros2 run uav_swarm_nodes raft_node --ros-args \
        -r __node:=raft_$i \
        -p node_id:=$i -p n_members:=$N \
        -p election_timeout_s:=5.0 -p heartbeat_period_s:=1.0 \
        -p jitter_max_s:=1.0 -p seed:=$((i * 7919 + 1)) \
        >/tmp/raft_${i}.log 2>&1 &
    PIDS+=("$!")
done

# Wait for initial leader election + steady state
sleep "$T_KILL"

# Detect initial leader via continuous /raft/heartbeat publish
# (leader_change is one-shot, volatile QoS, often missed by --once)
HB_OUT=$(timeout 2 ros2 topic echo --once /raft/heartbeat \
    uav_swarm_msgs/msg/RaftHeartbeat 2>/dev/null)
INITIAL_LEADER=$(grep '^leader_id:' <<<"$HB_OUT" | awk '{print $2}' | head -1)
if [[ -z "$INITIAL_LEADER" ]]; then
    echo "[FAIL] no initial leader heartbeat in ${T_KILL}s"
    echo "$HB_OUT" | head -5
    echo "{\"error\": \"no_initial_leader\"}" > "$OUT"
    exit 1
fi
echo "[2] initial leader detected via heartbeat: raft_$INITIAL_LEADER"

# Start the heartbeat stream FIRST (subscription needs ~500ms DDS
# discovery; if we start it AFTER kill there's a race where the new
# leader's heartbeats arrive before we're listening), then kill the
# leader, then poll the file.
ECHO_FILE=/tmp/raft_hb_stream.$$
stdbuf -oL timeout 35 ros2 topic echo /raft/heartbeat \
    uav_swarm_msgs/msg/RaftHeartbeat > "$ECHO_FILE" 2>/dev/null &
ECHO_PID=$!
PIDS+=("$ECHO_PID")
sleep 1.5   # let subscription discover publishers

# Kill the leader. pgid-based kill (kill -KILL -- -PID) is brittle
# because setsid + ros2 run + python -> the FINAL python child often
# lives in a different pgid by the time we read $! (ros2 run forks
# again internally before exec). Pattern-match by node-name instead.
T_KILL_UNIX=$(date +%s.%N)
pkill -9 -f "__node:=raft_${INITIAL_LEADER} " 2>/dev/null
pkill -9 -f "node_id:=${INITIAL_LEADER} " 2>/dev/null
echo "[3] killed leader raft_$INITIAL_LEADER at $T_KILL_UNIX"
RECOVERY=""
NEW_LEADER=""
T_DEADLINE=$(awk -v t="$T_KILL_UNIX" 'BEGIN{print t + 30}')
while :; do
    NOW=$(date +%s.%N)
    if awk -v n="$NOW" -v d="$T_DEADLINE" 'BEGIN{exit !(n > d)}'; then break; fi
    sleep 0.5
    # Read latest leader_id line from the stream
    LID=$(grep '^leader_id:' "$ECHO_FILE" 2>/dev/null | tail -1 | awk '{print $2}')
    if [[ -n "$LID" && "$LID" != "$INITIAL_LEADER" ]]; then
        T_NEW=$(date +%s.%N)
        RECOVERY=$(awk -v t="$T_KILL_UNIX" -v n="$T_NEW" 'BEGIN{print n - t}')
        NEW_LEADER=$LID
        echo "[4] new leader raft_$LID detected at recovery=${RECOVERY}s"
        break
    fi
done
kill "$ECHO_PID" 2>/dev/null || true

if [[ -z "$RECOVERY" ]]; then
    echo "[FAIL] no new leader emerged within 30s of kill"
    cat > "$OUT" <<EOF
{"n_members": $N, "initial_leader": $INITIAL_LEADER,
 "t_kill_unix": $T_KILL_UNIX, "recovery_s": null,
 "new_leader": null, "pass": false}
EOF
    exit 1
fi

cat > "$OUT" <<EOF
{"n_members": $N, "initial_leader": $INITIAL_LEADER,
 "t_kill_unix": $T_KILL_UNIX, "recovery_s": $RECOVERY,
 "new_leader": $NEW_LEADER, "pass": true}
EOF
echo "[5] DONE: recovery=${RECOVERY}s  out=$OUT"
