#!/usr/bin/env bash
# Phase 0 item 3 — build PX4 SITL inside the container.
#
# Pre-req: ../PX4-Autopilot/ already cloned on host (recursive submodules).
#          Bind-mounted into the container at /workspace/PX4-Autopilot/.
#
# Target: px4_sitl_default — compiles the SITL binary without launching.
#         Launching with Gazebo is a separate verify step (see
#         scripts/smoke-px4-sitl.sh once that exists).
#
# Wall time: ~30-45 min first build, ~30 s incremental.
# Writes build artefacts to /workspace/PX4-Autopilot/build/ which bind-
# mounts back to the host so subsequent runs reuse the cache.

set -euo pipefail

PX4_DIR=/workspace/PX4-Autopilot

if [[ ! -d "$PX4_DIR" ]]; then
    echo "FAIL: $PX4_DIR not present (host bind-mount missing)" >&2
    exit 1
fi

cd "$PX4_DIR"

# Use jobs = nproc - 1 to keep terminal responsive
JOBS=$(($(nproc) - 1))
[[ $JOBS -lt 1 ]] && JOBS=1

echo "=== PX4 SITL build ==="
echo "PX4 HEAD: $(git rev-parse --short HEAD)"
echo "Jobs:     $JOBS"
echo "Target:   px4_sitl_default"
echo ""

# Build. PX4's Makefile handles cmake configure on first invocation.
make px4_sitl_default -j"$JOBS"

echo ""
echo "=== Build complete ==="
ls -lh build/px4_sitl_default/bin/px4 2>/dev/null || {
    echo "FAIL: px4 binary not present in build/" >&2
    exit 1
}
echo "BUILD OK"
