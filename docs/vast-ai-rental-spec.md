# vast.ai rental spec

Parameters to look for when picking an instance for Phase 1 (PoO
FAR/FRR campaign) and later GPU phases (2, 3, 6, 7, 8).

---

## Spec — minimum acceptable

| Property | Value | Why |
|---|---|---|
| GPU model | **RTX 4090** (preferred) or RTX 3090 | SuperPoint inference is light; the 4090 is 2-3× faster than the 3090 for the same workload, and per-hour cost only 1.5-2× higher → better $/result. RTX 3090 acceptable for budget-bound runs. |
| GPU count | 1 | Phase 1-3 are single-process, single-GPU. Multi-GPU helps only at Phase 6+ batch sweeps. |
| GPU VRAM | ≥ 16 GB | SuperPoint @ 480×640 uses <1 GB; headroom for future Phase 2/3 factor-graph + GTSAM CUDA. |
| CPU cores | ≥ 8 | Phase 6+ runs multi-vehicle PX4 SITL (~150 MB / 0.5 core per drone × 10-20 drones). |
| RAM | ≥ 32 GB | Same — PX4 SITL footprint, plus Gazebo, plus Python interpreters. |
| Disk | ≥ 80 GB | Pre-pulled GPU image is 14.2 GB, plus PX4 build ~5-20 GB, plus Sentinel-2 imagery if used (~10-50 GB), plus run-data + bag files. |
| Network down | ≥ 500 Mbit/s | Image pull from GHCR is 14 GB; at 500 Mbit/s ≈ 4 min, at 100 Mbit/s ≈ 20 min. |
| Reliability | > 0.95 | Per vast.ai's host-reliability field; below 0.95 means instance restart / pre-emption risk. |
| Rental type | **On-demand**, NOT interruptible | Phase 1 campaign is ~30-60 GPU-hr; pre-emption risk costs more than savings. |
| CUDA version | ≥ 12.6 | Matches our GPU image base `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04`. |
| Ubuntu | 24.04 hosts preferred | not strictly required — Docker abstracts; pick on perf, not host OS. |

## Spec — preferred (Phase 1 + future)

Same as above plus:
- RTX 4090 (24 GB VRAM)
- 16 cores / 64 GB RAM
- 200 GB SSD
- 1 Gbit/s+ network
- EU/US-East datacenter region for low-latency SSH

## Spec — economy mode (Phase 1 cheap pass)

Bare minimum to run Phase 1 at slower wall-time, smaller spend:
- RTX 3090 (24 GB VRAM) — cheaper ~$0.20-0.40/hr
- 8 cores / 16 GB RAM
- 50 GB SSD
- 100 Mbit/s network (slow image pull but acceptable)

---

## vast.ai search command

```bash
# Preferred: RTX 4090
vastai search offers \
  'gpu_name=RTX_4090 num_gpus=1 reliability>0.95 disk_space>=80 \
   cpu_ram>=32 inet_down>=500 cuda_max_good>=12.6 \
   rentable=true rented=false' \
  --order dph_total
```

Replace `RTX_4090` with `RTX_3090` for economy.

`dph_total` orders by total dollars-per-hour (lowest first), surfacing
the cheapest matching offers.

## vast.ai provision command (one-time after picking an offer)

```bash
# Get OFFER_ID from the search result above
OFFER_ID=<numeric id from search>

vastai create instance "$OFFER_ID" \
  --image ghcr.io/a3ka/uav-lab:gpu \
  --disk 80 \
  --label uav-phase1-poo \
  --env '-e HOST_UID=1000 -e HOST_GID=1000' \
  --jupyter false \
  --ssh true
```

`--image ghcr.io/a3ka/uav-lab:gpu` causes vast.ai to pull our pre-pushed
image. If the GHCR image is private (default), see the "private image"
section below.

---

## Private GHCR image — login on the rental

GHCR repos default to private. Two paths:

### Path A: make the image public (simpler)

After our first push:
```bash
gh api -X PATCH /user/packages/container/uav-lab/visibility -f visibility=public
```
vast.ai instances then pull anonymously.

The image contains no secrets — only system packages + framework. Public
is fine.

### Path B: keep private, login on rental

Provision the instance, SSH in, then:
```bash
echo "$GHCR_PAT" | docker login ghcr.io -u a3ka --password-stdin
docker pull ghcr.io/a3ka/uav-lab:gpu
```
Requires copying the PAT to the instance via the `--env` flag or
manually. Reusable across rentals.

Recommendation: **Path A for first Phase 1 rental, Path B if we add
sensitive content later.**

---

## Once-rental setup (inside the instance, after SSH)

```bash
# 1. (only if private image) docker login to GHCR
echo "$GHCR_PAT" | docker login ghcr.io -u a3ka --password-stdin

# 2. Pull the image (skipped if vast.ai pre-pulled via --image)
docker pull ghcr.io/a3ka/uav-lab:gpu

# 3. Clone our source
git clone https://github.com/a3ka/uav-gazebo-lab.git ~/uav-gazebo-lab
git clone --depth 1 https://github.com/PX4/px4_msgs.git ~/px4_msgs
# PX4-Autopilot only needed for Phase 6+; Phase 1 doesn't need PX4
# git clone --recursive --depth 1 --branch main https://github.com/PX4/PX4-Autopilot.git ~/PX4-Autopilot

# 4. Stage Zurich Z16 dataset (re-tar locally then scp, ~11 MB)
# OR re-download from einhard-runtime (private repo — needs token).
# For Phase 1 the tile count is small enough to scp from local:
#   scp -r -P <PORT> /home/nous/research/uav-gazebo-lab/datasets/staged/ root@<host>:/root/datasets/

# 5. Launch container, mount source + datasets
docker run --rm -it --gpus all \
    -v ~/uav-gazebo-lab:/workspace/uav-gazebo-lab \
    -v ~/px4_msgs:/workspace/px4_msgs \
    -v ~/datasets:/datasets \
    -v ~/workspaces:/run-data \
    -e HOST_UID=1000 -e HOST_GID=1000 \
    --net=host --ipc=host \
    ghcr.io/a3ka/uav-lab:gpu

# 6. Inside the container:
cd /workspace/uav-gazebo-lab
mkdir -p /workspace/ros2_ws/src
ln -sf ../../px4_msgs /workspace/ros2_ws/src/
ln -sf ../../uav-gazebo-lab/src/uav_swarm_msgs /workspace/ros2_ws/src/
ln -sf ../../uav-gazebo-lab/src/uav_swarm_nodes /workspace/ros2_ws/src/
bash scripts/build-ros2-ws.sh

# 7. Smoke-test SuperPoint on GPU
bash scripts/smoke-superpoint.sh gpu

# 8. Run Phase 1 campaign
python3 scripts/phase1-poo-trials.py \
    --dataset /datasets/staged/zurich-z16 \
    --out /run-data/phase1-trials.csv \
    --n-honest 500 --n-byzantine 500 --seed 42

# 9. Extract results to local before destroying instance:
#   scp -P <PORT> root@<host>:/root/workspaces/phase1-trials.csv ./
```

---

## Cleanup (destroy instance)

```bash
# Confirm no important files remain on the instance
ssh root@<host> -p <PORT> "ls /root/workspaces"

# Destroy
vastai destroy instance <INSTANCE_ID>
```

Instance disk is wiped on destroy. Persistent volumes cost
~$0.10/GB-month; not used for Phase 1 — rebuild from image + git clone
each session.

---

## Cost estimate for Phase 1

| Item | Quantity | Rate | Cost |
|---|---|---|---|
| RTX 4090 rental | ~30-60 GPU-hr | $0.40-0.80/hr | $12-48 |
| Storage (no persistent volume) | 0 GB-mo | $0.10/GB-mo | $0 |
| Network egress (results download) | < 100 MB | free | $0 |
| **Phase 1 total** | | | **$12-48** |

Budget envelope (per docs/cost-budget.md): $15-50 for Phase 1. We're in
range.
