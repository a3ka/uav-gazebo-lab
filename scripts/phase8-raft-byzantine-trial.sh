#!/usr/bin/env bash
# Phase 8 Byzantine-attack trial — capability-gap measurement.
#
# Setup: N raft_nodes total, 1 is Byzantine (--byzantine) lying that
# it's leader from t=0. Honest nodes never silence-detect because
# Byzantine's heartbeats keep their election timer reset.
#
# Args:  N node_count  OUT_JSON
#
# Measures:
#   * `byzantine_dominates`: bool — at t=20s, is Byzantine the only
#     "leader" the cluster sees (i.e. honest cluster compromised)?
#   * `honest_leader_emerged`: bool — did ANY honest node successfully
#     elect itself? (Raft expectation: NO.)
#   * `t_honest_takeover_s`: time to first honest-leader heartbeat
#     after start, or None.

set -o pipefail

N="${1:-5}"
OUT="${2:-/tmp/raft_byz.json}"
BYZ_ID=0    # node 0 is the Byzantine attacker; honest = 1..N-1

declare -a PIDS=()
cleanup() {
    for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
    pkill -u "$(whoami)" -f 'raft_node' 2>/dev/null || true
    pkill -u "$(whoami)" -f 'phase8-heartbeat-watcher' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4

echo "[1] launching $N raft_nodes (node $BYZ_ID is Byzantine)..."
for i in $(seq 0 $((N - 1))); do
    BYZ_FLAG="false"
    if [[ "$i" == "$BYZ_ID" ]]; then BYZ_FLAG="true"; fi
    setsid ros2 run uav_swarm_nodes raft_node --ros-args \
        -r __node:=raft_$i \
        -p node_id:=$i -p n_members:=$N \
        -p election_timeout_s:=5.0 -p heartbeat_period_s:=1.0 \
        -p jitter_max_s:=1.0 -p seed:=$((i * 7919 + 1)) \
        -p byzantine:=$BYZ_FLAG \
        >/tmp/raft_${i}.log 2>&1 &
    PIDS+=("$!")
done

ECHO_FILE=/tmp/raft_byz_stream.$$
python3 /workspace/uav-gazebo-lab/scripts/phase8-heartbeat-watcher.py \
    --max-seconds 25 > "$ECHO_FILE" 2>"${ECHO_FILE}.err" &
ECHO_PID=$!
PIDS+=("$ECHO_PID")

# Observe for 20s. Sample heartbeat leaders.
sleep 20

# Analyze
T_FIRST_HONEST=""
HONEST_LEADERS=()
while IFS= read -r line; do
    LID=$(sed -n 's/.*leader=\([0-9][0-9]*\).*/\1/p' <<<"$line")
    TS=$(sed -n 's/^HB \([0-9][0-9]*\).*/\1/p' <<<"$line")
    if [[ -n "$LID" && "$LID" != "$BYZ_ID" ]]; then
        HONEST_LEADERS+=("$LID")
        if [[ -z "$T_FIRST_HONEST" ]]; then
            T_FIRST_HONEST=$TS
        fi
    fi
done < "$ECHO_FILE"

# Last 5s of stream: who dominated?
TOTAL_HB=$(grep -c '^HB ' "$ECHO_FILE" 2>/dev/null || echo 0)
HONEST_HB=${#HONEST_LEADERS[@]}
BYZ_HB=$((TOTAL_HB - HONEST_HB))
BYZ_DOMINATES="true"
if [[ "$HONEST_HB" -gt "$BYZ_HB" ]]; then BYZ_DOMINATES="false"; fi
HONEST_EMERGED="false"
if [[ "$HONEST_HB" -gt 0 ]]; then HONEST_EMERGED="true"; fi

cat > "$OUT" <<EOF
{"n_members": $N, "byzantine_id": $BYZ_ID,
 "total_heartbeats": $TOTAL_HB,
 "byzantine_heartbeats": $BYZ_HB,
 "honest_heartbeats": $HONEST_HB,
 "byzantine_dominates": $BYZ_DOMINATES,
 "honest_leader_emerged": $HONEST_EMERGED,
 "t_first_honest_us": ${T_FIRST_HONEST:-null}}
EOF
echo "[5] DONE: byz_dominates=$BYZ_DOMINATES honest_emerged=$HONEST_EMERGED  ($HONEST_HB honest hbs / $TOTAL_HB total)"
