# bft-uav-validation-lab

**Empirical validation testbed for a Byzantine-fault-tolerant cooperative
navigation architecture for UAV swarms operating in GNSS-denied
environments.**

This repository is the companion to the IEEE Access manuscript
*"Byzantine-Fault-Tolerant Hierarchical Navigation for GNSS-Denied UAV
Swarms: Architecture, Theoretical Analysis, and Empirical Validation"*
(Kalynovskyi, 2026). Every numerical claim in Section VI (Empirical
Validation) and Section VII (Baseline Comparison) of the paper traces to
a specific raw-data file in [`workspaces/`](workspaces/), via the
explicit map in [`CODE_TO_CLAIM_MAPPING.md`](CODE_TO_CLAIM_MAPPING.md).

> If you've arrived here without the paper: this is **scientific
> reproducibility infrastructure**, not a turnkey UAV product. It runs
> simulated UAVs in ROS 2 + Gazebo + a Python single-process harness,
> applies a Byzantine adversary, and measures whether the proposed
> protocol correctly excludes the adversary and keeps the swarm
> navigating. See the "What this is" section below for the 60-second
> orientation.

---

## What this is

In one paragraph: cooperative UAV swarms that share position estimates
over UWB radio links are vulnerable to a single "Byzantine" peer — a
captured, sensor-faulted, or maliciously-firmwared vehicle — that
transmits falsified position data and corrupts everyone else's
navigation solution. The published manuscript proposes an architecture
that combines six defences (terrain-referenced trust, asymmetric
reputation, dynamic anchor election, automatic failover, GNSS-spoofing
cross-verification, capacity-aware load balancing) at the
factor-graph state-estimation layer. **This repository is the validation
testbed** that empirically measures whether each of those six pillars
actually does what the theory predicts, end-to-end, in a flight-realistic
simulator. The eight-phase validation campaign produced 250 + 30 + 1200
+ 60 + 15 + 30 + 20 trial-level measurements; the headline numbers are
summarised below and every one of them is back-traceable to a CSV in
this repo.

## What this is NOT

- **Not a turnkey product.** No autopilot integration, no flight tests,
  no hardware. The validation runs in Gazebo + PX4 SITL (software in the
  loop) plus a Python single-process harness. Real-vehicle deployment is
  a separate engineering effort.
- **Not an LLM / AI research project.** No language models in any
  experimental loop. LLM assistance was used to write the supporting
  code (disclosed in the paper's AI Disclosure section), but every
  measurement was produced by deterministic ROS 2 / Python execution.
- **Not a general-purpose swarm SDK.** The 18 ROS 2 nodes are
  paper-specific implementations of the six pillars and the validation
  harness; they are not framework primitives for arbitrary swarm
  applications.

## TL;DR results (the eight phases)

Each row links to the workspace directory containing the raw production
sweep data and to the per-phase reproducibility document.

| # | Phase | What it measures | Headline number | Data |
|---|---|---|---|---|
| 1 | Proof-of-Observation | Visual terrain verification true/false-rate | AUC = 0.9996 (FAR/FRR at two operating points) | [`workspaces/phase1-sweep/`](workspaces/phase1-sweep/) · [doc](docs/results/phase-1.md) |
| 2 | Reputation-driven exclusion | Byzantine peer permanent exclusion | 30/30 trials, **0 false honest exclusions** | [`workspaces/phase2-batch/`](workspaces/phase2-batch/) · [doc](docs/results/phase-2.md) |
| 3 | CEP vs relay depth | Multi-hop position-error growth | CEP = 23 m at 3 relay hops (4× inside NATO 100-m ceiling) | [`workspaces/phase3-prod-v4/`](workspaces/phase3-prod-v4/) · [doc](docs/results/phase-3.md) |
| 4 | Automatic failover | Time to recover after anchor loss | p99 = 6.24 s across 1200 follower switches | [`workspaces/phase4-prod/`](workspaces/phase4-prod/) · [doc](docs/results/phase-4.md) |
| 5 | GNSS-spoof detection | Detect a spoofed vehicle via UWB cross-check | 98.3 % detection, 0 false positives, p99 = 0.60 s | [`workspaces/phase5-prod/`](workspaces/phase5-prod/) · [doc](docs/results/phase-5.md) |
| 6 | Progressive attrition | Survive losing anchors mid-mission | 14/15 missions survive with capacity invariant strictly held | [`workspaces/phase6-tier-b-prod-v3/`](workspaces/phase6-tier-b-prod-v3/) · [doc](docs/results/phase-6.md) |
| 7 | Single-pillar ablation | Which pillars are strictly necessary | TRN ablation degrades CEP by 32–117 % depending on hop depth | [`workspaces/phase7-abl{1,2,3}-*` + `phase7-abl4-notrn-v4/`](workspaces/) · [doc](docs/results/phase-7.md) |
| 8 | Vanilla-Raft baseline + Byzantine | Cost of Byzantine resilience vs crash-fault tolerance | Raft compromised indefinitely by 1 Byzantine; our protocol excludes in < 0.6 s | [`workspaces/phase8-prod/`](workspaces/phase8-prod/) · [doc](docs/results/phase-8.md) |

---

## Try it in 5 minutes (Docker)

If you just want to **see one experiment run** and verify a paper
number, this is the minimum path. You need Docker installed (no other
dependencies).

```bash
# 1. Clone this repo.
git clone https://github.com/ok-research/bft-uav-validation-lab.git
cd bft-uav-validation-lab

# 2. Pull the pre-built CPU image (~5 GB, one-time download; contains
#    ROS 2 Jazzy + Gazebo Harmonic + GTSAM + Python ready to run).
docker pull ghcr.io/a3ka/uav-lab:cpu

# 3. Run a fast sanity check inside the container — verifies that the
#    factor-graph state estimator converges from a 200-m initial
#    error to <1 m given three tight anchor priors. Takes ~30 seconds.
docker run --rm -v $PWD:/workspace/uav-gazebo-lab \
  ghcr.io/a3ka/uav-lab:cpu \
  bash -c 'source /opt/ros/jazzy/setup.bash &&
           source /workspace/uav-gazebo-lab/ros2_ws/install/setup.bash 2>/dev/null;
           cd /workspace/uav-gazebo-lab &&
           bash scripts/smoke-factor-graph.sh'

# 4. Verify the paper's headline CEP number against the stored data
#    (no Docker needed for this; just jq).
jq '.per_k[3].cep50_median' workspaces/phase3-prod-v4/analysis.json
# → 23.328   (Paper §VI-C reports "23 m at k=3"; this is the source value.)
```

If you got `23.328` from step 4, you have independently verified one
paper-claim against the released raw data. The same pattern works for
every number in §VI/§VII — see
[`CODE_TO_CLAIM_MAPPING.md`](CODE_TO_CLAIM_MAPPING.md) for the full
table of jq queries.

---

## Why this repository looks the way it does

If you came here cold, the directory tree may look intimidating: 18 ROS
nodes, 18 message types, ~47 shell scripts, 14 workspace directories,
two Docker images. Here is the rationale.

### Why "phases"?

The paper makes claims about six **architectural pillars**, plus a
baseline comparison. Each claim needs its own controlled experiment to
isolate it from the others. We label these experiments **Phase 1**
through **Phase 8** (the lab's internal numbering; the paper presents
them grouped by pillar rather than by phase number). The phases are
sequenced so that downstream phases reuse the validated components of
upstream ones:

- Phase 1 validates the trust primitive (Proof of Observation).
- Phase 2 reuses Phase 1's primitive to validate reputation-driven exclusion.
- Phase 3 measures position error under reputation-weighted multi-hop relay.
- Phase 4 measures anchor-failover latency.
- Phase 5 measures GNSS-spoof detection time.
- Phase 6 measures whole-mission survival under progressive attrition.
- Phase 7 ablates each pillar in turn to confirm necessity.
- Phase 8 compares against a crash-fault-tolerant baseline (vanilla
  Raft) and exposes the BFT-vs-CFT capability gap.

Each phase has a written specification in [`docs/`](docs/), a runner
script in [`scripts/`](scripts/), and an output workspace in
[`workspaces/`](workspaces/).

### Why ~47 shell scripts?

Scripts fall into three categories:

- **Sweep campaigns** (`scripts/phase{N}-batch-campaign.sh` and
  `scripts/phase{N}-campaign.sh`) orchestrate a full production sweep
  for a phase: spawn N trials, vary the parameter of interest,
  parallelise across CPU cores via `JOBS=8` or similar. Each writes its
  output to a workspace directory and is meant to be re-runnable
  end-to-end (`workspaces/<sweep>/` is overwritten at startup).
- **Analyzers** (`scripts/phase{N}-analyze.py`) compute aggregate
  statistics from a sweep's raw CSV → `analysis.json` summary used
  throughout the paper.
- **Smoke tests** (`scripts/smoke-*.sh`) are fast (< 2 min each)
  individual-component sanity checks — e.g., "does the factor graph
  converge?", "does the reputation manager exclude a bad peer?", "does
  the failover protocol kick in when an anchor is killed?". They are
  the unit-tests of this lab.

The proliferation reflects the **discipline** of validating each pillar
independently. There is no shortcut that combines Phase 1 + Phase 5 +
Phase 8 into a single mega-script; that would defeat the
isolation-of-mechanism that the experiments rely on.

### Why Docker (and why two images)?

The stack — ROS 2 Jazzy, Gazebo Harmonic, PX4 main, GTSAM 4.2,
SuperPoint feature extractor with CUDA — is not trivial to install on a
researcher's host machine, and any installation drift makes
reproducibility impossible. Docker freezes the entire stack into an
image. Pull once; run anywhere. **Your host machine never gets these
packages directly**, which also means your host gets back its package
manager.

We provide two images because the cost profile of the eight phases
differs:

- **`uav-lab:cpu`** is headless (no display, no CUDA). It runs Phases
  3, 4, 5, 6, 7, 8 — all the system-level protocol validations. Boots
  on any Linux/macOS/Windows machine with Docker.
- **`uav-lab:gpu`** adds CUDA and the SuperPoint vision pipeline.
  Required only for Phases 1 and 2 (Proof-of-Observation FAR/FRR sweep
  + reputation exclusion). A single Phase 1 production sweep costs about
  one US dollar of vast.ai GPU rental.

Splitting the images keeps the routine local development cheap and
isolates the GPU-only work into a separate environment.

Recipes in [`docker/Dockerfile.cpu`](docker/Dockerfile.cpu) and
[`docker/Dockerfile.gpu`](docker/Dockerfile.gpu). Published as
[`ghcr.io/a3ka/uav-lab:cpu`](https://ghcr.io/a3ka/uav-lab) and `:gpu`.

### Why 18 ROS 2 nodes + 18 messages?

Each pillar of the architecture maps to one or two nodes (anchor,
follower, reputation manager, factor graph, verifier, quorum exclusion,
spoof detector, attrition orchestrator, load monitor, Raft, …). Messages
match the pillars (signed observations, reputation updates, distilled
state, failover request/offer/ack, raft heartbeat, …). Both lists are
in [`src/uav_swarm_msgs/msg/`](src/uav_swarm_msgs/msg/) and
[`src/uav_swarm_nodes/`](src/uav_swarm_nodes/uav_swarm_nodes/) with one
file per item.

---

## Reproducing the paper end-to-end

The fast path above verifies one number. A full end-to-end reproduction
re-runs every production sweep from scratch and re-derives every paper
table. Total wall-time:

| Phase | Sweep wall-time | Hardware |
|---|---|---|
| 1 | ~30 min | vast.ai GPU |
| 2 | ~10 min | vast.ai GPU |
| 3 | ~28 min | local CPU (`JOBS=8`) |
| 4 | ~25 min | local CPU (`JOBS=4`) |
| 5 | ~20 min | local CPU (`JOBS=2`) |
| 6 (Tier B) | ~17 min | local CPU (`JOBS=2`) |
| 7 (4 ablations) | ~30 min | local CPU |
| 8 | ~5 min | local CPU |
| **Total** | **~3 hr** | mostly local CPU; ~$1 GPU rental for Phases 1–2 |

The canonical command for each phase is in
[`CODE_TO_CLAIM_MAPPING.md`](CODE_TO_CLAIM_MAPPING.md) ("Re-sweep:"
line at the bottom of each phase section).

Reproducibility pins (Docker image digest, git commit at sweep start,
manifest of sweep parameters) are recorded in
[`docs/results/phase-{1..8}.md`](docs/results/). These let you reproduce
*the specific sweep that produced the published numbers*, not just any
sweep with the same nominal parameters.

---

## Directory tour

```
bft-uav-validation-lab/
├── README.md                              ← you are here
├── LICENSE                                ← MIT
├── CODE_TO_CLAIM_MAPPING.md               ← every paper number → jq query mapping
├── .env.example                           ← template for Copernicus + vast.ai credentials
├── .gitignore, .dockerignore              ← what NOT to ship (artefacts, secrets)
│
├── docker/
│   ├── Dockerfile.cpu                     ← uav-lab:cpu recipe (ROS 2 + GTSAM + Gazebo)
│   ├── Dockerfile.gpu                     ← uav-lab:gpu recipe (adds CUDA + SuperPoint)
│   ├── docker-compose.yml                 ← optional compose orchestration
│   ├── requirements-px4.txt               ← PX4 SITL build dependencies
│   └── README.md                          ← Docker build notes
│
├── docs/
│   ├── VALIDATION_PLAN.md                 ← the locked 9-phase plan + stack lock
│   ├── poo-algorithm-spec.md              ← Phase 1 algorithm spec (PoO threshold + descriptors)
│   ├── phase-{2..8}-spec.md               ← per-phase experimental spec
│   └── results/phase-{1..8}.md            ← per-phase reproducibility pins + outcomes
│
├── src/
│   ├── uav_swarm_msgs/                    ← 18 ROS 2 .msg definitions + CMakeLists + package.xml
│   └── uav_swarm_nodes/                   ← 18 ROS 2 nodes + setup.py + package.xml
│
├── scripts/
│   ├── build-px4.sh                       ← build PX4 SITL inside container
│   ├── build-ros2-ws.sh                   ← colcon build the workspace
│   ├── cleanup-host.sh                    ← kill stray Gazebo / PX4 / DDS daemons
│   ├── phase{N}-*.{sh,py}                 ← per-phase campaign + analyzer + scenario-runner
│   └── smoke-*.sh                         ← fast component sanity checks
│
├── workspaces/                            ← production sweep raw data (14 sweeps total)
│   ├── phase1-sweep/                      ← Phase 1 PoO sweep — 11 CSVs (500 trials each)
│   ├── phase2-batch/                      ← Phase 2 exclusion — 30 trials × 2 CSV per trial
│   ├── phase3-prod-v4/                    ← Phase 3 CEP — 250 trials × 5 hop depths
│   ├── phase3-baseline-v3-50/             ← Phase 7 ABL4 with-TRN paired baseline (50 trials)
│   ├── phase4-prod/                       ← Phase 4 failover — 1200 follower switches
│   ├── phase5-prod/                       ← Phase 5 spoof detection — 30 trials × 2 victims
│   ├── phase6-tier-b-prod/                ← Phase 6 baseline (no admission control)
│   ├── phase6-tier-b-prod-v3/             ← Phase 6 with admission control (final)
│   ├── phase7-abl{1,2,3}-*                ← single-pillar ablations
│   ├── phase7-abl4-notrn-v4/              ← Phase 7 no-TRN ablation (50-trial paired)
│   ├── phase7-sparse-chain/               ← Phase 7 single-relay-per-hop ablation
│   └── phase8-prod/                       ← Phase 8 vanilla-Raft + Byzantine adversarial
│
```

Files in each workspace follow the convention:

- `manifest.json` — exact parameters of the sweep (seed_base, k_list,
  trials_per_k, sigma_*, JOBS, wall-time, git commit at start)
- `sweep.csv` or `results.csv` — per-trial raw measurements
- `analysis.json` — aggregate statistics consumed by the paper
- `*.png` — diagnostic plots (where applicable)

---

## FAQ

**Q: I just want to cite the dataset / code. What's the DOI?**
A: See the Citation section below. The Zenodo DOI is auto-assigned per
tagged release; the latest release is always linked from the GitHub
[Releases](https://github.com/ok-research/bft-uav-validation-lab/releases)
page.

**Q: Can I reproduce the paper without a GPU?**
A: Yes for Phases 3-8 (CPU-only). Phases 1 and 2 use the SuperPoint
vision pipeline and need a GPU; the cheapest path is a vast.ai RTX
rental (~$1 for one full Phase 1 sweep). The released `phase1-sweep/`
and `phase2-batch/` workspaces contain the already-computed raw data so
GPU re-runs are optional.

**Q: Why are some sweeps "v3" or "v4"? What was v1?**
A: Earlier iterations of certain sweeps used scaffold-only or smaller
sample sizes that introduced sampling artefacts (e.g., the original
Phase 3 v1 sweep reported CEP = 0.47 m which is physically impossible
given the sensor noise floor). These superseded versions are not
included in this release; only the final production sweeps cited by the
paper are shipped. See the per-phase results docs for the iteration
history and the rationale for each version bump.

**Q: I want to add a seventh pillar / a new experiment / hardware
integration. How?**
A: This repo is the *paper-validation* lab and is frozen at the paper's
tagged release. Forking is encouraged; the architecture is documented
end-to-end in `docs/VALIDATION_PLAN.md` and the per-phase specs.

**Q: Why does the paper reference a separate
`bft-uav-swarm-validation` repo too?**
A: That sibling repo
([ok-research/bft-uav-swarm-validation](https://github.com/ok-research/bft-uav-swarm-validation),
tag `v1.1`) contains the three abstract Monte Carlo simulators of paper
Sections VIII–X (asymmetric reputation decay, Byzantine-exclusion clamp
convergence, Byzantine-fraction resilience). They predate this lab and
are kept separate because their methodology (single-process Python
abstract simulators, no ROS 2 / no flight dynamics) differs from the
flight-realistic Gazebo + PX4 stack here.

**Q: Are the patents going to restrict my use of this code?**
A: No. The MIT licence on this code grants the standard MIT permissions
unconditionally. The pending DPMA patents cover the *methods* described
in the paper for commercial deployment of the system, not the use of
this validation testbed for research or reproduction. See the Patent
section at the bottom of this README.

**Q: Why is there a `CLAUDE.md` mentioned somewhere?**
A: It is not in this release. The lab's internal development used an
AI-assistant project-conventions file (`CLAUDE.md`) which was kept
private to the development environment. The AI Disclosure in the paper
covers the actual usage scope.

---

## Boundary rules (for contributors)

If you fork and extend, these are the three rules the lab follows:

1. **No LLM-in-the-loop experiments.** Every measurement here was
   produced by deterministic ROS 2 / Python code. LLM assistance for
   code generation and analysis is fine; injecting an LLM into the
   measurement loop is not (it breaks reproducibility audit).
2. **Reproducibility-first.** Every paper claim must trace to a
   workspace file via [`CODE_TO_CLAIM_MAPPING.md`](CODE_TO_CLAIM_MAPPING.md).
   If a number changes, re-run the sweep; do not estimate.
3. **Two-tier validation by design.** Gazebo + PX4 SITL for N ≤ 50
   mechanism validation; Python single-process harness at N = 200 for
   statistical characterisation. 200-UAV Gazebo runs are computationally
   infeasible on a single workstation and are reviewer-naive proposals
   that should be redirected to the two-tier methodology.

See [`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md) for the full
per-phase specification, pass criteria, and stack-lock list.

---

## Citation

If you use this lab in your work, please cite both the paper and the
specific code release:

> O. Kalynovskyi, "Byzantine-Fault-Tolerant Hierarchical Navigation for
> GNSS-Denied UAV Swarms: Architecture, Theoretical Analysis, and
> Empirical Validation," *IEEE Access*, 2026 (submitted).

> O. Kalynovskyi, "bft-uav-validation-lab vX.Y.Z — Empirical validation
> testbed for BFT UAV swarm navigation," Zenodo, 2026,
> doi: 10.5281/zenodo.NNNNNNN.
>
> *(replace `vX.Y.Z` and `NNNNNNN` with the latest tagged release; see the
> [Releases](https://github.com/ok-research/bft-uav-validation-lab/releases)
> page for the current version, or the concept-DOI which always resolves
> to the latest version.)*

---

## Licence

MIT — see [LICENSE](LICENSE). You may use, modify, distribute, and
commercialise this code without further permission; please retain the
copyright notice.

---

## Companion patent applications

The architecture and methods this lab validates are the subject of
pending patent applications filed at the German Patent and Trademark
Office (DPMA) in April 2026, Aktenzeichen 10 2026 001 712.2 and a
related filing. This public release is the academic-disclosure
companion to those filings. The MIT licence on this code grants
permission to use the code itself; the patent claims cover the *methods*
for commercial deployment of the system. Researchers reproducing the
paper for academic purposes are unaffected.

---

## Contact

Oleksandr Kalynovskyi · kalinovsky.research@proton.me · ORCID
[0009-0009-1437-3252](https://orcid.org/0009-0009-1437-3252)

For research questions, replication assistance, or bug reports, please
open an issue on the
[GitHub issues page](https://github.com/ok-research/bft-uav-validation-lab/issues).
