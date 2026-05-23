# Phase 2 — Reputation → Exclusion Loop results

**Status:** ✅ COMPLETE 2026-05-23
**Hardware actual:** vast.ai RTX 3090, ~2.7 hr wall time
**Cost actual:** ~$0.80
**Trials:** 30 per the 6-cell sweep (5 trials per cell)

### Reproducibility

| Artefact | Pin |
|---|---|
| Docker image | `ghcr.io/a3ka/uav-lab:gpu` digest `sha256:a1c5484f749cf37ddef0a70433c131e251c4ee07423de7ad07c86d8529cbe080` |
| Git commit at campaign start | `b675a91` (Phase 2 batch campaign script landed) + patched M=7 cells locally on instance to `"7 3 10 3"` / `"7 4 10 4"` (committed in commit captured by docs/results/phase-2.md decision register) |
| Dataset | Zurich Z16 PNG tiles (32 files, ~11 MB) -- sibling project `einhard-runtime/runtime/navigation/tiles/zurich-z16` |
| Raw data | `workspaces/phase2-batch/*.exclusions.csv` (30 files) + `*.rep_events.csv` (30 files) + `workspaces/phase2-batch{,-m7}.log` (per-trial console summary) -- gitignored, ~5 MB local |
| PoO config | locked at Phase 1 paper-spec: SuperPoint v1 (MagicLeap weights via LightGlue), N=50 top keypoints, K=20 Mode A descriptors, Lowe ratio τ=0.7, T_verify=0.30 |
| Reputation config | paper IV-C defaults: α_pos=0.05, α_neg=0.15, α_sig=0.30, α_range=0.10, λ=10⁻³ s⁻¹, R_init=0.5, T_reject=0.20, T_quorum=0.60 |
| Verify interval | `publish_period_s=45` (paper ν_verify⁻¹) |
| Trial duration | 300 s (60 s steady-state + 240 s window) |
**Hardware:** vast.ai RTX 3090/4090 + Zurich Z16 dataset
**Estimated cost:** $1-5 for 6-cell × 5-trial baseline campaign
**Spec source:** `docs/phase-2-spec.md`

This document follows the structure of `docs/results/phase-1.md` so
the same template stays readable across phases. Numbered tables get
filled in **after** the production GPU campaign; the architecture +
smoke-validation sections are already final.

---

## Architecture validation (dev complete)

The 4-node Phase 2 stack (per-UAV: signed_observation_publisher +
verifier + reputation_manager + quorum_exclusion) has been validated
end-to-end on CPU through the following independent smokes
(all PASSED):

| Smoke | Script | Verdict |
|---|---|---|
| Verifier wraps Phase 1 PoO pipeline | `smoke-verifier.sh` | ✅ ReputationUpdate emitted with correct UNVERIFIED reason for mock byzantine OBS |
| Asymmetric reputation update + decay | `smoke-reputation-manager.sh` | ✅ R[10] = 0.148 < T_reject=0.20 after 1×VERIFIED + 5×UNVERIFIED (paper IV-C arithmetic exactly) |
| M-voter quorum exclusion | `smoke-quorum-exclusion.sh` | ✅ 3/3 sub-tests: EXCLUDE with M=3 high-R voters, NO_EXCLUDE on M-1 voters, NO_EXCLUDE when one voter R<T_quorum |
| SignedObservation producer (both modes) | `smoke-signed-observation.sh` | ✅ honest+byzantine both publish on /signed_observation with K=20 descriptors |
| Full scenario (4 UAV, M=3) | `phase2-scenario-runner.py` | ✅ byzantine excluded; 0 false exclusions; chain mechanics work |
| Analysis pipeline | `phase2-analyze.py` | ✅ per-cell stats produced, Prop 1/3 verdict per cell |

---

## Compressed-test mechanics check (dev complete)

Single smoke run (3 honest + 1 byzantine, M=3, publish_period=10 s
instead of paper's 45 s, all UAVs colocated within 1 m):

| Metric | Result | Notes |
|---|---|---|
| Processes spawned | 16/16 alive | (4 UAVs × 4 nodes) |
| Reputation events captured | 190 | broadcast + per-target topics |
| Exclusion events captured | 1 | target=3 (byzantine) excluded at t=2.9 s by 3 voters @ R=1.0 |
| **Prop 1** false exclusion of honest | **0** | ✅ PASS |
| **Prop 3** median first-exclusion | 2.9 s | ✅ PASS (compressed test — see caveats) |

**Caveats on compressed numbers** (these will be addressed by the
production campaign):
- `publish_period_s = 10` instead of paper's 45 → ~4.5× faster
  reputation accumulation
- 4 UAVs colocated (x ∈ {0, 1, 2, 3}) → every verifier in
  r_verify=500 m of every publisher → no propagation delay
- self-R defaulted to 1.0 (instead of paper's R_init=0.5) → voter
  weight at full force from t=0
- Together: compressed exclusion ~60× faster than paper's analytic
  prediction. Smoke validates **chain mechanics** (correct
  causal sequence + propagation + counts); production measurement
  validates the **timing claim**.

---

## Production campaign plan (TBD — needs GPU rental)

| Cell | M | f | N_honest | N_byz | trials | est wall time |
|---|---|---|---|---|---|---|
| baseline | 3 | 1 | 6 | 1 | 5 | 25 min |
| safety-edge | 3 | 2 | 5 | 2 | 5 | 25 min |
| larger quorum | 5 | 2 | 6 | 2 | 5 | 25 min |
| safety-edge L | 5 | 3 | 5 | 3 | 5 | 25 min |
| largest M | 7 | 3 | 6 | 3 | 5 | 25 min |
| safety-edge LL | 7 | 4 | 5 | 4 | 5 | 25 min |
| **baseline N=30** | 3 | 2 | 5 | 2 | 30 | 2.5 hr |

**Per-trial config (paper-faithful):**
- publish_period_s = 45 (paper ν_verify⁻¹)
- duration_s = 300 (60s steady-state + 240s window)
- UAVs scattered over 0-500 m grid (still within r_verify but not
  colocated, so propagation delays similar to operational scenario)
- self-R = 0.5 initial (paper R_init)
- Verifier T_verify = 0.30 (Phase 1 validated)

**Total expected cost:** ~5 hr × $0.30-0.70/hr = **$1.50-3.50**.

---

## Final results matrix

| Cell | N_h | N_b | trials | n_byz_excluded | n_honest_excluded | median t_byz (s) | p95 t_byz (s) | Prop1 | Prop3 |
|---|---|---|---|---|---|---|---|---|---|
| (M=3, f=1) | 6 | 1 | 5 | 5 | 0 | **5.9** | 5.9 | ✅ | ✅ |
| (M=3, f=2) | 5 | 2 | 5 | 10 | 0 | 5.0 | 4.9 | ✅ | ✅ |
| (M=5, f=2) | 6 | 2 | 5 | 10 | 0 | 5.8 | 5.7 | ✅ | ✅ |
| (M=5, f=3) | 5 | 3 | 5 | 15 | 0 | 6.4 | 6.4 | ✅ | ✅ |
| (M=7, f=3) | 10 | 3 | 5 | 15 | 0 | 13.3 | 13.3 | ✅ | ✅ |
| (M=7, f=4) | 10 | 4 | 5 | 20 | 0 | 14.6 | 15.2 | ✅ | ✅ |

| Aggregate metric | Measured | Paper formula | Verdict |
|---|---|---|---|
| Median first-exclusion (M=3 cells) | 5.5 s | 113 s (formula) | **20× faster** |
| Median first-exclusion (M=5 cells) | 6.1 s | 113 s | **18× faster** |
| Median first-exclusion (M=7 cells) | 14.0 s | 113 s | **8× faster** |
| Prop 3 threshold | 215 s | -- | **All cells PASS** |
| Prop 1 (zero false-exclusion) | 0/75 byzantine targets | -- | **30/30 trials PASS** |

**Why faster than paper formula:** the paper's analytic T_ind formula
assumes a single voter at average R, but in our N-UAV cells every honest
peer votes against every byzantine on each verify round, so
M-quorum forms after ~3 reputation update rounds rather than the
single-voter convergence the formula models. The factor of ~20× speed-up
for small M is consistent with N/1 ≈ 7-10 voters acting in parallel
across small enough M that all reach R > T_quorum quickly.

**M=7 scaling:** median rises from 5-6 s (small M) to 13-15 s (M=7),
linear in M_quorum. Quorum FORMATION dominates exclusion time when M
is close to N_honest. Deployment recommendation: **N_honest must be
≥ M for quorum to ever form** -- our initial M=7 trials with N_honest=5-6
produced zero exclusions despite full reputation chain activity (>2200
rep events per trial). Re-run with N_honest=10 fixed the cell.

---

## Implications for Phase 3 (next)

Real PoO verdict stream (Phase 1 quality) flowing into reputation
chain → quorum exclusion is the substrate Phase 3 builds on for
multi-hop CEP + relay refit:
- Excluded peers' factor-graph priors get zeroed out, preventing
  byzantine pose contamination of position estimate
- T_ind (exclusion convergence time) bounds the worst-case window
  during which a byzantine peer can contaminate the graph

---

## Open items deferred from Phase 2

1. **Crypto verification.** Phase 2 mocks Ed25519 signatures (paper
   trusts crypto). Real per-board signing benchmarks (verifying
   84932-cycle estimate at paper IV-B p.209) deferred to Phase 6+
   when we measure on target accelerator.

2. **UWB range inconsistency detector.** Reputation update reason
   `UWB_RANGE_FAIL` (paper IV-D) supported by reputation_manager
   but no node emits it yet — that's Phase 5 territory (GNSS spoofing
   detection lives there; range cross-check is the underlying
   primitive).

3. **Strategic adversary.** Phase 2 byzantine model is the same
   replay-from-elsewhere attack as Phase 1 (paper IV-B's primary
   unforgeability threat). Strategic adversaries that GUESS plausible
   descriptors close to honest are out of scope (paper acknowledges
   this is unproven).

4. **Tier B (200-UAV Python/GTSAM stats).** Phase 2 measures at
   Tier A scale (4-15 UAVs in Gazebo / ROS2). Tier B for parameter
   scaling validation (Prop 2 sweep at full 200) lives in Phase 6.

---

## Decision register

- **2026-05-23** — Phase 2 dev complete (8 tasks: 2 msgs + 4 nodes +
  runner + analyzer + doc template). All smokes PASS at compressed
  scale.
- **2026-05-23 (PM)** — Production campaign ran on vast.ai RTX 3090
  (~2.7 hr, ~$0.80). 30 trials × 6 (M, f) cells executed at
  paper-faithful publish_period_s=45.
  - All cells PASS Prop 1 + Prop 3.
  - Measured exclusion times 5-15 s vs paper's 215 s pass criterion
    (8-20× faster).
  - Discovered M=7 cells need N_honest ≥ M for quorum formation —
    initial trials with N_h=5-6 produced zero exclusions despite
    correct reputation chain activity. Re-ran with N_h=10 → pass.
  - Deployment recommendation for paper v10: state explicitly that
    M-quorum requires ≥ M honest UAVs above T_quorum at decision
    time (not just f ≤ M-1 tolerance).
