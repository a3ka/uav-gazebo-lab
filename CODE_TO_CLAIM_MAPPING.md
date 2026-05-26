# Paper Claim → Workspace File Mapping

For every numerical claim in the IEEE Access paper (Sections VI and VII), this
document records the exact `workspaces/<sweep>/` artefact and `jq` query that
produced the number. If a reviewer challenges any value, this is the table to
open.

The paper is the IEEE Access submission (companion to this code release).

---

## Convention

| Tag | Meaning |
|---|---|
| `jq …` | Run inside repo root; queries a single value from a workspace's `analysis.json` |
| CSV path | Aggregation is over a CSV; computation is in the corresponding `phase{N}-analyze.py` script |
| `bash` script | Re-run the full sweep that produced the artefact |

To verify any number end-to-end:

```bash
# 1. Run the cited jq command — should match the paper value (within rounding)
jq '.summary.detection_rate_per_victim' workspaces/phase5-prod/analysis.json
# → 0.9833 (paper §VI-F: 98.3 %)

# 2. (Optional) Re-derive analysis.json from raw sweep.csv
python3 scripts/phase5-analyze.py --csv workspaces/phase5-prod/results.csv \
                                    --out workspaces/phase5-prod/analysis.json

# 3. (Optional) Re-run the full sweep from scratch
JOBS=2 bash scripts/phase5-campaign.sh
```

---

## Section VI — Empirical Validation (Phases 1-7)

### §VI-B Phase 1 — Proof-of-Observation FAR/FRR

| Paper claim | Source |
|---|---|
| AUC = 0.9996 | `workspaces/phase1-sweep/baseline-paper.csv` ROC over 500 honest + 500 byzantine V_score rows |
| FAR = 0.4 %, FRR = 3.0 % at T_verify = 0.30 (paper-spec) | `awk -F, 'NR>1 && $2=="honest" {h++; if($4<0.30) hr++} NR>1 && $2=="byzantine" {b++; if($4>=0.30) ba++} END {print "FAR="ba/b*100" FRR="hr/h*100}' workspaces/phase1-sweep/baseline-paper.csv` |
| FAR = 0 %, FRR = 4.6 % at T_verify = 0.32 (zero-FAR operating point) | same awk, threshold 0.32 |

Re-sweep: `bash scripts/phase1-batch-sweep.sh` (~30 min GPU on vast.ai).

### §VI-C Phase 3 — CEP vs relay depth + sigma_k refit

| Paper claim | Source |
|---|---|
| CEP_50 median at k=3 = 23.3 m | `jq '.per_k[3].cep50_median' workspaces/phase3-prod-v4/analysis.json` |
| sigma_0 = 19.4 m, delta = 0.088 (empirical GDOP fit) | `jq '.fits.gdop' workspaces/phase3-prod-v4/analysis.json` |
| Linear/GDOP ΔAIC < 1 statistical tie | `jq '.fits.linear.aic, .fits.gdop.aic' workspaces/phase3-prod-v4/analysis.json` → 12.88 vs 13.45 |
| Per-k row 0/1/2/3/5 — full table | `jq '.per_k' workspaces/phase3-prod-v4/analysis.json` |
| Sparse-chain k=1 CEP = 33 m | `jq '.per_k[1].cep50_median' workspaces/phase7-sparse-chain/analysis.json` |

Re-sweep: `JOBS=8 bash scripts/phase3-batch-campaign.sh` (~28 min CPU).

### §VI-D Phase 4 — Failover timing (1200 measurements)

| Paper claim | Source |
|---|---|
| Silence-failover p99 = 6.19–6.24 s (S1/S2/S3) | `jq '.per_scenario | map({s: .scenario, p99: .switch_time_p99})' workspaces/phase4-prod/analysis.json` |
| Reputation-failover (S5) p99 = 1.94 s | `jq '.per_scenario[3].switch_time_p99' workspaces/phase4-prod/analysis.json` |
| 100 % pass rate all four scenarios | `jq '.per_scenario | map(.pass_rate)' workspaces/phase4-prod/analysis.json` |
| 1200 total measurements | 4 scenarios × 30 trials × 10 followers = 1200 |

Re-sweep: `JOBS=4 bash scripts/phase4-campaign.sh` (~25 min CPU).

### §VI-E Phase 2 — Reputation-driven Byzantine exclusion

| Paper claim | Source |
|---|---|
| 30/30 trials, 0 false honest exclusions | Per-trial CSV pairs: `workspaces/phase2-batch/m{M}f{F}-trial{i}.exclusions.csv` (6 cells × 5 trials = 30 files) |
| Median exclusion 5-15 s across (M, f) cells | Aggregation in `docs/results/phase-2.md` Section "Cell-level results" |
| 20× faster than analytical 215 s bound | Derivation: 215 / ~10 (measured median across cells) |

Re-sweep: `bash scripts/phase2-batch-campaign.sh` (~10 min GPU on vast.ai).

### §VI-F Phase 5 — GNSS-spoofing detection

| Paper claim | Source |
|---|---|
| 98.3 % detection (59 / 60 victims) | `jq '.summary.detection_rate_per_victim' workspaces/phase5-prod/analysis.json` |
| 0 false positives | `jq '.summary.total_fp' workspaces/phase5-prod/analysis.json` |
| Detection time p99 = 0.60 s | `jq '.summary.t_detect_p99_s' workspaces/phase5-prod/analysis.json` |
| 30 trials × 2 victims × N = 20 swarm | `jq '.summary.n_trials, .summary.n_victims, .summary.mean_n_uavs' workspaces/phase5-prod/analysis.json` |
| Operational threshold T_spoof = 20 m | `jq '.t_spoof_m' workspaces/phase5-prod/manifest.json` (tighter than the §IV-G design spec of 50 m; rationale in paper §VI-F Configuration) |

Re-sweep: `JOBS=2 bash scripts/phase5-campaign.sh` (~20 min CPU).

### §VI-G Phase 6 — Progressive attrition with admission control

| Paper claim | Source |
|---|---|
| 14 / 15 mission survival (with admission control) | `jq '.summary.mission_survived, .summary.trials' workspaces/phase6-tier-b-prod-v3/analysis.json` |
| over_cap = 0.000 s (with admission control) | `jq '.summary.over_cap_interval_max_max' workspaces/phase6-tier-b-prod-v3/analysis.json` |
| 15 / 15 mission survival but over_cap = 29.8 s (no admission control, Pareto pair) | `workspaces/phase6-tier-b-prod/analysis.json` baseline |
| Pareto trade-off — both numbers reported | Both workspaces above |
| Tier A Gazebo single trial switching time = 6.10 s | Documented in `docs/results/phase-6.md` section "Tier A" |

Re-sweep: `JOBS=2 bash scripts/phase6-tier-b-campaign.sh` (~17 min CPU).

### §VI-H Phase 7 — Single-pillar ablation

| Paper claim | Source |
|---|---|
| ABL1 spoof-detection 98.3 % → 0 % (PoO disabled) | `workspaces/phase7-abl1-nospoof/analysis.json` vs `workspaces/phase5-prod/analysis.json` |
| ABL2 failover 6.08 s → 31.0 s with T_timeout = 30 s (~5×) | `workspaces/phase7-abl2-nofailover/analysis.json` vs `workspaces/phase4-prod/analysis.json` |
| ABL3 α_cap → 0 yields no change in over_cap | `workspaces/phase7-abl3-noloadbal/analysis.json` |
| ABL4 no-TRN k=0 baseline 17.40 m → 37.73 m ablation (+117 %, 2.17×) | `workspaces/phase3-baseline-v3-50/sweep.csv` (50-trial paired with-TRN baseline) vs `workspaces/phase7-abl4-notrn-v4/sweep.csv` (50-trial paired no-TRN ablation) |
| ABL4 no-TRN k=3 baseline 21.67 m → 28.63 m ablation (+32 %, 1.32×) | same workspaces, k=3 rows |

Re-runs:
- `bash scripts/phase7-ablation-runner.sh` (~30 min CPU for all 4 abls)
- ABL4 paired 50-trial re-run (separately): per `phase3-batch-sweep.py` with k_list=[0,3] trials_per_k=50

---

## Section VII — Baseline Comparison (Phase 8)

### §VII-A Nominal failover comparison

| Paper claim | Source |
|---|---|
| Raft median failover = 5.087 s | `jq '.raft.median' workspaces/phase8-prod/comparison.json` |
| Ours median failover = 6.080 s | `jq '.ours.median' workspaces/phase8-prod/comparison.json` |
| ~ 1 s gap (capacity-coordination overhead) | 6.080 - 5.087 = 0.993 |
| 10 trials per protocol, N = 5 peers | `jq '.n_members, .trials_per_protocol' workspaces/phase8-prod/comparison.json` |

### §VII-B Byzantine adversarial measurement

| Paper claim | Source |
|---|---|
| 19 / 19 heartbeats from Byzantine attacker (100 %) | `jq '.byzantine_heartbeats, .total_heartbeats' workspaces/phase8-prod/byz_t0.json` |
| 0 heartbeats from any honest peer | `jq '.honest_heartbeats' workspaces/phase8-prod/byz_t0.json` |
| 20 s observation window | `jq '.t_observation_s' workspaces/phase8-prod/byz_t0.json` |
| 4 honest peers + 1 Byzantine (N = 5) | `jq '.n_members, .n_byzantine' workspaces/phase8-prod/byz_t0.json` |
| Our protocol excludes Byzantine within p99 < 0.6 s | Cross-reference to §VI-F Phase 5 detection time p99 (Pillar 5 mechanism) |

Re-sweep: `bash scripts/phase8-campaign.sh` (~5 min CPU).

---

## Section IV (Approach) — derived numbers

### §IV-E Empirical refit paragraph

| Paper claim | Source |
|---|---|
| sigma_0 = 19.4 m, delta = 0.088 (empirical) | same as §VI-C above |
| Tightening: paper-v9 delta = 0.15 was conservative | derivation: 0.15 / 0.088 ≈ 1.7× tightening |

### §IV-G Admission control v10 patch paragraph

| Paper claim | Source |
|---|---|
| Thundering-herd 30 s over_cap window (baseline) | §VI-G Phase 6 no-AC variant above |
| Both mitigations together reduce over_cap to 0 | §VI-G Phase 6 with-AC variant above |
| Pareto cost: 1 unattached follower per 15 trials | §VI-G with-AC variant above |

---

## Reproducibility pins

Each phase's results doc records the exact reproduction state:

| Phase | Pins doc |
|---|---|
| 1 | `docs/results/phase-1.md` |
| 2 | `docs/results/phase-2.md` |
| 3 | `docs/results/phase-3.md` |
| 4 | `docs/results/phase-4.md` |
| 5 | `docs/results/phase-5.md` |
| 6 | `docs/results/phase-6.md` |
| 6 Tier A | `docs/results/phase-6-tier-a-trial.md` |
| 7 | `docs/results/phase-7.md` |
| 8 | `docs/results/phase-8.md` |

Each pin includes Docker image digest, git commit at sweep start, manifest of
sweep parameters (k_list, trials_per_k, sigma_uwb_m, sigma_trn_m, seed_base,
trn_period_s, wall_time_s).

---

## What is *not* in this mapping

- Sections VIII / IX / X numbers (abstract Monte Carlo studies) live in the
  companion repo
  [`ok-research/bft-uav-swarm-validation`](https://github.com/ok-research/bft-uav-swarm-validation)
  at tag `v1.1`; their code-to-claim mapping is in that repository's README.
- Theoretical predictions in §IV-E Table tab:cep_predicted (the 30-50 / 45-79 /
  ... ranges) are analytical derivations from the per-hop noise model, not
  measurements; their source is the equations in §IV-D / §IV-E themselves.
- Hyperparameter table tab:hyperparams values are design parameters, not
  measurements; their source is the deployment specification in §IV.

---

## Audit harness independence

This repository's claims have been independently audited by a separate
fabrication-detection pipeline at
[`audit-harness`](https://github.com/ok-research/audit-harness) (or similar
fork). The audit cross-references every paper number against the workspace
files cited above; the most recent audit (2026-05-26) returned READY-TO-SUBMIT
with 0 critical / 0 major / 0 minor unresolved findings.
