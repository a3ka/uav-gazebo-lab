#!/usr/bin/env bash
# Vast.ai instance one-shot bootstrap for Phase 1 / 2 / 3 campaigns.
#
# Phase 1 + 2 require GPU (SuperPoint + PoO match). Phase 3 is CPU-only
# (TRN is mocked, no vision pipeline) and runs on either the :cpu or
# :gpu image; for the production sweep, rent a high-core-count CPU
# instance (e.g. 16 cores) and use --jobs to parallelise trials.
#
# Run from INSIDE the vast.ai instance after SSH'ing in. Assumes the
# image is ghcr.io/a3ka/uav-lab:gpu (public). On first run it:
#   1. Clones uav-gazebo-lab + px4_msgs at /workspace
#   2. Builds the colcon workspace (px4_msgs + uav_swarm_msgs + nodes)
#   3. Smoke-tests SuperPoint on GPU on one Zurich tile
#
# Dataset staging (Zurich Z16 tiles) must be done from your LOCAL host
# BEFORE running this -- the instance has no internet route to
# einhard-runtime. From local:
#   scp -P <PORT> -r /home/nous/einhard-runtime/runtime/navigation/tiles/zurich-z16 \
#       root@<HOST>:/workspace/uav-gazebo-lab/datasets/staged/
#
# Idempotent: re-running just re-runs the build + smoke (won't re-clone).

set -eo pipefail

ROOT=/workspace
REPO_URL=https://github.com/a3ka/uav-gazebo-lab.git
PX4_MSGS_URL=https://github.com/PX4/px4_msgs.git

echo "=== vast-bootstrap on $(hostname) ==="
cd "$ROOT"

# 1. uav-gazebo-lab repo
if [[ -d "$ROOT/uav-gazebo-lab/.git" ]]; then
    echo "[1/5] uav-gazebo-lab already cloned -- pulling latest"
    git -C "$ROOT/uav-gazebo-lab" pull --rebase 2>&1 | tail -2
else
    echo "[1/5] Cloning uav-gazebo-lab..."
    git clone --depth 1 "$REPO_URL" "$ROOT/uav-gazebo-lab" 2>&1 | tail -2
fi
cd "$ROOT/uav-gazebo-lab"
git log -1 --oneline
mkdir -p datasets/staged workspaces

# 2. px4_msgs sibling
if [[ -d "$ROOT/px4_msgs/.git" ]]; then
    echo "[2/5] px4_msgs already cloned"
else
    echo "[2/5] Cloning px4_msgs..."
    git clone --depth 1 "$PX4_MSGS_URL" "$ROOT/px4_msgs" 2>&1 | tail -2
fi

# 3. colcon workspace
echo "[3/5] Setting up ros2_ws (symlinks src/ -> repo packages)..."
mkdir -p "$ROOT/ros2_ws/src"
cd "$ROOT/ros2_ws/src"
ln -sfn "$ROOT/px4_msgs" px4_msgs
ln -sfn "$ROOT/uav-gazebo-lab/src/uav_swarm_msgs" uav_swarm_msgs
ln -sfn "$ROOT/uav-gazebo-lab/src/uav_swarm_nodes" uav_swarm_nodes
ls -la

cd "$ROOT/uav-gazebo-lab"
echo "[4/5] Building ros2_ws (~3-5 min first build)..."
bash scripts/build-ros2-ws.sh 2>&1 | tail -8

# 5. SuperPoint GPU smoke
echo "[5/5] SuperPoint smoke on GPU..."
if [[ ! -d "$ROOT/uav-gazebo-lab/datasets/staged/zurich-z16" ]]; then
    echo "  WARNING: dataset not staged yet at $ROOT/uav-gazebo-lab/datasets/staged/zurich-z16"
    echo "  scp it from your local host (see header comment), then re-run this script."
    exit 0
fi
python3 - <<'PYEOF'
import cv2, torch, time
from lightglue import SuperPoint
img = cv2.imread('/workspace/uav-gazebo-lab/datasets/staged/zurich-z16/tile_47.4010_8.5410_47.4065_8.5465.png')
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model = SuperPoint(max_num_keypoints=512).eval().to(device)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype('float32') / 255.0
t = torch.from_numpy(gray)[None, None, ...].to(device)
for _ in range(3):
    with torch.no_grad(): _ = model({'image': t})
if device == 'cuda':
    torch.cuda.synchronize()
t0 = time.monotonic()
for _ in range(20):
    with torch.no_grad(): out = model({'image': t})
if device == 'cuda':
    torch.cuda.synchronize()
ms = (time.monotonic() - t0) / 20 * 1000
nkp = int(out['keypoints'][0].shape[0])
print(f'GPU smoke: keypoints={nkp}, avg inference {ms:.1f} ms on {device}')
PYEOF

echo ""
echo "=== bootstrap complete ==="
echo ""
echo "Next: run a production campaign."
echo ""
echo "Phase 2 (M-quorum sweep, ~2.5 hr GPU):"
echo "  bash scripts/phase2-batch-campaign.sh"
echo ""
echo "Phase 3 (CEP-vs-hops, ~3.5 hr CPU at jobs=4, no GPU needed):"
echo "  JOBS=4 bash scripts/phase3-batch-campaign.sh"
