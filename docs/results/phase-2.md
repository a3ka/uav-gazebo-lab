# Phase 2 — Reputation → Exclusion Loop results

**Status:** template (dev complete, campaign pending GPU rental)
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

## Final results matrix (TBD post-campaign)

| Cell | trials | n_byz_excluded | n_honest_excluded | median t_byz | p95 t_byz | Prop1 | Prop3 |
|---|---|---|---|---|---|---|---|
| (M=3, f=1) | -- | -- | -- | -- | -- | -- | -- |
| (M=3, f=2) | -- | -- | -- | -- | -- | -- | -- |
| (M=5, f=2) | -- | -- | -- | -- | -- | -- | -- |
| (M=5, f=3) | -- | -- | -- | -- | -- | -- | -- |
| (M=7, f=3) | -- | -- | -- | -- | -- | -- | -- |
| (M=7, f=4) | -- | -- | -- | -- | -- | -- | -- |

| Aggregate metric | Measured | Paper formula | Within ±15%? |
|---|---|---|---|
| Median first-exclusion time | -- s | 113 s (formula) / 170 s (paper claim) | -- |
| 95th percentile | -- s | -- | -- |
| AUC of verdict stream | -- | > 0.95 | -- |

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

## Decision register (TBD entries fill in post-campaign)

- **2026-05-23** — Phase 2 dev complete (8 tasks: 2 msgs + 4 nodes +
  runner + analyzer + doc template). All smokes PASS at compressed
  scale. GPU rental queued for paper-faithful production campaign.
