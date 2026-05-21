# Cost budget — running spend per phase

Required by `CLAUDE.md` Hard Rule 6 (cost-tracking).

All values in USD. `Estimate` from `VALIDATION_PLAN.md`. `Spent` filled
after invoice (vast.ai dashboard for GPU; Copernicus is free; local dev
electricity not tracked here).

Cumulative budget cap: **$500** (~30% buffer over $395 upper estimate).
If cumulative spent approaches $400, stop and re-budget with user.

| Phase | Estimate (low) | Estimate (high) | Spent | Status |
|---|---:|---:|---:|---|
| Phase 0 (incl. PF-7 docker build) | 0 | 0 | — | pending |
| Phase 1 — PoO FAR/FRR | 15 | 50 | — | pending |
| Phase 2 — Reputation loop | 20 | 65 | — | pending |
| Phase 3 — CEP + relay refit | 30 | 100 | — | pending |
| Phase 4 — Failover timing | 0 | 0 | — | pending |
| Phase 5 — GNSS spoofing reaction | 0 | 0 | — | pending |
| Phase 6 — Attrition + load balancing | 20 | 50 | — | pending |
| Phase 7 — Ablation | 30 | 80 | — | pending |
| Phase 8 — SwarmRaft baseline | 15 | 50 | — | pending |
| **Total** | **130** | **395** | **0** | — |

## Pre-flight spend

| Item | Amount | Date | Note |
|---|---:|---|---|
| vast.ai initial deposit (PF-3) | — | — | $50 target on first signup |

## Notes

- vast.ai pricing volatile — RTX 4090 ranges $0.40-1.00/hr depending on
  region + demand. Estimates assume $0.50-0.80/hr median.
- Phase 7 (ablation) re-runs Phase 1/3/6 configs — could be cheaper if
  results cached / partial.
- Phase 8 implementation cost (if no open-source SwarmRaft ref, +2 wk
  dev) is time, not GPU dollars. Tracked separately in
  `docs/results/phase-8.md` once started.
- Storage on vast.ai (~$0.10/GB-month for persistent volumes) not used
  by default — rebuild image per session keeps storage cost $0.
