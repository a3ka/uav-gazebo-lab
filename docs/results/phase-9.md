# Phase 9 — PoO same-region forgery results

**Status:** EXECUTED (see docs/phase-9-spec.md for pre-registered design)
**Trials:** honest=500 | wrong-region fab=500 | same-region fab=500
**T_verify:** 0.30

## Headline

| Population | median V_score | n |
|---|---:|---:|
| honest revisit       | 1.000  | 500 |
| wrong-region fab     | 0.000 | 500 |
| **same-region fab**  | **0.000** | 500 |

AUC (honest vs same-region fab) = **0.9217**

## Same-region V_score by temporal gap

| Gap bin | n | median V | mean V |
|---|---:|---:|---:|
| same-season (<=90d) | 41 | 0.000 | 0.096 |
| cross-season (91-365d) | 338 | 0.000 | 0.097 |
| cross-year (>365d) | 121 | 0.000 | 0.100 |

## Operating points (T_verify sweep)

| T_verify | FRR (honest) | FAR_wrong-region | FAR_same-region |
|---:|---:|---:|---:|
| 0.20 | 10.60% | 0.00% | 13.80% |
| 0.25 | 10.60% | 0.00% | 11.20% |
| 0.30 | 10.60% | 0.00% | 10.00% |
| 0.32 | 10.60% | 0.00% | 10.00% |
| 0.35 | 10.60% | 0.00% | 9.60% |
| 0.50 | 10.60% | 0.00% | 7.40% |

## Pre-registered interpretation outcome

Same-region median V_score = **0.000** → STRENGTHEN — same-region forgery defeated; Mode A unforgeability claim is observably supported.

**Tail caveat (not pre-registered, disclosed for completeness):** the operating-point table above shows that although the *median* same-region V_score is at floor, the upper tail of the same-region distribution does cross T_verify on a non-trivial fraction of trials (see FAR_same-region column). Same-region fabrication is therefore *harder* than wrong-region fabrication but not impossible at the paper-spec T_verify = 0.30; the §IV-B/§XI-A wording should reflect both the floor median and this tail.

## Artefacts

- Raw CSV: `workspaces/phase9-sweep/forgery_trials.csv`
- Histogram: `workspaces/phase9-sweep/figures/histogram_v_score.png`
- ROC: `workspaces/phase9-sweep/figures/roc_curve.png`

