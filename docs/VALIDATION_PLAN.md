# VALIDATION_PLAN — uav-gazebo-lab

**Status:** locked 2026-05-21. Read this fully before any phase.

This document is the single source of truth for what to validate, in
what order, with what hardware, and at what cost. Architect should not
deviate from the phase ordering or two-tier scale without explicit
discussion with the user.

---

## Purpose

Empirically validate every claim in the BFT-Resilient UAV Swarm
Navigation paper (v9_8, arXiv preprint, DPMA Aktenzeichen
10 2026 002 312.2) using physics-grounded simulation (Gazebo Harmonic
+ PX4 SITL) and high-fidelity factor-graph estimation (GTSAM 4.2+).

Out of scope (deferred to post-validation future work): hardware-in-the-
loop with real UAVs. That is a normal scope split — sim-validated
papers in this venue family (IROS / ICRA / AAAI) routinely defer real-
flight to follow-on work.

---

## Two-tier scale (preamble — READ FIRST)

**Problem:** the paper claims results at N=200 UAV. Gazebo PX4 SITL
cannot run 200 vehicles — even 50 is at the edge of a workstation. Each
SITL instance is ~150-400 MB RAM + meaningful CPU, plus physics tick
contention. 200 instances = ~80-150 GB RAM and >200 CPU cores. Not
feasible on rentable hardware.

**Solution (standard in top-venue UAV papers):**

| Tier | Engine | UAV count | Validates |
|---|---|---|---|
| **Tier A — Mechanism fidelity** | ROS2 Jazzy + Gazebo Harmonic + PX4 SITL | 10-20 | That mechanisms (PoO, reputation update, failover, spoofing reaction) work under realistic physics, sensor noise, and middleware (DDS) timing |
| **Tier B — Statistical scale** | Python + GTSAM (and the existing v9_8 §VII-IX abstract Monte Carlo) | 200 (and up) | Aggregate behavior, convergence bounds, parameter sensitivity, f-resilience curves |

Tier B already partially exists in the published §VII-IX. **Do NOT
redo §VII-IX.** Tier B work in this lab augments §VII-IX with
factor-graph realism (real CEP from real sensor models), not replaces
it.

This split is a strength, not a weakness — Gazebo provides mechanism
fidelity that abstract sim cannot; abstract sim provides scale that
Gazebo cannot. The paper narrative explicitly frames them as
complementary.

---

## Thesis → Phase mapping

| Paper claim | Validated in |
|---|---|
| PoO primitive (concept, T_verify=0.3, unforgeability) | Phase 1 |
| Pillar 1 — BFT consensus | Phase 2 + Phase 7 (ablation) |
| Pillar 2 — Dynamic hierarchy / role rotation | Phase 4 + Phase 6 |
| Pillar 3 — Reputation-weighted position relay | Phase 2 + Phase 3 |
| Pillar 4 — Failover < 10 s | Phase 4 |
| Pillar 5 — GNSS spoofing detection | Phase 5 |
| Pillar 6 — Load balancing | Phase 6 |
| Prop 1 — Quorum safety (honest not excluded when f ≤ M-1) | Phase 2 |
| Prop 2 — Parameter scaling (M, f) | Phase 2 (variation sweep) + analytics |
| Prop 3 — Convergence ≲ 215 s | Phase 2 |
| Headline CEP < 100 m up to k=3 (multi-anchor fusion) | Phase 3 |
| Comm complexity ~ 185 B per message, 13.3 kbit/s | Phase 0 (message size log) + Phase 4 (link rate log) |
| Comparative claim vs SwarmRaft | Phase 8 |

If a claim is in the paper and not in this table, flag immediately — it
either belongs in a phase below or in §VII-IX (already released).

---

## Cost budget summary

Estimates assume vast.ai RTX 4090 single-GPU at $0.50-0.80/hr median.
Upper bound includes ~30% buffer for re-runs.

| Phase | Hardware | Wall time | Cost (USD) |
|---|---|---|---|
| Phase 0 | Local CPU | ~1.5 wk | $0 (incl. Sentinel-2 download — free Copernicus account) |
| Phase 1 | vast.ai RTX 4090 | ~30-60 GPU-hr | $15-50 |
| Phase 2 | vast.ai RTX 4090 | ~40-80 GPU-hr | $20-65 |
| Phase 3 | vast.ai RTX 4090 | ~60-120 GPU-hr | $30-100 |
| Phase 4 | Local CPU (parallel) | ~1 wk | $0 |
| Phase 5 | Local CPU (parallel) | ~1 wk | $0 |
| Phase 6 | Mixed (Gazebo CPU + Python GTSAM on vast.ai for 200 runs) | ~40-60 GPU-hr | $20-50 |
| Phase 7 | Mixed (re-runs of P1/P3 configs with each pillar disabled) | ~60-100 GPU-hr | $30-80 |
| Phase 8 | vast.ai (re-runs of P3/P6 setups with SwarmRaft) | ~30-60 GPU-hr | $15-50 |
| **Total** | | **~10-14 wk** | **$130-395** |

**Plus**: Phase 8 SwarmRaft pre-flight (see Pre-flight) — if no open-
source reference exists, add ~2 weeks dev time (no GPU cost during
implementation).

**Plus**: vast.ai storage (~$0.10/GB-month for persistent volumes if
used). Optional — can rebuild image per session for $0 storage cost.

---

## Risk register

| Risk | Phase | Severity | Mitigation |
|---|---|---|---|
| PoO FRR > 10% on degraded imagery | 1 | **HIGH — make-or-break** | If realised, the entire reputation-exclusion chain is over-aggressive; either paper PoO threshold needs adjustment OR PoO algorithm needs replacement. Plan revisit of paper Assumption (iv) explicitly. |
| Sentinel-2 dataset acquisition rate-limited | 0 | MEDIUM | Pre-stage entire region of interest before Phase 1 start; budget 2-3 days for downloads |
| Formula 9 (1+0.15)^k disagrees with measured σ_k | 3 | MEDIUM — expected | This IS the expected outcome. Plan response: keep formula as worst-case bound, publish measured form (likely ~√k) as v10 paper revision |
| Factor-graph timing too slow for online CEP | 3 | MEDIUM | iSAM2 with fixed-lag smoother should keep up; if not, batch every 1-2s instead of fully online |
| 200-vehicle SITL infeasible (already known) | 6 | LOW (already designed for) | Two-tier scale — Python/GTSAM at 200; Gazebo at 10-20 |
| SwarmRaft no open-source ref | 8 | MEDIUM | Pre-flight check; budget +2 wk dev if needed |
| vast.ai instance pre-emption / disconnection | 1-3, 6-8 | LOW | Use on-demand (not interruptible) tier; checkpoint every 30 min |
| Gazebo Harmonic camera plugin produces imagery unsuitable for SuperPoint | 1 | MEDIUM | Smoke test in Phase 0 — render a few frames, run SuperPoint, confirm reasonable keypoint count (>500 per frame). If poor, augment with photorealistic plugin or pre-render satellite imagery as backdrop |

---

## Go/no-go decision points

These are checkpoints where the user reviews results before authorising
the next phase block.

1. **After Phase 1** — if PoO FAR<5% AND FRR<10%: proceed Phase 2.
   Otherwise STOP, revisit paper Assumption (iv) and algorithm spec.
2. **After Phase 3** — if measured CEP < 100 m up to k=3: headline claim
   stands. If not: paper headline needs revision before Phase 6+
   continues.
3. **After Phase 7** — if ablation shows each disabled-pillar variant
   degrades meaningfully: pillar necessity claims stand. Otherwise,
   paper pillar count may need revision.

User holds the go/no-go decision. Architect produces the report at
each checkpoint; does not auto-proceed.

---

## Pre-flight (BEFORE Phase 0)

Complete all of these before starting Phase 0. Cost: free, ~half-day.

| Check | What | Why |
|---|---|---|
| **PF-1** ✅ | SwarmRaft reference exists (Skoltech, arXiv 2508.00622). Pure Python Monte Carlo — not Gazebo/ROS2. Phase 8 revised: ~3-7 days ROS2 wrapping, not +2 wk reimplementation. License undeclared on the repos; author contact required before vendoring. See `docs/preflight/pf-1-swarmraft.md`. | Phase 8 scope known. |
| **PF-2** ⏳ | Copernicus Data Space Ecosystem account — user-driven signup at https://dataspace.copernicus.eu. Credentials go into `.env` (template at `.env.example`). See `docs/preflight/pf-2-copernicus.md`. | Phase 0 dataset staging blocks. |
| **PF-3** ⏸ | vast.ai account + deposit — **DEFERRED** by user decision (2026-05-21) until GPU image and first GPU experiment are ready (closer to Phase 1 start). Phase 0/4/5 do not block on this. | Phase 1 GPU work blocks. |
| **PF-4** ✅ | v9_8 PDF + tex copied to `docs/reference/` as frozen reference (from `audit-harness/inputs/papers/`). | Avoid drift if paper revisions land. |
| **PF-5** ✅ | PoO algorithm spec locked at `docs/poo-algorithm-spec.md` (2026-05-21). All paper-locked values in §IV-B traced + cited; Phase-1-specific Track 2 deferrals closed with concrete defaults (SuperPoint pretrained weights, Mode A only, Lowe ratio matcher per paper spec, ~50 km replay byzantine model, Sentinel-2 L2A at 480×640 px). Sensitivity sweep over T_verify ∈ {0.2, 0.3, 0.4} retained as Phase 1 measurement output (paper-specified). | Phase 1 can now start. |
| **PF-6** ✅ | Cost-tracking landed at `docs/cost-budget.md` ($500 cumulative cap, ~30% over $395 upper estimate). | Required by Hard Rule 6. |
| **PF-7** 🟡 | Both Docker images build; push GPU to registry. CPU build kicked off, fixed uXRCE-DDS Agent install (source-build, not apt). Re-running in background. | Phase 0 first item depends on this. |

---

## Phase 0 — Infrastructure (headless, local CPU)

### Goal
Lay the foundation every later phase depends on. No paper claims
validated here directly; this enables Phases 1-8.

### Hardware
Local CPU. No GPU needed.

### Dependencies
Pre-flight PF-1 through PF-6 complete.

### Time / cost
~1.5 weeks. $0 (excluding any vast.ai signup deposits).

### Spec
0. **Docker images first** — build `uav-lab:cpu` from
   `docker/Dockerfile.cpu`; build `uav-lab:gpu` from
   `docker/Dockerfile.gpu`. Smoke test: `docker compose --profile cpu
   run --rm dev` opens a shell with ROS2 Jazzy + Gazebo Harmonic +
   uXRCE-DDS + GTSAM 4.2 already installed. Push GPU image to
   registry (used by vast.ai later). All subsequent Phase 0 items
   run INSIDE the container.
1. **ROS2 Jazzy** — verify `ros2 topic list` works inside the CPU
   container (no host install).
2. **ros_gz_bridge** — smoke test: spawn empty Gazebo world inside
   the container, bridge `/clock` topic, confirm ROS2 sees it.
3. **PX4 main clone + build** — clone to host-side
   `../PX4-Autopilot/`, build inside container with Gazebo Harmonic
   config. Confirm `make px4_sitl gz_x500` launches a single drone.
4. **uXRCE-DDS agent** — already in image; verify by running and
   confirming PX4 topics (e.g. `/fmu/out/vehicle_local_position`)
   appear in `ros2 topic list` when single drone runs.
5. **Multi-vehicle spawn script** — launch 10-20 PX4 SITL instances in
   one Gazebo world, verify each gets a unique `/pxN/...` topic
   namespace.
6. **uav_swarm_msgs ROS2 package** — message types:
   - `SignedObservation` (PoO payload — sensor observation + signature)
   - `DistilledState` (post-fusion state estimate)
   - `NoisyPose` (broadcast pose with σ field)
   - `ReputationUpdate` (R value + reason code)
7. **Shared utility nodes**:
   - `position_broadcaster_node` — publishes pose with configurable σ
   - `uwb_ranging_simulator_node` — emits range measurements with
     realistic UWB noise model (σ_range ~ 0.1 m + bias)
   - `comm_logger_node` — logs message sizes + send rates (feeds
     Phase 0 comm-complexity check)
8. **Sentinel-2 dataset staging** — download region of interest,
   tile, convert to formats the Gazebo camera plugin and SuperPoint
   can both consume. Store under `datasets/staged/`.
9. **Gazebo camera + SuperPoint smoke test** — render one frame from
   a Gazebo drone above a Sentinel-2-textured ground plane; run
   SuperPoint; confirm ≥500 keypoints. If not, Risk-9 mitigation
   kicks in.
10. **Comm complexity log** — single 10-UAV run, log all message
    bytes + send rates. Verify ~185 B/msg + ~13.3 kbit/s aggregate
    (paper claim).

### Pass criteria
- Each of items 1-10 completes without manual intervention beyond
  documented bootstrap.
- All shared nodes have a unit test and a Gazebo smoke test.
- Comm complexity numbers match paper claim within ±15% (NOT a
  separate phase — done here because measurement is trivial once
  infrastructure exists).

### Expected outcomes
- Smooth: pipeline works, dataset staged, smoke tests green.
- Could-fail-in-good-way: Gazebo camera plugin renders imagery
  SuperPoint can't process well; mitigation = enrich with photo-real
  texturing or pre-rendered Sentinel-2 backdrops.

### Don't do
- Do NOT implement PoO algorithm here (locked in Phase 1).
- Do NOT run 200-UAV scenarios (infeasible; Tier B is Python/GTSAM).
- Do NOT skip the camera+SuperPoint smoke test even if Phase 1 feels
  far away — it gates whether Phase 1 can start.

---

## Phase 1 — PoO FAR / FRR (GPU, vast.ai)

### Goal
Validate the **PoO primitive** end-to-end on realistic degraded imagery.
This is the highest-risk piece of the paper — if PoO does not separate
honest from byzantine observers reliably, downstream reputation logic
is over-aggressive (Phase 2-3 results would be meaningless).

### Paper references
PoO concept; Assumption (iv) (degraded imagery inlier rate 60-90% /
20-40%); T_verify = 0.3.

### Hardware
vast.ai RTX 4090, 1 GPU. Headless OK (no display).

### Dependencies
Phase 0 complete (specifically: PoO algorithm spec locked, Sentinel-2
dataset staged, Gazebo camera plugin verified).

### Time / cost
~30-60 GPU-hours over ~1-2 wk. $15-50.

### Spec
- 1 honest UAV camera (Gazebo rendered with Sentinel-2 backdrop) +
  1 byzantine UAV camera (forged or replayed imagery)
- For each, run PoO verification against reference satellite image
- Sweep: lighting conditions, motion blur, partial occlusion,
  altitude — exercise Assumption (iv) inlier ranges
- Per trial: record VERIFIED/UNVERIFIED verdict, raw inlier count,
  ratio threshold value, T_verify result

### Method
1. Set up Gazebo scene with N=2 UAVs above Sentinel-2-textured ground.
2. UAV 1 (honest): normal camera, normal imagery.
3. UAV 2 (byzantine): inject forged imagery (random crop from
   different region, or replay from earlier timestamp).
4. Run PoO verification per spec.
5. Sweep environmental params (lighting, blur, altitude) for ≥500
   honest trials + ≥500 byzantine trials.
6. Compute FAR (false accept of byzantine), FRR (false reject of
   honest), ROC curve, separability AUC.

### Pass criteria
- FAR < 5% at paper's T_verify = 0.3
- FRR < 10% at paper's T_verify = 0.3
- ROC AUC > 0.90

### Expected outcomes
- Pass: proceed Phase 2.
- Fail (FRR > 10%): Assumption (iv) is too optimistic; either threshold
  needs adjustment, paper needs revised assumption, OR PoO algorithm
  needs replacement. STOP. Discuss with user.
- Fail (FAR > 5%): byzantine can forge verification too easily;
  unforgeability claim weakens. Same STOP.

### Don't do
- Do NOT use synthetic textbook images — must be realistic Sentinel-2
  + Gazebo-rendered.
- Do NOT proceed to Phase 2 without explicit go decision from user.
- Do NOT change PoO algorithm spec mid-phase (locked in PF-5).

---

## Phase 2 — Reputation → Exclusion Loop (GPU, vast.ai)

### Goal
Validate the chain real-PoO-verdict → reputation update → quorum
exclusion. Validates Prop 1 (quorum safety) + Prop 3 (convergence ≲
215 s) under realistic PoO verdicts, not abstract label flips.

### Paper references
Pillar 1 (BFT consensus); Prop 1; Prop 3; Assumption (iv).

### Hardware
vast.ai RTX 4090 (vision needed for real PoO).

### Dependencies
Phase 1 PASS.

### Time / cost
~40-80 GPU-hours. $20-65.

### Spec
- 10-15 UAV swarm, mix of honest + byzantine (vary f from 1 to ⌊(M-1)/3⌋)
- Real PoO running on Gazebo cameras as in Phase 1
- Reputation update node consuming PoO verdicts
- Quorum exclusion logic per paper
- Measure exclusion time (time from byzantine joining to byzantine
  being excluded by quorum)
- Variation: sweep M (quorum size) and f (byzantine count) per Prop 2

### Method
1. Scenario setup as above.
2. Inject byzantine after t=60 s (steady-state established).
3. Log: per-UAV reputation R(t), exclusion event timestamps,
   per-honest-UAV "was I incorrectly excluded?" flag.
4. Run ≥100 trials per (M, f) cell.

### Pass criteria
- Prop 1: zero false exclusions of honest UAVs when f ≤ M-1, across all
  trials.
- Prop 3: median exclusion time ≲ 215 s; 95th percentile ≲ 300 s.
- Prop 2: parameter sweep confirms paper's scaling formula within ±15%.

### Expected outcomes
- Pass: paper's reputation/exclusion claims stand under physics.
- Could-fail-in-good-way: exclusion time faster than 215 s under
  realistic PoO (because verdicts arrive faster than abstract sim
  modeled). Update paper with measured median.
- Fail (any honest excluded): Prop 1 broken. STOP.

### Don't do
- Do NOT use abstract label flips for PoO verdicts here — that's what
  §VII-IX already did. The whole point is real PoO output feeding the
  loop.
- Do NOT skip variation sweep — Prop 2 needs the (M, f) grid.

---

## Phase 3 — CEP vs Hops + Relay Refit (GPU, vast.ai) — SUBSUMES naive M1

### Goal
Measure CEP as a function of hop count k under realistic multi-anchor
fusion. Validate headline accuracy claim. **Empirically refit relay
formula** — paper's σ_k = σ_anchor × (1+0.15)^k is a conservative GDOP
bound, expected to be loose; this phase measures the physical form.

### Paper references
Headline CEP < 100 m up to k=3; Pillar 3 (relay); §IV-D formula 9.

### Hardware
vast.ai RTX 4090 (real PoO + GTSAM + camera-driven TRN).

### Dependencies
Phase 0 (factor graph stack), Phase 1 (PoO).

### Time / cost
~60-120 GPU-hours. $30-100.

### Spec
- 10-15 UAV swarm in chain + multi-anchor topology
- Real GTSAM iSAM2 factor graph per UAV
- Reputation-weighted priors
- UWB ranging (σ ~ 0.1 m, from Phase 0 simulator)
- Multi-hop position relay through k = 0, 1, 2, 3, 5 chain depths
- Real TRN (terrain-referenced navigation) from camera + Sentinel-2
- Measure: per-UAV position error → CEP_50, CEP_95 per hop tier
- **Plus**: log raw σ_k per hop, fit both √k and (1+β)^k forms

### Method
1. Chain scenario: anchor → relay_1 → relay_2 → relay_3 → relay_5,
   plus parallel chains for multi-anchor fusion.
2. Run ≥200 trials per hop tier.
3. Compute CEP per tier.
4. Fit measured σ_k vs k to both forms; report which fits better and
   R² for each.

### Pass criteria
- CEP_50 < 100 m at k=3 under multi-anchor fusion (headline).
- σ_k fit reports both forms with R² and explicit "winning" form.

### Expected outcomes (PLAN FOR THESE EXPLICITLY)
- **Likely outcome:** measured σ_k grows ~√k (independent hop noise),
  not (1+0.15)^k. The paper's formula is conservative worst-case GDOP,
  not physical decay. **This is not a failure** — it is the expected
  refit. Paper response: keep (1+0.15)^k as worst-case bound (cited as
  such), publish measured √k as v10 update / errata.
- Pass on CEP: headline stands.
- Fail on CEP (> 100 m at k=3): headline must be revised before any
  paper publication. STOP.

### Don't do
- Do NOT "validate the formula as stated" — measure reality, report
  what reality is.
- Do NOT use Phase 1 PoO with FRR > paper-claimed value — that would
  bias relay measurements with bad reputation feedback.
- Do NOT collapse "CEP" and "σ_k" into one metric — they are different
  (CEP is percentile-based position error; σ is variance estimate
  parameter).

---

## Phase 4 — Failover Timing (headless, local CPU — parallel to Phase 1-3)

### Goal
Validate Pillar 4 (failover < 10 s) under real ROS2/DDS middleware
timing + flight dynamics.

### Paper references
Pillar 4; failover scenarios F1-F5.

### Hardware
Local CPU. Headless — runs in parallel with GPU work above.

### Dependencies
Phase 0 complete.

### Time / cost
~1 wk. $0.

### Spec
- 10 UAV swarm
- Scenarios F1-F5 per paper (anchor failure, link failure, partial
  partition, slow degradation, sudden loss)
- Comm conditions: nominal + 5% packet loss
- Measure: switching time (anchor death → successor active)

### Pass criteria
- All scenarios: switching time < 10 s, both nominal and 5% loss.

### Expected outcomes
- Pass: pillar 4 stands.
- Could-fail-in-good-way: faster than 10 s — update paper.
- Fail: investigate whether DDS QoS settings or election algorithm
  needs tuning.

### Don't do
- Do NOT use abstract sim timing — measure real DDS publish/subscribe
  delay.

---

## Phase 5 — GNSS Spoofing Reaction (headless, local CPU — parallel)

### Goal
Validate Pillar 5 (spoofing detection via UWB cross-verification).

### Paper references
Pillar 5; reaction time < 5 s.

### Hardware
Local CPU. Parallel to GPU work.

### Dependencies
Phase 0.

### Time / cost
~1 wk. $0.

### Spec
- N=50 partial-GNSS scenario
- Spoof 5 UAV with 120 m position offset
- Measure: time from spoof injection to spoof detection + reaction

### Pass criteria
- Reaction time < 5 s for all 5 spoofed UAVs.
- Zero false-positive spoof flags on honest UAVs.

### Expected outcomes
- Pass: pillar 5 stands.
- Fail: revisit UWB cross-check threshold.

### Don't do
- Do NOT use 200 UAV — N=50 matches paper scenario; Tier A scale.

---

## Phase 6 — Progressive Attrition + Load Balancing (mixed two-tier)

### Goal
Validate Pillar 6 (load balancing) + Pillar 2 (dynamic roles) under
progressive 22.5% attrition.

### Paper references
Pillar 6; Pillar 2.

### Hardware
- Tier A mechanism validation: Gazebo, 10-20 UAV — local or vast.ai
- Tier B statistical scale: Python/GTSAM, 200 UAV — vast.ai

### Dependencies
Phase 3 (CEP framework) + Phase 4 (failover primitives).

### Time / cost
~40-60 GPU-hours mixed. $20-50.

### Spec
- Tier A: 15-20 UAV, 22.5% attrition profile, log handover events,
  standby promotions, aggregate CEP timeline
- Tier B: 200-UAV Python/GTSAM with same attrition profile, log same
  metrics aggregated statistically

### Pass criteria
- Tier A: mechanisms execute as specified (handovers complete, standby
  promoted, no orphan UAVs).
- Tier B: aggregate CEP timeline matches paper §VII-IX prediction
  within ±15%.

### Expected outcomes
- Pass on both: pillars 2 + 6 stand at both scales.
- Tier A pass, Tier B fail: mechanism works but statistical claim
  needs revision.
- Tier A fail: mechanism issue — investigate before re-running Tier B.

### Don't do
- Do NOT run 200 UAV in Gazebo (infeasible — Tier B is Python/GTSAM).
- Do NOT skip Tier A and run only Tier B — that re-creates §VII-IX
  without value-add.

---

## Phase 7 — Ablation (integration)

### Goal
Validate that each pillar is necessary — disabling it degrades
measured performance meaningfully.

### Paper references
All 6 pillars.

### Hardware
Mixed — re-run Phase 1 / 3 / 6 configurations with single-pillar-
disabled variants.

### Dependencies
All of Phase 1-6 complete.

### Time / cost
~60-100 GPU-hours. $30-80.

### Spec
4 ablation variants (minimum):
- No reputation (PoO runs but verdicts don't update R)
- No PoO (use abstract label flips as in §VII-IX, comparing to Phase 2)
- No failover (anchors don't switch on death)
- No load balancing (no role handovers)

For each: re-run Phase 3 (CEP) and Phase 6 (attrition) scenarios.

### Pass criteria
- Each disabled-pillar variant shows ≥30% degradation on its
  relevant metric (CEP for relay/PoO/reputation; orphan rate for
  failover/load-balancing).

### Expected outcomes
- All pillars necessary: paper's pillar count justified.
- Some pillars dispensable: paper claim weakens; consider reframing
  or removing the dispensable pillar in v10.

### Don't do
- Do NOT skip ablation because "intuitively each pillar matters" —
  reviewers require this evidence; intuition isn't evidence.

---

## Phase 8 — SwarmRaft Baseline Comparison

### Goal
Validate the comparative claim vs prior art (SwarmRaft).

### Paper references
Comparative table; SwarmRaft citation.

### Hardware
vast.ai (re-run Phase 3 + Phase 6 setups with SwarmRaft implementation
in place of our system).

### Dependencies
Phase 7 complete. PF-1 done (SwarmRaft reference availability known).

### Time / cost
~30-60 GPU-hours implementation runs. $15-50. Plus **~3-7 days** ROS2
wrapping of the existing SwarmRaft Python simulator (kapeldev/SwarmRaft
canonical, yashmadhwal/SwarmRaft alternate — see
`docs/preflight/pf-1-swarmraft.md`). Down from +2 wk thanks to PF-1
finding that reference impl exists.

### Pre-step (before Phase 8 starts)
- Contact Skoltech authors (yyanovich@skoltech.ru) for explicit
  license grant on `kapeldev/SwarmRaft` — repo has no LICENSE file,
  default "all rights reserved." Required before vendoring as
  submodule/fork. Fair-use academic comparison (run + report
  numbers) is generally tolerated without grant but redistribution
  in our repo needs it.

### Spec
- Port SwarmRaft consensus + voting logic from the Python simulator
  to ROS2 nodes runnable in our Gazebo stack
- Verify algorithmic parity: run our port on the Monte Carlo
  scenarios from the upstream repo, match published numbers within
  tolerance
- Re-run Phase 3 (CEP vs hops) and Phase 6 (attrition + load
  balancing) with SwarmRaft node in place of our system
- Same metrics, same scenarios as Phase 3 / 6

### Pass criteria
- Comparative table populated with measured values for both systems
  on identical scenarios.
- Claim of superiority on specific metrics is supported by the
  measurements (or honestly reported as worse where applicable).

### Expected outcomes
- We beat SwarmRaft on claimed metrics: paper claim stands.
- Mixed: report honest measurements; paper narrative may need
  revision to acknowledge trade-offs.
- We lose on claimed metrics: paper claim must be revised.

### Don't do
- Do NOT cherry-pick metrics where we win — report all of: CEP,
  exclusion time, failover time, comm overhead.
- Do NOT skip honest reporting of losses — reviewers will catch
  asymmetric comparisons.

---

## Out of scope (post-validation future work)

- Hardware-in-the-loop with real UAVs (separate Phase 4+ project)
- Real GNSS spoofer hardware testing
- Outdoor flight under adversarial RF conditions
- Long-duration (>1 hr) endurance tests

These are all normal scope splits for sim-validated UAV papers.

---

## Document maintenance

- Phase pass/fail outcomes append to a per-phase results doc
  (`docs/results/phase-N.md`), not to this file.
- This file is locked; revisions require explicit user discussion.
- Cost-tracking lives in `docs/cost-budget.md` (running spend per
  phase).
- Decision register at the end of each phase results doc.

---

## Decision register (this document)

- **2026-05-21** — initial lock. Risk-first phase ordering chosen over
  ease-first; PoO validated before all downstream because make-or-break.
  Two-tier scale (Gazebo 10-20 + Python/GTSAM 200) documented as
  by-design, not workaround. §VII-IX explicitly out of scope for
  re-doing. Naive M1 (relay formula validation in Python) DROPPED in
  favor of Phase 3 (CEP + relay refit in factor graph with measured
  reality).
- **2026-05-21** — Docker-first dev surface added (CLAUDE.md Hard Rule 8).
  Two images: `uav-lab:cpu` for local Phase 0/4/5, `uav-lab:gpu` for
  vast.ai Phase 1/2/3. Same dev pattern as sister sakana-lab. Phase 0
  Spec item 0 + PF-7 added accordingly. Host machine never gets ROS2 /
  Gazebo / PX4 / GTSAM installed directly.
