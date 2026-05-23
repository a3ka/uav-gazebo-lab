# Phase 3 — CEP vs Hops + Relay σ_k Refit results

**Status:** 🟡 DEV COMPLETE, production sweep PENDING (2026-05-23)
**Hardware target:** CPU (no vision pipeline in this phase — TRN is mocked,
see task 3.4 commit). Optional vast.ai CPU instance for parallel speedup.
**Estimated cost:** $0 local, $1-5 if rented for ~4 hr parallel batch.
**Spec source:** `docs/phase-3-spec.md`

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

## Production sweep — PENDING

Plan (1000 trials, ~4 hr wall on a 16-core CPU instance or ~7-8 hr on a
4-core local box):

```
scripts/phase3-batch-sweep.py \
    --k-list 0 1 2 3 5 \
    --trials-per-k 200 \
    --warmup-s 20 --trial-s 30 \
    --sigma-uwb-m 0.1 --sigma-trn-m 5.0 --trn-period-s 10.0 \
    --run-id phase3-prod \
    --jobs 4
```

Then:

```
scripts/phase3-analyze.py \
    --csv workspaces/phase3-prod/sweep.csv \
    --out workspaces/phase3-prod/analysis.json \
    --plot workspaces/phase3-prod/cep_vs_hops.png
```

For vast.ai parallel runs, use `scripts/phase3-batch-campaign.sh`
(thin wrapper that streams logs and resumes incomplete runs).

### Per-cell results matrix (to be filled in)

| k | n_trials | CEP_50 median (m) | CEP_50 mean (m) | std (m) | Pass criterion |
|---|---|---|---|---|---|
| 0 | 200 | _pending_ | _pending_ | _pending_ | — |
| 1 | 200 | _pending_ | _pending_ | _pending_ | — |
| 2 | 200 | _pending_ | _pending_ | _pending_ | — |
| 3 | 200 | _pending_ | _pending_ | _pending_ | **< 100 m (paper IV-D)** |
| 5 | 200 | _pending_ | _pending_ | _pending_ | — |

### σ_k refit verdict (to be filled in)

| Model | Fit | AIC | ΔAIC vs best |
|---|---|---|---|
| Linear | _pending_ | _pending_ | _pending_ |
| GDOP (paper) | _pending_ | _pending_ | _pending_ |
| sqrt-hops | _pending_ | _pending_ | _pending_ |

**Paper-v10 action:** If GDOP δ ≠ 0.15 ± 0.05, an erratum is required.
If sqrt-hops best, paper's conservative bound is RETAINED as
worst-case but main-text formula updated to empirical fit.
If linear best (likely on small n; reassess at production scale)
the paper's exponential-growth framing needs revision.

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
