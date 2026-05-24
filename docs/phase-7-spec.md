# Phase 7 — Ablation (spec)

**Validates:** Each pillar is NECESSARY — disabling any one
meaningfully degrades the measured metric.
**Hardware:** local CPU (re-runs of Phase 4/5/6 sweeps with single-
pillar disabled).
**Cost:** $0.
**Wall-time estimate:** ~1 hour active dev + ~30-60 min sweeps.

This phase doesn't need new physics or new protocols — it re-runs
existing infrastructure with one feature flag flipped per variant.

---

## Ablation variants (paper-mandated)

| ABL | Disabled pillar | Base phase | Metric | Pass = degradation ≥30% |
|---|---|---|---|---|
| ABL1 | Reputation weighting | Phase 5 (spoof detection) | detection rate | rate drops below 70% |
| ABL2 | Failover | Phase 4 (anchor death) | mission survival | drops below 70% |
| ABL3 | Load balancing (α_cap=0) | Phase 6 Tier B | load variance | std(n_attached) doubles |
| ABL4 | TRN absolute fix | Phase 3 (CEP k=3) | CEP_50 at k=3 | grows >2× |

Each ablation is run for 5-10 trials (enough for monotone signal vs the
established-baseline median; not a full statistical sweep).

---

## Implementation task tree

### 7.1 — Disable flags on existing nodes

| Flag | Default | Disabled value |
|---|---|---|
| `t_timeout` (follower_node) | 5.0 | 10000.0 → no failover ever fires |
| `alpha_cap` (follower_node) | 0.25 | 0.0 → no load-balancing weight |
| `t_spoof_m` (spoof_detector) | 20.0 | 1e9 → never triggers |
| `sigma_trn_m` (trn_anchor) | 5.0 | 1e9 → effectively no TRN |
| `sigma_base / gossip_sigma` (factor_graph) | 50.0 | already large; no extra flag |

All flags are existing parameter; no node changes needed.

### 7.2 — `phase7-ablation-runner.py`

For each ABL variant, spawn the corresponding phase's batch sweep with
the disabled-pillar flag, store under `workspaces/phase7-<abl_id>/`.

### 7.3 — Aggregator + results doc

`phase7-aggregate.py` reads each ablation's analysis.json + the
baseline production sweep from Phase 3/4/5/6, computes degradation %,
writes `docs/results/phase-7.md` with the comparison table.

---

## Honest scope limits

1. **N matches each base phase** — not paper's full N=200 for ablation
   (would 10× the runtime).
2. **5-10 trials per ablation, not full 30** — sufficient for
   ≥30% degradation visibility but not for tight CI.
3. **No "trusted boot" ablation** (Pillar 1) — Pillar 1 not implemented
   in any phase; can't ablate what isn't there.
