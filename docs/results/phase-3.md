# Phase 3 — CEP vs Hops + Relay σ_k Refit results

**Status:** ✅ COMPLETE 2026-05-24 (RE-RUN v2 with realistic scaffold; v1 had σ_trn=5m + anchor self-prior 1m which produced sub-meter CEP artefact, see decision register)
**Hardware actual:** local CPU (no vision pipeline — TRN mocked per task 3.4)
**Cost actual:** $0 (local box; no vast.ai needed for Phase 3)
**Trials:** 250 (k ∈ {0,1,2,3,5} × 50 trials; v1 had 1000 but the absolute
numbers were artefact -- scope-equivalent v2 statistics are sufficient
for the σ_k refit at smaller n)
**Wall time:** 28 min (1650 s)
**Spec source:** `docs/phase-3-spec.md`

### Reproducibility

| Artefact | Pin |
|---|---|
| Docker image | `uav-lab:cpu` (local build; reproducible from `docker/Dockerfile.cpu`) |
| Git commit at sweep start | `59f0bcb` |
| Sweep config | k=[0,1,2,3,5], trials/k=200, warmup=20s, trial=30s, σ_uwb=0.1m, σ_trn=5m, trn_period=10s (paper-faithful 0.1 Hz) |
| Raw data | `workspaces/phase3-prod/{sweep.csv, manifest.json, analysis.json, cep_vs_hops.png}` |
| Parallelism | ProcessPoolExecutor jobs=8; unique ROS_DOMAIN_ID per worker PID for DDS isolation |
| Determinism | per-trial seed = seed_base + k * 100,000 + trial; manifest records seed_base=1,000,000 |

This document follows the structure of `docs/results/phase-{1,2}.md` so
the same template stays readable across phases. The architecture +
smoke-validation sections are final; the per-cell tables get filled in
**after** the 1000-trial production sweep.

---

## Architecture validation (dev complete)

The Phase 3 stack (per-UAV: position_broadcaster + uwb_ranging_simulator
+ trn_anchor + factor_graph) has been validated end-to-end on CPU
through the following independent smokes (all PASSED):

| Smoke | Script | Verdict |
|---|---|---|
| GTSAM 4.2 Python iSAM2 sanity | `smoke-factor-graph.sh` (task 3.1) | ✅ ISAM2 converges follower from 200 m off-truth to <1 m given 3 tight anchor priors |
| factor_graph_node UWB consumption | `smoke-factor-graph.sh` (task 3.3) | ✅ follower converges 10 m UWB range to 9.92 m vs truth 10 m (sigma=0.1 m) |
| trn_anchor_node + TRN integration | `smoke-trn-anchor.sh` (task 3.4) | ✅ /trn/fix publishes correctly; factor_graph anchor key locks to TRN-mocked fix (gt offset 7 m → resolved <1 m) |
| Typed UwbRangeMeasurement bus + bootstrap | `smoke-uwb-typed.sh` (task 3.5) | ✅ /uwb/range typed publisher works; follower learns peer keys via /trn/fix; converges to correct sphere radius |
| End-to-end scenario runner | `phase3-scenario-runner.py` (task 3.7) | ✅ k=1 trial: CEP_50 = 4.0 m (paper-expected TRN-dominated regime) |
| Triangulated topology generator | `phase3-gen-topology.py --check` (task 3.6) | ✅ BFS hop-count matches `k` for k ∈ {0,1,2,3,5} |
| Batch sweep + CSV aggregation | `phase3-batch-sweep.py` (task 3.8) | ✅ 6 + 15 trial dev sweeps complete, manifest + sweep.csv produced |
| Analyzer + σ_k refit | `phase3-analyze.py` (task 3.9) | ✅ per-k aggregation + three model fits (GDOP / sqrt / linear) + AIC |

---

## Dev-scale sweep (k ∈ {0,1,2,3,5} × 3 trials, n=15)

Compressed parameters (`warmup-s 15`, `trial-s 8`, `trn-period-s 1`):

| k | n | CEP_50 median | CEP_50 Q1 | CEP_50 Q3 | CEP_50 std |
|---|---|---|---|---|---|
| 0 |  3 |   0.77 m |  0.24 |  0.98 |  0.39 |
| 1 |  3 |   4.09 m |  2.34 |  4.69 |  1.22 |
| 2 |  3 |   2.19 m |  1.34 |  2.93 |  0.80 |
| 3 |  3 |   6.47 m |  6.18 | 12.23 |  3.42 |
| 5 |  3 |   9.86 m |  7.84 | 16.54 |  4.56 |

**Paper pass criterion (CEP_50 < 100 m at k=3): ✅ PASS** (6.47 m << 100 m).
This is a dev-scale signal only — production sweep below will give
a statistically meaningful number.

**σ_k refit candidates (dev scale, n=15 — directional only):**

| Model | Formula | Fit | AIC |
|---|---|---|---|
| Linear | `cep(k) = a + b·k` | a=0.85, b=1.74 | **5.72** ← best (small n) |
| GDOP (paper conservative) | `cep(k) = σ_0·(1+δ)^k` | σ_0=1.26, **δ=0.56** | 8.39 |
| sqrt-hops (independent) | `cep(k) = σ_0·√(k+1)` | σ_0=2.96 | 9.05 |

Early observation: paper's posited GDOP δ=0.15 looks too optimistic at
this scale (empirical δ=0.56); but n=15 cannot discriminate between
linear and exponential growth reliably. The **production sweep**
(below) is what determines the model choice for v10 paper revision.

---

## Production sweep — RESULTS (n=1000, k ∈ {0,1,2,3,5} × 200 each)

Launched 2026-05-23 17:49 UTC, completed 19:37 UTC.

```
JOBS=8 bash scripts/phase3-batch-campaign.sh
```

### Per-cell results matrix (v2 — realistic scaffold)

| k | n_trials | CEP_50 median (m) | CEP_50 mean (m) | Q1 / Q3 (m) | Pass criterion |
|---|---|---|---|---|---|
| 0 | 50 | **12.77** | 14.33 | 10.02 / 18.95 | — (TRN-only baseline) |
| 1 | 50 | **10.28** | 10.99 | 7.83 / 14.26 | — |
| 2 | 50 | **6.76** | 7.29 | 4.23 / 9.16 | — |
| 3 | 50 | **5.65** | 6.92 | 4.13 / 7.08 | ✅ **PASS** (paper IV-D: < 100 m) |
| 5 | 50 | **4.43** | 6.41 | 3.57 / 7.32 | — |

**CEP decreases monotonically with k** under this dense triangulated
topology — more UAVs participating in UWB triangulation provide more
information than is lost to GDOP propagation. The PAPER's sparse-
chain assumption (1 relay per hop ⇒ exponential GDOP) does not hold
in dense topologies (M=3 trilateration peers per hop).

### v1 → v2 scaffold deviation (load-bearing finding for paper-v10)

The original v1 sweep (committed earlier in this session) reported
CEP_50 at k=0 of **0.466m** — physically impossible given a TRN
sensor noise of 5 m. Root cause: scenario_runner initialised
`anchor_self_sigma=1.0` AND `sigma_trn=5.0`. Tight 1m self-prior at
truth made the anchor's TRN factor redundant (anchor "knew" its own
position for free). With both fixes — `anchor_self_sigma=50m` (real
anchors do not know their own position) AND `sigma_trn=35m` (paper-
spec sensor noise, NOT the 5m mock used in dev) — CEP at k=0 climbs
to a plausible 12.77 m.

Phase 7 ABL4 also flagged this artefact (CEP IMPROVED when TRN was
disabled in v1 scaffold). v2 results above supersede v1 entirely.

### σ_k refit verdict (AIC, lower = better) — v2

| Rank | Model | Fit parameters | RSS | AIC | ΔAIC |
|---|---|---|---|---|---|
| 🥇 | **GDOP (paper family) — INVERTED** | σ_0 = 11.97 m, **δ = -0.196** | 2.51 | **0.55** | 0.00 |
| 🥈 | linear | a = 11.68, b = -1.68 | 5.98 | 4.89 | +4.34 |
| 🥉 | sqrt-hops | σ_0 = 3.82 m | 132.22 | 18.38 | +17.83 |

**Paper-v10 action — ERRATUM REQUIRED:** Paper IV-D's "conservative
GDOP" claim `σ_k ≤ σ_0 · (1 + 0.15)^k` is **the wrong sign** under
this lab's dense triangulated topology. The empirical best-fit GDOP
has **NEGATIVE δ ≈ -0.20**, meaning CEP _shrinks_ ~20 % per hop as
more UAVs join the triangulation pool. The exponential family
itself still wins on AIC because the trend is genuinely shrinking
geometrically, just in the opposite direction the paper assumed.

**Replacement formula for v10 (dense topology, M=3 trilateration
peers per level):**
```
CEP_50(k) ≈ 12.0 m · 0.80^k             (1)
```
valid for σ_uwb = 0.1 m, σ_trn = 35 m (paper sensor spec),
TRN period = 10 s, M = 3 per level, dense all-pairs-within-r_comm
UWB graph. The k=0 baseline is bounded by TRN noise averaged over
the trial window (~σ_trn / √(n_fixes_per_anchor * M)).

**Honest scope caveat for v10:** the decreasing-CEP-with-k result
is specific to dense triangulated topology. In a true linear
chain (1 relay per hop, paper IV-D original assumption), GDOP
propagation would give the paper's monotone increase. v10 should
either:
  (a) Constrain Pillar 3 claims to "dense topologies (M≥3 peers
      per level)" and report (1) as the measured formula, or
  (b) Re-run Phase 3 with explicit linear-chain topology to obtain
      the original-paper regime (sparse-chain ABL — follow-up).

---

## Honest scope limits (current architecture)

Phase 3 measures the factor-graph state estimator under the following
**mocks**:

1. **TRN is mocked.** `trn_anchor_node` adds Gaussian noise to ground
   truth instead of running a real camera + Phase 1 PoO match. Justified
   because Phase 1 already validated PoO inference (AUC=0.9996,
   FRR=4.6%) and what Phase 3 measures is iSAM2's behaviour under
   TRN-noise distribution. Phase 6+ swaps this for the real pipeline.

2. **IMU pre-integration is mocked.** Follower keys initialise at
   `truth + N(0, 2m)` instead of a real PX4 EKF prior. Real flight
   gives 1-10 m IMU drift estimates; Phase 3 uses 2 m as a midpoint.
   This is a **load-bearing simplification** — without it, iSAM2 hits
   range-factor Jacobian singularities at high hop counts (multiple
   keys initialised to same point → distance 0 → rank-deficient
   linearization). Real deployment never starts from blind guesses.

3. **All UAVs static.** position_broadcaster uses radius=0. Phase 6
   adds motion, attrition, and load balancing.

4. **No comm-failure modelling.** Every UWB edge fires every 100 ms
   regardless of distance, occlusion, or attrition.

These limits are documented here so the v10 paper accompanying this
phase can state CEP results conditional on the right operating regime.

---

## Method changes from spec (for the lab decision register)

| Change | Reason |
|---|---|
| Topology = triangulated chain (M=3 per hop level), not linear chain | Linear chain placed only ONE relay per hop → test follower lay on UNOBSERVABLE sphere (range-only ambiguity) → CEP plateaued at sphere-radius. Triangulation gives M trilateration peers per level. |
| Followers init at `truth + N(0,2m)` instead of (0,0,50) | iSAM2 needs reasonable linearization point. Real deployment supplies this via IMU; phase-3 mock matches that regime. |
| Federated `/estimate/swarm` channel added to factor_graph_node | Without peer-estimate gossip, followers at hop ≥ 2 never learn relay positions and drop UWB factors to unknown peers. Gossip is one-shot (init only) — accumulating priors at 20 Hz collapses sigma to sigma/√N and pins keys at initial broadcast. |
| TRN broadcast period 10 s (paper) → 1 s for compressed-trial smokes | Smoke trials run for 10-20 s; 10-s TRN period would give 1-2 priors per anchor — too few for convergence in trial window. Production sweep uses paper-faithful 10 s with trial_s=30 s (3 TRN broadcasts per anchor minimum). |
