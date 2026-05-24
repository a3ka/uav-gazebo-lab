# uav-gazebo-lab — System Instructions

Track-3 project: **empirical validation testbed** for the BFT UAV Swarm
paper (v9_8 on arXiv). Standalone — does NOT use Sakana for discovery.

Read this file fully before any task. The single source of truth for what
to validate and in what order is `docs/VALIDATION_PLAN.md`. Read that
before starting any phase.

## Project boundary (vs sister projects)

| Project | Purpose | This relationship |
|---|---|---|
| `audit-harness/` (Track 1) | Catches fabrication in finished papers | Audits any papers/preprints we produce here |
| `sakana-lab/` (Track 2) | LLM-driven research discovery | Independent. NOT used here. |
| **`uav-gazebo-lab/` (Track 3)** | **Empirical validation in physics-grounded sim** | This project. |

**Boundary rule:** This project does not use LLMs as part of any
experimental loop. Measurements come from ROS2 / Gazebo / Python code,
not from "the model said so."

## Core principle

Every claim made by this lab is either:
- **MEASURED**: produced by an actual experiment run, raw data preserved,
  measurement code under version control.
- **NOT_MEASURED**: anything else (including educated guesses, paper
  references, expert intuition).

No "approximately validates" or "consistent with." A measurement matches
the paper claim or it doesn't.

## Hard rules

1. **Risk-first phase ordering.** Validate the highest-risk novel
   primitive first (PoO), not the easiest piece. If the highest-risk
   primitive fails, downstream work is wasted — better to know in week 2
   than week 12. See `VALIDATION_PLAN.md` for the locked phase order.

2. **Two-tier scale is by design.** Gazebo for 10-20 UAV mechanism
   validation (high fidelity). Python/GTSAM for 200-UAV statistical
   results (Monte Carlo). 200 UAV in Gazebo is computationally infeasible
   and reviewer-naive plans that propose it should be redirected to this
   document.

3. **Don't redo §VII-IX of the paper.** Abstract Monte Carlo results
   (r=3, convergence bound, f-resilience up to 0.5) are already released
   in v9_8. This lab augments those with physics — never replaces them.
   When uncertain whether a result belongs here or in §VII-IX, default
   to "augment with physics" (i.e. is there a value-add from Gazebo's
   sensor/comm/flight realism that abstract sim can't produce?).

4. **PoO algorithm spec must be locked before Phase 1.** Paper describes
   the PoO concept but does not pin algorithmic choices (SuperPoint vs
   ORB, LightGlue vs ratio-test matching, exact VERIFIED threshold
   function). Phase 1 results would be inconclusive if these decisions
   are made ad-hoc during implementation. Spec lock lives in
   `docs/poo-algorithm-spec.md` and must be reviewed before Phase 1
   code starts.

5. **Hardware target matches phase.** Vision phases (1, 2, 3) require
   GPU and run on vast.ai rentals. Headless phases (0, 4, 5) run on
   local CPU. Don't build the wrong infrastructure — if you find
   yourself implementing camera pipeline on local CPU, stop and check
   the phase's hardware target.

6. **Raw data preservation.** Every Gazebo run writes a complete bag
   file (ros2 bag record -a) AND a structured CSV/JSON of computed
   metrics. Bag files go to `workspaces/<run-id>/bag/`. Metrics go to
   `workspaces/<run-id>/metrics.json`. Both committed to long-term
   storage (not just git — see VALIDATION_PLAN.md storage section).

7. **Expected-outcome explicit in phase spec.** Each phase spec must
   include "what happens if measurement contradicts paper claim?"
   This is not pessimism — Phase 3 specifically expects to discover
   that the conservative GDOP bound (1+0.15)^k is not the physical
   reality (physical decay likely ~√k). Plan the response (paper
   erratum, v10 update with conservative bound retained as worst-case)
   BEFORE running the experiment.

8. **Docker-first development. No host installs.** ROS2, Gazebo, PX4,
   GTSAM, CUDA, PyTorch — all live inside the `uav-lab:cpu` /
   `uav-lab:gpu` images. The host machine never gets these packages
   directly. Local Phase 0/4/5 dev uses the CPU image; vast.ai Phase
   1/2/3 work uses the GPU image. This is what allows local-to-rental
   migration to be one command, not one afternoon. Image definitions
   live in `docker/`. If you find yourself running `apt-get install
   ros-jazzy-*` on the host, stop — that goes in `Dockerfile.cpu`
   instead.

9. **No leaked processes or containers after a test.** Every test
   container runs with `docker run --rm` (auto-removed on exit) and
   without `--pid=host` (so its PID namespace is isolated — all
   in-container processes die when the container exits). Every smoke
   script installs a single-shot trap that kills MicroXRCEAgent / PX4 /
   gz sim explicitly on EXIT/INT/TERM. If a test crashes mid-run, the
   `--rm` flag still cleans the container; if anything escapes (e.g.
   someone runs binaries on the host accidentally),
   `scripts/cleanup-host.sh` is the user-scoped wiper. After a test
   session you should be able to run `docker ps`, `pgrep -u $USER -f
   'bin/px4|MicroXRCEAgent|gz sim'`, and `ss -lnup | grep 8888` and
   see nothing from this lab.

## Stack lock

| Component | Version | Why |
|---|---|---|
| Ubuntu | 24.04 Noble | Already installed; required for Jazzy |
| ROS2 | Jazzy Jalisco | LTS until May 2029; native to Ubuntu 24.04 |
| Gazebo Sim | Harmonic v8.x | LTS; default pairing with Jazzy; already installed |
| PX4 Autopilot | main (>= v1.15) | Native Gazebo Harmonic support |
| uXRCE-DDS Agent | latest | PX4 ↔ ROS2 bridge (replaces older mavros) |
| GTSAM | 4.2+ | Factor graph backend for CEP measurement |
| Python | 3.12 (Jazzy default) | ROS2 Python nodes; analysis scripts |

Do NOT swap any of these without updating both this file and
`VALIDATION_PLAN.md` stack section.

## Phase status

- [ ] Phase 0 — Infrastructure (headless, local) — **next**
- [ ] Phase 1 — PoO FAR/FRR (GPU vast.ai) — highest risk, blocks 2/3
- [ ] Phase 2 — Reputation → exclusion (GPU vast.ai)
- [x] Phase 3 — CEP vs hops + relay refit (CPU, TRN mocked) — COMPLETE 2026-05-24 (v4 final); 250-trial sweep at realistic scaffold (sigma_trn=35m paper-spec, anchor/follower init noise 30/50m); CEP_50 at k=3 = 23.3m PASS << 100m; **paper GDOP family CONFIRMED with empirical δ=0.088 (paper's δ=0.15 is conservative upper bound)** — best fit `CEP(k) ≈ 19.4·(1.088)^k`
- [x] Phase 4 — Failover timing (CPU, local) — COMPLETE 2026-05-23; 1200 follower-switches across 4 scenarios (S1/S2/S3/S5; S4 deferred), all 100% pass; silence-triggered p99=6.24s, reputation-triggered p99=1.94s, both << 15s threshold
- [x] Phase 5 — GNSS spoofing reaction (CPU, local) — COMPLETE 2026-05-23; N=20/F=2 × 30 trials, detection_rate=98.3% (59/60), 0 false positives, p99 detection 0.60s (paper criterion <5s); N=50 scope-limited due to Python rclpy/DDS overhead (documented; Phase 7 C++ detector follow-up)
- [🟡] Phase 6 — Progressive attrition + load balancing — Tier B (Python MC) COMPLETE 2026-05-24; 15/15 trials mission_survived at N=50/M=10/3-kill, but capacity-invariant timing budget violated 6× (29.8s vs paper 5s) due to thundering-herd in α_cap selection — paper-v10 erratum + protocol revision needed. Tier A 1-trial demo (N=5 PX4 + bridge + Phase 4 protocol on Gazebo flight dynamics) PASS at 6.10s; full Tier A campaign DEFERRED. N=200 scaling cliff documented.
- [x] Phase 7 — Ablation 2026-05-24; 4 ablations × 3-5 trials. ABL1 spoof-detection NECESSARY (98.3%→0%). ABL2 failover-watchdog is timing knob (6s→31s, 5×). ABL3 α_cap NOT load-balancing lever (no change). ABL4 TRN scaffold-artifact (CEP improves on disable — needs revised scenario).
- [🟡] Phase 8 — SwarmRaft baseline — infrastructure built (raft_node + 3 msgs + comparison scripts), initial leader election works; recovery-after-kill stability issue documented (DEFERRED to v11 or canonical SwarmRaft wrap). Paper's comparative claim must DEFER, DROP, or use partial evidence.

## When in doubt

- **Before starting a phase** → read `docs/VALIDATION_PLAN.md` phase
  section in full. Pass criteria + don't-do list + expected outcome.
- **Before any GPU rental** → check `docs/cost-budget.md` for current
  vast.ai spend and remaining budget.
- **Before any code that processes camera images** → confirm phase
  hardware target is GPU. If on local CPU, stop.
- **Anything not in VALIDATION_PLAN.md** → ask the user, do not improvise.
