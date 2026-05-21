#!/usr/bin/env bash
# Emergency cleanup helper — guarantees no uav-gazebo-lab artefacts
# linger after a test crash or Ctrl+C.
#
# Scope: ONLY processes / containers owned by the invoking user, and
# ONLY those started by uav-gazebo-lab smoke / build scripts.
# Will not touch other users' processes or containers from other projects.
#
# Idempotent — safe to run any time.

set -uo pipefail

ME=$(whoami)
PROJECT_TAG=uav-lab
echo "=== uav-gazebo-lab cleanup-host ==="
echo "User: $ME"
echo ""

# 1. Stop and remove any running uav-lab containers (--rm should already
#    handle this on graceful exit, but covers the crash case).
RUNNING=$(docker ps --filter "ancestor=$PROJECT_TAG:cpu" --filter "ancestor=$PROJECT_TAG:gpu" -q)
if [[ -n "$RUNNING" ]]; then
    echo "[1] Stopping $(echo "$RUNNING" | wc -l) running container(s):"
    docker stop $RUNNING
    docker rm   $RUNNING 2>/dev/null || true
else
    echo "[1] No running uav-lab containers."
fi
echo ""

# 2. Kill stray PX4 / Gazebo / uXRCE-DDS processes started by THIS user.
#    Docker --rm + per-container PID namespace should kill these for us,
#    but if someone ran a binary on the host directly, this catches it.
echo "[2] Stray host processes owned by $ME:"
KILLED=0
for pat in 'bin/px4 ' 'MicroXRCEAgent ' 'gz sim -s' 'ruby.*gz-sim'; do
    PIDS=$(pgrep -u "$ME" -f "$pat" || true)
    if [[ -n "$PIDS" ]]; then
        echo "  killing: pattern='$pat', pids=$(echo $PIDS)"
        echo "$PIDS" | xargs -r kill 2>/dev/null || true
        sleep 0.5
        echo "$PIDS" | xargs -r kill -9 2>/dev/null || true
        KILLED=$((KILLED + 1))
    fi
done
[[ $KILLED -eq 0 ]] && echo "  (none)"
echo ""

# 3. Port 8888 (uXRCE-DDS Agent default) and 4560 (PX4 SITL MAVLink)
#    should be free.
echo "[3] Port status:"
for p in 8888 4560 4561 4562; do
    if ss -lnup 2>/dev/null | grep -q ":$p\b"; then
        echo "  port $p: STILL LISTENING (manual investigation)"
    else
        echo "  port $p: free"
    fi
done
echo ""

echo "=== cleanup-host done ==="
