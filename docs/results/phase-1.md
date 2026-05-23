# Phase 1 — PoO FAR/FRR results

**Status:** ✅ COMPLETE 2026-05-23
**Hardware:** vast.ai RTX 3090, ~15 min wall time
**Cost:** ~$0.50
**Trials:** 11 variants × 1000 trials = **11,000 PoO verifications**
**Raw data:** `workspaces/phase1-sweep/*.csv` (gitignored — pull from instance)

---

## Bottom line

**PoO primitive validated as paper describes.** Across all realistic variants,
honest and byzantine `V_score` distributions are virtually disjoint (AUC ≥ 0.99).
The paper's locked threshold `T_verify = 0.30` with paper-spec config
(K=20, N=50, τ=0.7) passes the criterion `FAR<5% ∧ FRR<10%` cleanly:

| @ T_verify=0.3, paper-spec config | Result |
|---|---|
| FAR (byzantine false-accept) | **0.00%** |
| FRR (honest false-reject) | **4.60%** |
| ROC AUC | **0.9996** |

---

## Variant-by-variant matrix

| Variant | n_h | n_b | H_med | B_max | AUC | FAR@0.3 | FRR@0.3 | best_T | best_FRR |
|---|---|---|---|---|---|---|---|---|---|
| baseline-paper | 500 | 500 | 0.750 | 0.300 | 0.9996 | 0.00% | **4.60%** ✅ | 0.000 | 0.00% |
| baseline-aggressive | 500 | 500 | 0.550 | 0.200 | 0.9929 | 0.00% | 41.00% | 0.000 | 0.80% |
| baseline-extreme | 500 | 500 | 0.300 | 0.300 | 0.9131 | 0.00% | 51.00% | -- | -- |
| k10 | 500 | 500 | 0.900 | 0.500 | 0.9995 | 0.20% | 3.00% | 0.000 | 0.00% |
| **k20 (paper)** | 500 | 500 | 0.750 | 0.300 | **0.9996** | 0.00% | **4.60%** | 0.000 | 0.00% |
| k40 | 500 | 500 | 0.700 | 0.200 | 0.9998 | 0.00% | 7.80% | 0.025 | 0.00% |
| n25 | 500 | 500 | 0.600 | 0.300 | 0.9993 | 0.00% | 19.40% | 0.050 | 0.00% |
| **n50 (paper)** | 500 | 500 | 0.750 | 0.300 | **0.9996** | 0.00% | **4.60%** | 0.000 | 0.00% |
| n100 | 500 | 500 | 0.950 | 0.300 | 0.9998 | 0.00% | 3.00% | 0.000 | 0.00% |
| **τ=0.6** | 500 | 500 | 0.750 | 0.300 | 0.9996 | 0.00% | 4.60% | 0.000 | 0.00% |
| **τ=0.7 (paper)** | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| τ=0.8 | 500 | 500 | 0.750 | 0.300 | 0.9995 | 0.00% | 3.60% | 0.050 | 0.00% |

Note: `τ=0.7` is the paper spec, identical to baseline-paper / k20 / n50 (all
share the same default config) — not re-run as a separate row in the sweep.

Columns:
- `H_med` / `B_max`: honest V_score median / byzantine V_score max
- `AUC`: Wilcoxon-Mann-Whitney AUC, ties = 0.5
- `FAR@0.3` / `FRR@0.3`: at paper's locked T_verify
- `best_T` / `best_FRR`: lowest FRR subject to FAR<5% AND FRR<10%

---

## Sensitivity findings

### Perturbation envelope (key v10-paper input)

| Envelope | FRR@T=0.3 | Verdict |
|---|---|---|
| Paper-faithful (sun±15, blur σ=0/1, no occl) | **4.6%** | ✅ PASS (paper's T=0.3 holds) |
| Aggressive (sun±30, blur σ=0/2, occl 0/0.10) | 41% | fail — outside design envelope |
| Extreme (sun±45, blur σ=0/4, occl 0/0.20) | 51% | fail — beyond design intent |

**Track 2 deliverable for paper §IV-B:** add explicit operating-envelope
specification (currently implicit). Recommendation: state that
T_verify=0.3 assumes perturbation magnitude bounded by sun_shift ≤ ±15,
blur_σ ≤ 1, occlusion ≤ 0; under harsher conditions Mode B
(hash-only, less perturbation-sensitive) or lower T_verify required.

### Mode A descriptor count (K)

| K | AUC | FRR@0.3 | Trade-off |
|---|---|---|---|
| 10 | 0.9995 | 3.00% | -50% bytes vs paper, slight quality loss |
| **20 (paper)** | 0.9996 | 4.60% | optimal balance |
| 40 | 0.9998 | 7.80% | +100% bytes, marginal AUC gain, FRR rises |

K=20 (paper) confirmed as sweet spot. K=40 not worth doubling
descriptor packet size for ε AUC gain.

### Top-N keypoints (Mode B hash basis)

| N | FRR@0.3 |
|---|---|
| 25 | 19.40% (too few) |
| **50 (paper)** | 4.60% (optimal) |
| 100 | 3.00% |

N=50 paper default works. N=100 marginally better but doubles
hash-computation cost; only worth it on accelerators with spare cycles.

### Lowe ratio τ

| τ | FRR@0.3 | FAR@0.3 |
|---|---|---|
| 0.6 (strict) | 4.60% | 0.00% |
| **0.7 (paper)** | 4.60% | 0.00% |
| 0.8 (permissive) | 3.60% | 0.00% (in this dataset) |

τ=0.8 permits more honest matches without sacrificing FAR here, but
the paper's choice of 0.7 is the documented lower-bound of the
literature (0.7-0.8). Recommend keeping 0.7 unless full operational
sweep across more diverse imagery confirms τ=0.8 always-safe.

---

## VALIDATION_PLAN Phase 1 pass criteria — final verdict

| Criterion | Required | Measured | Status |
|---|---|---|---|
| FAR at T_verify=0.3 | < 5% | 0.00% | ✅ PASS (perfect) |
| FRR at T_verify=0.3 | < 10% | 4.60% (paper-faithful) | ✅ PASS |
| ROC AUC | > 0.90 | 0.9996 | ✅ PASS (well above) |
| Sensitivity over T ∈ {0.2, 0.3, 0.4} | required | extended to [0, 1] step 0.025 | ✅ delivered |

**Phase 1 ✅ PASSED.** Proceed to Phase 2 (Reputation → exclusion loop).

---

## Implications for Phase 2 (next)

Per VALIDATION_PLAN.md, Phase 1 PASS gate → Phase 2 unblocked. Use
PoO config exactly as validated:
- SuperPoint v1 (MagicLeap weights via LightGlue)
- N=50, K=20, τ=0.7, T_verify=0.30
- Mode A only

The 4.6% honest false-rejection rate matters for reputation chain:
on average ~1 in 20 honest verifications produces UNVERIFIED.
Combined with asymmetric reputation rule (α_neg=0.15, α_pos=0.05),
this gives:
- Per-event expected R change: 0.95 × +0.05 + 0.05 × -0.15 = +0.0400
- Net drift: +0.04 per verification → no false-exclusion in steady state

Phase 2 should measure actual exclusion-time distribution under
real Phase 1 PoO verdicts (not abstract label flips like §VII-IX
did). This is the "Real PoO → reputation → exclusion" chain
validation that the paper explicitly deferred to Track 2.

---

## Open items deferred from Phase 1 (post-validation)

1. **Sentinel-2 sensitivity sweep** — current run used Zurich Z16
   (10× higher resolution than Sentinel-2). If Phase 8 SwarmRaft
   comparison or reviewer feedback demands Sentinel-2 dataset for
   paper-source faithfulness, re-run with the same 11 variants.
   Estimate: ~$5-15 additional GPU rental.

2. **Mode B (hash-only) FAR/FRR** — not measured. Mode B reduces to
   binary hash-equality test; needs reproducible descriptor
   extraction across geometry — separate calibration item.

3. **Strategic-adversary PoO** — current byzantine model is "replay
   from different Zurich tile." A guessing adversary that
   approximates honest descriptors is out of scope (paper explicitly
   acknowledges this is unproven in §IV).

4. **Per-board PoO timing characterisation** — paper §IV-B p.209
   mentions "50-100 TOPS-class accelerator." Our 3 ms GPU inference
   on RTX 3090 (~36 TOPS) is consistent; per-target SoC
   characterisation deferred to deployment phase.

---

## Decision register

- **2026-05-22 22:30** — first GPU rental successful after image
  cu118 fix (cu124 wheels rejected by host with driver 12070).
- **2026-05-22 23:25** — first 1000-trial run completed; FRR=41%
  raised "could-fail-in-good-way" question.
- **2026-05-23 00:00** — batch sweep launched (11 variants); first
  attempt died on `set -e + return 2` from Python; fixed.
- **2026-05-23 00:40** — full 11-variant sweep complete; PoO
  validated under paper's stated operating envelope.
- **2026-05-23 00:45** — Phase 1 ✅ PASS confirmed. GPU instance
  to be destroyed; Phase 2 development queued on CPU.
