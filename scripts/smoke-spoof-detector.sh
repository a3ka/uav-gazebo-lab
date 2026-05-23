#!/usr/bin/env bash
# Phase 5 smoke -- spoof_detector_node detects a single spoofed UAV.
#
# Setup: 4 UAVs in a tight square (within UWB), all pairs UWB-ranging.
#        UAV 0 starts honest. At t=5s, we set spoof_offset=[120,0,0] on
#        UAV 0 -- its reported GNSS pose jumps but UWB ranges remain true.
# Pass:  /spoof/alert publishes suspect_uav_id=0 within 5 s of injection.

set -o pipefail

CLEAN_DONE=0
declare -a PIDS=()
cleanup() {
    [[ "$CLEAN_DONE" -eq 1 ]] && return 0
    CLEAN_DONE=1
    for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
    pkill -u "$(whoami)" -f 'uav_swarm_nodes' 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

echo "=== Phase 5 spoof detector smoke ==="

echo "[1/4] Launch 4 static UAVs (square, side ~30m), all unique pb__node names..."
for i in 0 1 2 3; do
    cx=$(( (i % 2) * 30 ))
    cy=$(( (i / 2) * 30 ))
    ros2 run uav_swarm_nodes position_broadcaster_node --ros-args \
        -r __node:=pb${i} \
        -p uav_id:=${i} -p radius:=0.0 -p "center:=[${cx}.0, ${cy}.0]" \
        -p altitude:=50.0 -p sigma_inject:=0.5 -p publish_rate:=10.0 \
        > /tmp/pb${i}.log 2>&1 &
    PIDS+=("$!")
done
sleep 1.5

echo "[2/4] Launch 6 UWB simulators (all pairs)..."
PAIRS=("0 1" "0 2" "0 3" "1 2" "1 3" "2 3")
for pair in "${PAIRS[@]}"; do
    a=${pair% *}; b=${pair#* }
    ros2 run uav_swarm_nodes uwb_ranging_simulator_node --ros-args \
        -r __node:=uwb_${a}_${b} \
        -p uav_id_a:=${a} -p uav_id_b:=${b} -p sigma_range:=0.1 \
        -p publish_rate:=10.0 -p emit_typed:=true -p seed:=$((a*10+b)) \
        > /tmp/uwb_${a}_${b}.log 2>&1 &
    PIDS+=("$!")
done
sleep 1.5

echo "[3/4] Launch detector (known_uav_ids=[0,1,2,3])..."
ros2 run uav_swarm_nodes spoof_detector_node --ros-args \
    -p "known_uav_ids:=[0, 1, 2, 3]" \
    -p t_spoof_m:=20.0 -p m_suspect:=3 -p window_s:=2.0 \
    -p tick_rate_hz:=5.0 -p cooldown_s:=1.0 \
    > /tmp/spoof.log 2>&1 &
PIDS+=("$!")
sleep 3   # steady state

echo "[4/4] Inject spoof on UAV 0 (offset 120m on X)..."
T_INJECT=$(date +%s.%N)
ros2 param set /pb0 spoof_offset "[120.0, 0.0, 0.0]" > /dev/null

ALERT_OUT=$(timeout 8 ros2 topic echo --once /spoof/alert \
    uav_swarm_msgs/msg/SpoofAlert 2>&1 || true)
T_ALERT=$(date +%s.%N)
echo "  /spoof/alert sample:"
echo "$ALERT_OUT" | sed "s/^/    /" | head -6

SUSPECT=$(echo "$ALERT_OUT" | grep "^suspect_uav_id:" | awk '{print $2}')
DT=$(awk -v a="$T_INJECT" -v b="$T_ALERT" 'BEGIN{print b-a}')
echo ""
if [[ "$SUSPECT" == "0" ]]; then
    if awk -v t="$DT" 'BEGIN{exit !(t < 5.0)}'; then
        echo "SPOOF SMOKE OK  detection_dt=${DT}s  suspect=${SUSPECT} (correct)"
        exit 0
    else
        echo "FAIL: detected but slow (dt=${DT}s >= 5.0s)"; exit 1
    fi
fi
echo "FAIL: suspect=${SUSPECT}, expected 0"
tail -15 /tmp/spoof.log
exit 1
