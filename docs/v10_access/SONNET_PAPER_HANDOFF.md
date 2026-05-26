# Sonnet Handoff — Paper v10 (IEEE Access) Check-and-Test Guide

**Audience:** Claude Sonnet 4.6 (or any future model) picking up paper work
on `docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.tex`.
**Purpose:** Everything a fresh agent needs to (a) re-read the source-of-truth
artefacts, (b) re-run any measurement on demand, and (c) verify a paper claim
against the data without re-deriving the lab structure.
**Read order:** this doc first, then `CLAUDE.md`, then `docs/VALIDATION_PLAN.md`.

---

## 0. Boundary rules (inherit from `CLAUDE.md`)

1. **Two-tier scale is by design.** Gazebo for N≤20 mechanism validation;
   Python/GTSAM Monte Carlo for N≤200 statistics. **Never** propose
   200-UAV Gazebo runs — they are computationally infeasible.
2. **No LLM-in-the-loop measurements.** Everything in `workspaces/` was
   produced by deterministic ROS2/Python code. If a number changes,
   re-run the sweep; do not "estimate" it.
3. **Docker-first.** All execution happens inside `uav-lab:cpu` (Phases
   0/3/4/5/6/7/8) or `uav-lab:gpu` (Phases 1/2). Do not `apt install`
   on host.
4. **Risk-first phase ordering.** Phase 1 (PoO) and Phase 2 (reputation
   exclusion) block downstream work. Never reorder.
5. **Raw data is authoritative.** If `analysis.json` and a phase-N.md
   summary disagree, the JSON wins. Update the doc.

---

## 1. Source-of-truth file map

### 1.1 Paper LaTeX
| File | Role |
|---|---|
| `docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.tex` | **The paper.** Sole source. 1240 lines. |
| `docs/reference/BFT_UAV_Swarm_Paper_v9_8.tex` | Frozen v9.8 (arXiv). Do NOT edit — diff target only. |

### 1.2 Per-phase results documents
| Doc | Phase claim covered |
|---|---|
| `docs/results/phase-1.md` | PoO FAR/FRR, AUC, paper-spec threshold |
| `docs/results/phase-2.md` | Reputation-driven Byzantine exclusion (M, f sweep) |
| `docs/results/phase-3.md` | CEP vs hops, σ_k empirical refit (v4 final) |
| `docs/results/phase-4.md` | Anchor-failover timing (4 scenarios, 1200 switches) |
| `docs/results/phase-5.md` | GNSS-spoof detection rate + latency |
| `docs/results/phase-6.md` | Progressive attrition + admission control (Tier B) |
| `docs/results/phase-6-tier-a-trial.md` | 1-trial Gazebo demo (Tier A foundation) |
| `docs/results/phase-7.md` | Single-pillar ablation (4 ABLs) |
| `docs/results/phase-8.md` | Vanilla-Raft baseline + Byzantine adversarial trial |

### 1.3 Production-sweep workspaces (raw data)
Layout: each contains `manifest.json` (config), `results.csv` or
`sweep.csv` (raw per-trial), `analysis.json` (aggregated metrics),
optional `*.png` (plots). **Always pair the workspace name with its
phase-N.md doc.**

| Workspace | Phase | Key file for paper number |
|---|---|---|
| `workspaces/phase1-sweep/` | 1 | `baseline-paper.csv` → AUC=0.9996 |
| `workspaces/phase2-batch/` | 2 | 30 `m{M}f{F}-trial{i}.exclusions.csv` pairs |
| `workspaces/phase3-prod-v4/` | 3 | `analysis.json` → CEP@k=3 = 23.3 m; σ_k δ=0.088 |
| `workspaces/phase4-prod/` | 4 | `analysis.json` → p99 silence-failover = 6.24 s |
| `workspaces/phase5-prod/` | 5 | `analysis.json` → detection=98.3%, p99 latency=0.60 s |
| `workspaces/phase6-tier-b-prod-v3/` | 6 | `analysis.json` → over_cap=0, 14/15 mission_survived |
| `workspaces/phase7-abl{1..4}-*` | 7 | per-ablation `analysis.json` |
| `workspaces/phase7-abl4-notrn-v3/` | 7 ABL4 | final-scaffold TRN ablation (~10% degrade) |
| `workspaces/phase8-prod/` | 8 | `comparison.json` (Raft vs ours nominal), `byz_t0.json` (Byzantine attack) |

**Do NOT cite** any `phase3-prod` (v1) or `phase3-prod-v2` workspace —
sub-metre CEP is a scaffold artefact (see phase-3.md §"Scaffold artefact
pathway"). Only `phase3-prod-v4` numbers go in the paper.

### 1.4 ROS2 source (`src/uav_swarm_nodes/`)
| Node file | Role | Phase |
|---|---|---|
| `anchor_node.py` | TRN anchor + admission control | 3,4,6 |
| `follower_node.py` | iSAM2 client + ATTACH-timeout retry | 3,4,6 |
| `factor_graph_node.py` | GTSAM iSAM2 wrapper | 3 |
| `trn_anchor_node.py` | TRN fix publisher (mocked for 3) | 3 |
| `uwb_ranging_simulator_node.py` | UWB range bus | 3,4,5,6 |
| `position_broadcaster_node.py` | Noisy-pose generator | 3,4,5 |
| `reputation_manager_node.py` | Asymmetric reputation update | 2 |
| `verifier_node.py` | PoO verifier | 1,2 |
| `quorum_exclusion_node.py` | Multi-verifier permanent exclusion | 2 |
| `spoof_detector_node.py` | GNSS vs UWB residual check | 5,7 |
| `attrition_orchestrator_node.py` | Scheduled SIGKILL events | 6 |
| `load_monitor_node.py` | Per-event over-cap/rebal logger | 6 |
| `raft_node.py` | Vanilla-Raft baseline + Byzantine mode | 8 |
| `signed_observation_publisher_node.py` | Test stimulus for §2 | 2 |
| `multi_uwb_simulator_node.py` | Multi-anchor UWB bursts | 4 |
| `comm_logger_node.py` | Per-topic ts/seq log | all |
| `px4_position_bridge_node.py` | PX4↔ROS bridge | 6 Tier A |

### 1.5 Messages (`src/uav_swarm_msgs/msg/`, 18 total)
Stable: `DistilledState`, `NoisyPose`, `EstimatedPose`, `UwbRangeMeasurement`,
`TrnAbsoluteFix`, `SignedObservation`, `ReputationUpdate`,
`PeerReputationView`, `ExclusionEvent`, `SpoofAlert`,
`ReassignRequest`, `ReassignOffer`, `AttachAck`,
`AttritionEvent`, `AnchorLoad`, `RaftHeartbeat`,
`RaftVoteRequest`, `RaftVoteGrant`.

---

## 2. Standard commands

### 2.1 Container entry (every session starts here)
```bash
# CPU image — Phases 0/3/4/5/6/7/8
docker run --rm -it \
  -v /home/nous/research/uav-gazebo-lab:/workspace/uav-gazebo-lab \
  -v /home/nous/research/uav-gazebo-lab/ros2_ws:/workspace/ros2_ws \
  uav-lab:cpu bash

# Inside container, every shell:
source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
```

For GPU phases (1, 2) use the published image:
```bash
docker pull ghcr.io/a3ka/uav-lab:gpu
```

### 2.2 Build ROS2 workspace
```bash
bash /workspace/uav-gazebo-lab/scripts/build-ros2-ws.sh
# Rebuilds only changed packages; safe to re-run.
```

### 2.3 Re-run a phase's production sweep
| Phase | Command | Wall time |
|---|---|---|
| 1 | `python3 scripts/phase1-poo-trials.py ...` + `phase1-batch-sweep.sh` | ~30 min GPU |
| 2 | `bash scripts/phase2-batch-campaign.sh` | ~10 min CPU |
| 3 | `JOBS=8 bash scripts/phase3-batch-campaign.sh` | 28 min CPU |
| 4 | `JOBS=4 bash scripts/phase4-campaign.sh` | ~25 min CPU |
| 5 | `JOBS=2 bash scripts/phase5-campaign.sh` | ~20 min CPU |
| 6 | `JOBS=2 bash scripts/phase6-tier-b-campaign.sh` | 17 min CPU |
| 7 | `bash scripts/phase7-ablation-runner.sh` | ~30 min CPU |
| 8 | `bash scripts/phase8-campaign.sh` | ~5 min CPU |

Each writes to a workspace named in `manifest.json`. Re-running overwrites
in place. Use `run_in_background` for the longer ones.

### 2.4 Re-analyze without re-sweeping
```bash
python3 scripts/phase3-analyze.py workspaces/phase3-prod-v4/
python3 scripts/phase4-analyze.py workspaces/phase4-prod/
python3 scripts/phase5-analyze.py workspaces/phase5-prod/
python3 scripts/phase6-analyze.py workspaces/phase6-tier-b-prod-v3/
python3 scripts/phase2-analyze.py workspaces/phase2-batch/
python3 scripts/phase1-analyze.py workspaces/phase1-sweep/
```
Outputs an updated `analysis.json` in the workspace.

### 2.5 Smoke / sanity checks (fast, ≤2 min)
```bash
bash scripts/smoke-factor-graph.sh        # iSAM2 sanity
bash scripts/smoke-quorum-exclusion.sh    # reputation→exclusion
bash scripts/smoke-reputation-manager.sh  # asymmetric decay
bash scripts/smoke-failover-S1.sh         # silence-triggered failover
bash scripts/smoke-failover-all.sh        # all four failover scenarios
bash scripts/smoke-px4-multi.sh           # 2-vehicle Gazebo + PX4 (longer)
```

### 2.6 Inspect / extract a single measurement
```bash
# Headline numbers from any analysis.json:
jq '.' workspaces/phase4-prod/analysis.json | less

# Phase-3 σ_k fit candidates side-by-side:
jq '.sigma_k_fits' workspaces/phase3-prod-v4/analysis.json

# Phase-8 Byzantine outcome:
jq '.' workspaces/phase8-prod/byz_t0.json
```

### 2.7 Cleanup (after every Gazebo / PX4 session)
```bash
bash scripts/cleanup-host.sh
docker ps              # should be empty
pgrep -u $USER -f 'bin/px4|MicroXRCEAgent|gz sim'  # should be empty
```

---

## 3. Paper-claim → data-source mapping

For every number in `BFT_UAV_Swarm_Paper_v10_access.tex` §VI–§VII, here
is the file the claim comes from. If a reviewer challenges a number,
this is what to open.

| Paper claim (§) | Number | Source artefact |
|---|---|---|
| Abstract / §VI-B | AUC = 0.9996 (PoO) | `workspaces/phase1-sweep/baseline-paper.csv` → ROC; `docs/results/phase-1.md` Table 1 |
| §VI-B | FAR = 0 %, FRR = 4.6 % | `workspaces/phase1-sweep/baseline-paper.csv` at τ=0.30 |
| §VI-C / Table cep_measured | CEP@k=3 = 23.328 m | `jq '.per_k[3].cep50_median' workspaces/phase3-prod-v4/analysis.json` |
| §VI-C / IV-E refit | σ_k empirical δ = 0.0878 | `jq '.fits.gdop' workspaces/phase3-prod-v4/analysis.json` |
| §VI-C | Linear/GDOP ΔAIC < 1 | `jq '.fits.linear.aic, .fits.gdop.aic' …/phase3-prod-v4/analysis.json` |
| §VI-D / Table phase4_measured | Silence-failover p99 = 6.19–6.24 s (S1/S2/S3) | `jq '.per_scenario | map({s: .scenario, p99: .switch_time_p99})' workspaces/phase4-prod/analysis.json` — S1=6.193, S2=6.236, S3=6.225 |
| §VI-D | Reputation-trigger failover (S5) p99 = 1.94 s | same file, `.per_scenario[3].switch_time_p99` |
| §VI-E | Reputation exclusion 30/30 PASS | `workspaces/phase2-batch/m{M}f{F}-trial{i}.exclusions.csv` (30 pairs, 5 cells × 5 trials), aggregated in phase-2.md |
| §VI-F | Spoof detection 98.3 % | `jq '.summary.detection_rate_per_victim' workspaces/phase5-prod/analysis.json` |
| §VI-F | Spoof 0 FP | same file, `.summary.total_fp` |
| §VI-F | Spoof p99 latency = 0.598 s | same file, `.summary.t_detect_p99_s` |
| §VI-G / Table phase6_attrition | over_cap_interval_max = 0 s | `jq '.summary.over_cap_interval_max_max' workspaces/phase6-tier-b-prod-v3/analysis.json` |
| §VI-G | mission_survived 14/15 | same file, `.summary.mission_survived` (denominator `.summary.trials`) |
| §VI-H / Table ablation_measured | ABL1: 98.3 % → 0 % | `workspaces/phase7-abl1-nospoof/analysis.json` `.summary` vs `phase5-prod/analysis.json.summary` |
| §VI-H | ABL2: 6 s → 31 s (≈5×) | `workspaces/phase7-abl2-nofailover/analysis.json` vs `phase4-prod` |
| §VI-H | ABL4 TRN: ~10 % CEP degrade (dense topology) | `workspaces/phase7-abl4-notrn-v3/sweep.csv` (final scaffold; v1/v2 superseded) |
| §VII-A / Table phase8_nominal | Raft 5.087 s vs Ours 6.080 s | `jq '.raft.median, .ours.median' workspaces/phase8-prod/comparison.json` |
| §VII-B / Table phase8_byzantine | 19/19 Byz hbs, 0 honest | `jq '.byzantine_heartbeats, .honest_heartbeats' workspaces/phase8-prod/byz_t0.json` |
| §IV-G admission-control paragraph | Pareto: 14/15 (v3) vs 15/15 baseline + 30 s over-cap | `phase6-tier-b-prod/analysis.json` (v1 baseline) vs `phase6-tier-b-prod-v3/analysis.json` |

---

## 4. Sister-project pointers (Track 1 audit-harness)

The audit-harness lives at `/home/nous/research/audit-harness/`. It is
the **fabrication-audit pipeline** that catches non-existent citations
and fabricated numerical claims. Run it on the v10 PDF before any
external submission:

```bash
cd /home/nous/research/audit-harness
# Audit a finished tex/PDF — see audit-harness docs for current CLI.
```

Do **not** run audit-harness on `phase-N.md` files — those are working
documents, not publication targets.

---

## 5. What to flag (do not silently fix)

If you discover any of the following, **stop and report to the user**
before editing:

1. A paper number that does not match its source artefact.
2. A `\ref{}` resolving to a missing label (use the cross-ref check
   below).
3. A workspace whose `manifest.json` and `analysis.json` describe
   different sweeps (sweep-then-recompute discipline broken).
4. A bibliography entry without a DOI / arXiv ID / publisher URL.
5. Any LaTeX warning of "multiply defined labels" or "undefined
   references" after compile (compile inside docker; texlive-publishers
   is not on host).
6. Any new claim added to the paper that does not trace back to a
   workspace artefact named in §3 above.

### Cross-ref sanity check
```bash
grep -oE '\\ref\{[^}]+\}' docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.tex \
  | sort -u | sed 's/.*{\([^}]*\)}/\1/' > /tmp/refs.txt
grep -oE '\\label\{[^}]+\}' docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.tex \
  | sort -u | sed 's/.*{\([^}]*\)}/\1/' > /tmp/labels.txt
comm -23 /tmp/refs.txt /tmp/labels.txt   # dead refs
comm -13 /tmp/refs.txt /tmp/labels.txt   # unused labels (OK but worth noting)
```

---

## 6. Operating tempo for paper-revision sessions

1. **Read** §1 of this doc + the specific phase-N.md being revised.
2. **Open** the workspace's `analysis.json` and `manifest.json` BEFORE
   touching the LaTeX — confirm the number you are about to write
   exists in the artefact.
3. **Edit** the .tex with a single `Edit` per paragraph (preserves
   diff legibility).
4. **Verify** cross-refs (§5 check) and run the in-docker compile if
   you have shell access to `uav-lab:cpu` (texlive-publishers is in
   the image but not on host).
5. **Update** the phase-N.md doc if the workspace was re-swept.
6. **Do not** invent new claims, citations, or workspace names. If a
   needed measurement does not exist, propose a new phase script and
   wait for user approval before running it.

---

## 7. Quick orientation prompt for a fresh Sonnet session

> "Read `docs/v10_access/SONNET_PAPER_HANDOFF.md` then `CLAUDE.md`.
> The paper is `docs/v10_access/BFT_UAV_Swarm_Paper_v10_access.tex`.
> The task is: \<describe revision\>. Source-of-truth artefacts live
> under `workspaces/phaseN-*`. Do not introduce numbers not present in
> an `analysis.json`. Run the cross-ref check before reporting done."
