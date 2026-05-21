# docker/ — container workflow for uav-gazebo-lab

All development happens inside containers. The host machine is never
expected to have ROS2, Gazebo, PX4, or GTSAM installed directly.

This is a hard rule (see `../CLAUDE.md`). It exists because:
1. The toolchain is heavy (~6-10 GB system packages).
2. Local dev (Phase 0/4/5) and vast.ai rental (Phase 1/2/3) must run
   identical environments — only containers guarantee that.
3. Re-creating the dev environment from scratch must take one command,
   not one afternoon.

---

## Image map

| Image | Built from | Size | Used for |
|---|---|---|---|
| `uav-lab:cpu` | `Dockerfile.cpu` | ~3-4 GB | Phase 0 bootstrap, Phase 4 failover, Phase 5 GNSS spoofing, all headless dev locally |
| `uav-lab:gpu` | `Dockerfile.gpu` | ~10 GB | Phase 1 PoO, Phase 2 reputation loop, Phase 3 CEP+relay — vision-heavy work on vast.ai |

Both share: ROS2 Jazzy + Gazebo Harmonic + ros_gz_bridge + uXRCE-DDS
agent + PX4 build deps + GTSAM 4.2.

GPU adds: CUDA 12.4 runtime + cuDNN + PyTorch CUDA + Kornia + LightGlue.

---

## Volumes and bind mounts

| Mount | Purpose | Persistence |
|---|---|---|
| `/workspace/uav-gazebo-lab` | Project source (bind from host) | Lives on host, edit with host IDE |
| `/workspace/PX4-Autopilot` | PX4 source (bind from sibling dir, cloned by `scripts/bootstrap.sh`) | Lives on host |
| `/workspace/ros2_ws` | colcon build artifacts (named volume) | Persists across container restarts; rebuilt per image |
| `/run-data` | Per-run bags + metrics | Bind to host `workspaces/` — visible after run for analysis |
| `/datasets` | Sentinel-2 staged imagery | Bind to host `datasets/` — survives container destruction |

PX4 builds inside the container but writes artifacts to the bind-
mounted `/workspace/PX4-Autopilot` so they persist on host. First PX4
build is ~1 hour; subsequent incremental builds are seconds.

---

## Local CPU workflow

```bash
cd /home/nous/research/uav-gazebo-lab

# One-time: build the CPU image
docker compose --profile cpu build

# Start a dev container (interactive shell)
docker compose --profile cpu run --rm dev

# Inside container:
lab@host:/workspace/uav-gazebo-lab$ ros2 topic list
lab@host:/workspace/uav-gazebo-lab$ gz sim --version
lab@host:/workspace/uav-gazebo-lab$ scripts/bootstrap.sh    # Phase 0 setup
```

`--net=host` + `--ipc=host` are set in compose so ROS2 DDS auto-
discovery and Gazebo transport work without extra config. Multi-vehicle
PX4 SITL inside the container uses different UDP ports per instance.

---

## vast.ai GPU workflow

```bash
# One-time on dev machine: build + push GPU image
docker compose --profile gpu build
docker tag uav-lab:gpu ghcr.io/<you>/uav-lab:gpu
docker push ghcr.io/<you>/uav-lab:gpu

# Per rental: provision instance with the image
vastai create instance OFFER_ID \
    --image ghcr.io/<you>/uav-lab:gpu \
    --disk 80 \
    --label uav-phase1-poo

# Once running, ssh in, then run experiment scripts.
# After completion, rsync /run-data back to host before destroying.
```

Image pull on vast.ai: ~5-10 min depending on region and image registry
pull speed.

---

## Image build size reduction (later optimisation)

Current Dockerfiles install full Ubuntu development environments
(build-essential, full LaTeX is not included but PX4 deps are heavy).
If image size becomes a problem:

- Multi-stage build: install builders + GTSAM build in a builder stage,
  copy only artifacts to final image (saves ~1.5 GB).
- Strip `apt-get install -y` package recommends more aggressively.
- Split PX4 build deps into a separate "px4-build" image used only at
  PX4 build time.

Do this only if push-pull time on vast.ai becomes a bottleneck.

---

## What lives WHERE

| Concept | Inside container | On host | Notes |
|---|---|---|---|
| Source code | `/workspace/uav-gazebo-lab` (bind) | `~/research/uav-gazebo-lab/` | Single source of truth, edit on host |
| PX4 source | `/workspace/PX4-Autopilot` (bind) | sibling of project dir | Cloned by `scripts/bootstrap.sh` |
| Compiled ROS2 packages | `/workspace/ros2_ws/install/` (volume) | docker volume `ros2_ws` | Rebuild after image rebuild |
| Compiled PX4 | `/workspace/PX4-Autopilot/build/` | bind | Persists across container restarts |
| Run data (bags, metrics) | `/run-data/<run-id>/` | `workspaces/<run-id>/` (bind) | Visible to host analysis tools |
| Sentinel-2 imagery | `/datasets/staged/` | `datasets/staged/` (bind) | Staged once, reused across phases |
| Python venvs | nowhere (uses system python3 from container) | — | Don't create venvs inside containers — image is the venv |

---

## When to update the Dockerfiles

- A new system dep is needed by the validation code → add to apt-get block
- A new Python lib is needed → add to pip install block
- A new ROS2 package is needed → add to apt-get with `ros-jazzy-*` prefix

After any Dockerfile change: `docker compose --profile <p> build` to rebuild.
Pushed image must be re-pushed before next vast.ai rental.
