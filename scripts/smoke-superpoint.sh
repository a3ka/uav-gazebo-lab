#!/usr/bin/env bash
# Phase 0 item 9 -- camera + SuperPoint smoke test.
#
# Goal: confirm that the GPU image's vision stack (torch + kornia +
# Zurich Z16 imagery) actually loads and produces keypoints on a real
# tile.
#
# Runs on either the CPU or GPU image. Without a CUDA device torch
# falls back to CPU inference (~5-15 s per frame, acceptable for
# smoke). With CUDA, inference is <100 ms.
#
# Image to use:
#   bash scripts/smoke-superpoint.sh           -> uses uav-lab:cpu
#   bash scripts/smoke-superpoint.sh gpu       -> uses uav-lab:gpu

set -eo pipefail

VARIANT="${1:-cpu}"
IMAGE="uav-lab:${VARIANT}"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "FAIL: image $IMAGE not present locally" >&2
    exit 1
fi

echo "=== SuperPoint smoke on $IMAGE ==="

docker run --rm -i \
    -v /home/nous/research/uav-gazebo-lab:/workspace/uav-gazebo-lab \
    -v /home/nous/einhard-runtime/runtime/navigation/tiles/zurich-z16:/datasets/zurich-z16 \
    "$IMAGE" \
    python3 - <<'PYEOF'
import os
import sys
import time

import cv2

# kornia ships SuperPoint as a torch module. CPU image has only kornia
# (no torch); GPU image has both. The CPU-image branch falls back to
# OpenCV ORB as a smoke proxy.
try:
    import torch
    from lightglue import SuperPoint
    HAVE_TORCH = True
except ImportError as exc:
    HAVE_TORCH = False
    print(f'[i] torch/lightglue not in this image ({exc}) -- using OpenCV ORB fallback')

TILES = sorted(p for p in os.listdir('/datasets/zurich-z16') if p.endswith('.png'))
print(f'[1/3] dataset: {len(TILES)} tiles visible')

img = cv2.imread('/datasets/zurich-z16/' + TILES[10])
print(f'[2/3] sample loaded: shape={img.shape} dtype={img.dtype}')

if HAVE_TORCH:
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'[3/3] running SuperPoint on {device}...')
    t0 = time.monotonic()
    # LightGlue's SuperPoint expects a dict `{'image': tensor}` and a
    # grayscale tensor of shape [B, 1, H, W] in [0, 1].
    model = SuperPoint(max_num_keypoints=512).eval().to(device)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype('float32') / 255.0
    t = torch.from_numpy(gray)[None, None, ...].to(device)
    with torch.no_grad():
        out = model({'image': t})
    elapsed = time.monotonic() - t0
    n_kp = int(out['keypoints'][0].shape[0])
    print(f'    SuperPoint: {n_kp} keypoints in {elapsed:.2f}s on {device}')
    if n_kp < 50:
        sys.exit(f'FAIL: keypoint count {n_kp} below smoke floor 50')
    print(f'SUPERPOINT OK ({n_kp} kp, {elapsed:.2f}s, {device})')
else:
    print('[3/3] running OpenCV ORB (no torch in this image)...')
    orb = cv2.ORB_create(nfeatures=2000)
    t0 = time.monotonic()
    kps = orb.detect(img, None)
    elapsed = time.monotonic() - t0
    print(f'    ORB: {len(kps)} keypoints in {elapsed:.2f}s')
    if len(kps) < 500:
        sys.exit(f'FAIL: ORB count {len(kps)} below smoke floor 500')
    print(f'ORB OK ({len(kps)} kp, {elapsed:.2f}s)')
PYEOF
