# bft-uav-validation-lab

Empirical validation testbed for the IEEE Access manuscript
**"Byzantine-Fault-Tolerant Hierarchical Navigation for GNSS-Denied UAV Swarms:
Architecture, Theoretical Analysis, and Empirical Validation"** (Kalynovskyi, 2026).

## Contents

This repository is the companion code release for Section VI (Empirical Validation,
seven phases) and Section VII (Baseline Comparison) of the paper. It contains the
ROS 2 + Gazebo + Python harness, sweep configurations, production-sweep raw data,
and per-phase analysis scripts used to produce every numerical claim in those
sections.

The three abstract Monte Carlo simulators of paper Sections VIII–X live in a
separate companion repository:
[ok-research/bft-uav-swarm-validation](https://github.com/ok-research/bft-uav-swarm-validation)
at tag `v1.1`.

## Reproducibility status

All headline numbers in paper §VI/§VII trace to a specific workspace directory
under `workspaces/`. The mapping is documented in
[`CODE_TO_CLAIM_MAPPING.md`](CODE_TO_CLAIM_MAPPING.md).

| Phase | Status | Headline number | Workspace |
|---|---|---|---|
| 1 — Proof-of-Observation | done | AUC = 0.9996 (FAR/FRR @ ROC operating points) | `workspaces/phase1-sweep/` |
| 2 — Reputation-driven exclusion | done | 30/30 trials, 0 false honest exclusions | `workspaces/phase2-batch/` |
| 3 — CEP vs relay depth | done | CEP = 23 m at k = 3, empirical δ = 0.088 | `workspaces/phase3-prod-v4/` |
| 4 — Failover timing | done | p99 = 6.24 s across 1200 follower switches | `workspaces/phase4-prod/` |
| 5 — GNSS-spoofing detection | done | 98.3 % detection, 0 FP, p99 = 0.60 s | `workspaces/phase5-prod/` |
| 6 — Progressive attrition | done | 14/15 mission survival with admission control; capacity invariant strict | `workspaces/phase6-tier-b-prod{,-v3}/` |
| 7 — Single-pillar ablation | done | TRN strictly necessary (50-trial paired sweep) | `workspaces/phase7-abl{1..4,4-notrn-v4}/` |
| 8 — Vanilla-Raft baseline + Byzantine | done | Raft compromised under 1 Byzantine; ours excludes in < 0.6 s | `workspaces/phase8-prod/` |

## Stack

| Component | Version |
|---|---|
| Ubuntu | 24.04 Noble |
| ROS 2 | Jazzy Jalisco |
| Gazebo Sim | Harmonic v8.x |
| PX4 Autopilot | main (≥ v1.15) |
| uXRCE-DDS Agent | latest |
| GTSAM | 4.2+ |
| Python | 3.12 |

All dependencies are containerised via Docker. The host machine never gets these
packages directly. Two images are used:

- `uav-lab:cpu` — Phases 0, 3, 4, 5, 6, 7, 8 (headless, local CPU)
- `uav-lab:gpu` — Phases 1, 2 (vision pipeline, vast.ai GPU rental)

Recipes in `docker/Dockerfile.{cpu,gpu}`. Published images:
[`ghcr.io/a3ka/uav-lab:gpu`](https://ghcr.io/a3ka/uav-lab) (and `:cpu`).

## Quick reproduction

```bash
# 1. Container entry (CPU phases)
docker run --rm -it \
  -v $PWD:/workspace/uav-gazebo-lab \
  -v $PWD/../ros2_ws:/workspace/ros2_ws \
  uav-lab:cpu bash

# Inside container, every shell:
source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash

# 2. Build ROS2 workspace (one-time)
bash /workspace/uav-gazebo-lab/scripts/build-ros2-ws.sh

# 3. Re-run a phase's production sweep (example: Phase 3)
JOBS=8 bash scripts/phase3-batch-campaign.sh
# Wall time: ~28 min on CPU.

# 4. Re-analyse without re-sweeping
python3 scripts/phase3-analyze.py --csv workspaces/phase3-prod-v4/sweep.csv \
                                   --out workspaces/phase3-prod-v4/analysis.json

# 5. Verify a paper claim against workspace data
jq '.per_k[3].cep50_median' workspaces/phase3-prod-v4/analysis.json
# → 23.328 (matches paper §VI-C Table tab:cep_measured)
```

Per-phase reproducibility pins (Docker image digest, git commit at sweep
start, manifest of sweep parameters) are in `docs/results/phase-{1..8}.md`.

## Directory layout

```
bft-uav-validation-lab/
├── README.md                            ← this file
├── LICENSE                              ← MIT
├── CODE_TO_CLAIM_MAPPING.md             ← paper-claim → workspace-file map
├── docs/
│   ├── VALIDATION_PLAN.md               ← locked 9-phase plan + stack
│   ├── phase-{2..8}-spec.md             ← per-phase specs
│   ├── poo-algorithm-spec.md            ← Phase 1 algorithm spec
│   ├── results/phase-{1..8}.md          ← per-phase results docs (reproducibility pins)
│   └── reference/                       ← frozen paper versions for diff reference
├── docker/
│   ├── Dockerfile.cpu                   ← uav-lab:cpu recipe
│   ├── Dockerfile.gpu                   ← uav-lab:gpu recipe
│   ├── docker-compose.yml
│   └── requirements-px4.txt
├── src/
│   ├── uav_swarm_msgs/msg/              ← 18 ROS 2 message definitions
│   └── uav_swarm_nodes/                 ← 18 ROS 2 nodes (anchor, follower, …)
├── scripts/
│   ├── phase{1..8}-*.{py,sh}            ← per-phase sweep + analysis scripts
│   ├── smoke-*.sh                       ← fast (< 2 min) sanity checks
│   ├── build-px4.sh, build-ros2-ws.sh
│   └── cleanup-host.sh
├── workspaces/                          ← production-sweep raw data
│   ├── phase1-sweep/                    ← Phase 1 PoO sweep
│   ├── phase2-batch/                    ← Phase 2 reputation exclusion 30 trials
│   ├── phase3-prod-v4/                  ← Phase 3 CEP final (250 trials)
│   ├── phase3-baseline-v3-50/           ← Phase 7 ABL4 baseline (50-trial paired)
│   ├── phase4-prod/                     ← Phase 4 failover 1200 measurements
│   ├── phase5-prod/                     ← Phase 5 spoof detection
│   ├── phase6-tier-b-prod{,-v3}/        ← Phase 6 attrition (no-AC + with-AC)
│   ├── phase7-abl{1,2,3}-*              ← Ablations 1-3
│   ├── phase7-abl4-notrn-v4/            ← Ablation 4 no-TRN (50-trial)
│   ├── phase7-sparse-chain/             ← m_relay=1 sparse ablation
│   └── phase8-prod/                     ← Vanilla-Raft baseline + Byzantine
└── configs/                             ← Phase configuration JSONs
```

## Boundary rules

This is a measurement project, not a discovery project.

1. **No LLM-in-the-loop experiments.** Every number under `workspaces/*/`
   was produced by deterministic ROS 2 / Python code. LLM assistance was
   used for code generation and analysis but never to fabricate measured
   data.
2. **Reproducibility-first.** Every paper claim must trace to a workspace
   file via the `CODE_TO_CLAIM_MAPPING.md` table. If a number changes,
   re-run the sweep; do not estimate.
3. **Two-tier validation by design.** Gazebo + PX4 SITL for N ≤ 50
   mechanism validation; Python single-process harness at N = 200 for
   statistical characterisation. 200-UAV Gazebo runs are computationally
   infeasible on a single workstation and are reviewer-naive proposals
   that should be redirected to the two-tier methodology.

See `docs/VALIDATION_PLAN.md`
for the per-phase specification and pass criteria.

## Citation

If you use this lab in your work, please cite the paper:

> O. Kalynovskyi, "Byzantine-Fault-Tolerant Hierarchical Navigation for
> GNSS-Denied UAV Swarms: Architecture, Theoretical Analysis, and Empirical
> Validation," *IEEE Access*, 2026 (submitted).

And the code release directly:

> O. Kalynovskyi, "bft-uav-validation-lab v1.0.0 — Empirical validation
> testbed for BFT UAV swarm navigation," Zenodo, 2026,
> doi: 10.5281/zenodo.XXXXXXX (DOI assigned at first tagged release).

## Licence

MIT — see [LICENSE](LICENSE).

## Companion patent applications

The architecture and methods this lab validates are the subject of pending
patent applications filed at the German Patent and Trademark Office (DPMA)
in April 2026, Aktenzeichen 10 2026 001 712.2 and a related filing. This
public release is the academic-disclosure companion to those filings; no
rights in the subject matter are transferred by use of this software.

## Contact

Oleksandr Kalynovskyi · kalinovsky.research@proton.me · ORCID
[0009-0009-1437-3252](https://orcid.org/0009-0009-1437-3252)
