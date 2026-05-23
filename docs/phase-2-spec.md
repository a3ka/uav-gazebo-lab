# Phase 2 — Reputation → Exclusion Loop (spec)

**Validates:** Paper Prop 1 (quorum safety) + Prop 3 (convergence ≲ 215 s) +
Prop 2 (parameter scaling) under **real PoO verdicts** from Phase 1's
validated pipeline (not abstract label-flip Monte Carlo of §VII-IX).

**Hardware:** local CPU for dev + integration tests; **vast.ai GPU for
final measurement campaign** (real PoO runs in the loop).

**Cost:** ~$20-65 GPU rental for final campaign.
**Wall-time:** ~2-3 wk total (1-2 wk CPU dev + 1-2 day GPU campaign).

This phase is the second step of the GPU track per VALIDATION_PLAN.md
(Phase 1 ✅ → Phase 2). Without Phase 1 PASS, Phase 2 would have been
blocked; Phase 1's AUC=0.9996 + paper-spec FAR/FRR confirms the
chain's first link works.

---

## Paper anchor

§IV-B (PoO) → §IV-C (Asymmetric Reputation) → §IV-F end (quorum
exclusion):

| Mechanism | Paper formula / constant |
|---|---|
| VERIFIED update | `R_j ← clamp(R_j + α_pos · R_k, 0, 1)` |
| UNVERIFIED update | `R_j ← clamp(R_j - α_neg · R_k, 0, 1)` |
| INVALID_SIG update | `R_j ← clamp(R_j - α_sig, 0, 1)` |
| UWB range inconsistency | `R_j ← clamp(R_j - α_range, 0, 1)` |
| Temporal decay | `V_weighted = V · exp(-λ Δt)`, λ=10⁻³ s⁻¹ |
| Defaults | α_pos=0.05, α_neg=0.15, α_sig=0.30, α_range=0.10 |
| Reject threshold | T_reject = 0.20 |
| Quorum reputation floor | T_quorum = 0.60 |
| Default quorum size | M = 3 (tolerates f ≤ M-1 = 2 colluding byzantine) |
| Predicted exclusion time | T_ind ≈ (R_init - T_reject) / (α_neg · R̄_honest · ν_verify) ≈ 170 s |

Quorum exclusion (§IV-F end): "permanent exclusion additionally
requires M independent UAVs, each with R > T_quorum=0.6, to confirm
the exclusion."

---

## Architecture

```
┌─────────────────┐    SignedObservation    ┌─────────────────┐
│ honest UAV i    ├────────────────────────▶│ verifier UAV j  │
│  - emits OBS    │     (cryptographic)     │  - runs PoO     │
└─────────────────┘                         │    (validated   │
                                            │    Phase 1)     │
┌─────────────────┐    SignedObservation    │  - VERIFIED /   │
│ byzantine UAV i ├────────────────────────▶│    UNVERIFIED   │
│  - replays from │  (descriptors mismatch  └────────┬────────┘
│    other tile   │   verifier's revisit)           │
└─────────────────┘                                  │ ReputationUpdate
                                                    ▼
                                            ┌─────────────────┐
                                            │ rep_manager j   │
                                            │  - maintains    │
                                            │    R_per_peer   │
                                            │  - asymmetric   │
                                            │    update       │
                                            │  - decay        │
                                            └────────┬────────┘
                                                    │ DistilledState
                                                    │ (includes R_j)
                                                    ▼
                                            ┌─────────────────┐
                                            │ quorum exclusion│
                                            │  - sees other   │
                                            │    UAVs' Rs     │
                                            │  - if M voters  │
                                            │    with R>0.6   │
                                            │    say target   │
                                            │    R<0.2 → excl │
                                            └─────────────────┘
```

### Nodes to build

| Node | Phase 2 role |
|---|---|
| `verifier_node` | Wraps Phase 1 PoO pipeline (SuperPoint + Lowe ratio). Subscribes to `/uav<i>/signed_observation`, runs verification on revisit, publishes `ReputationUpdate` on `/reputation/update/u<i>` with reason VERIFIED/UNVERIFIED. |
| `reputation_manager_node` | Per-UAV. Subscribes to `/reputation/update/u<my_id>` (votes against me) AND maintains its OWN view of every peer (subscribes to `/reputation/update/u<peer>`). Applies asymmetric update + decay. Publishes own R in `DistilledState` already; broadcasts internal `R_peer_view` for quorum. |
| `quorum_exclusion_node` | Per-UAV. Subscribes to all peers' broadcasted R views. When sees M ≥ 3 voters with R > T_quorum agreeing target's R < T_reject, logs `ExclusionEvent(target, t)` to `/phase2/exclusions`. |
| `signed_observation_publisher_node` | Per-UAV. Periodically (paper ν_verify⁻¹ = 45 s) emits SignedObservation against its current camera frame (or Zurich tile based on its pose). Two modes: honest (real descriptors), byzantine (replay from offset tile). |
| `phase2_scenario_runner.py` (host-side) | Launches N=10-15 UAVs (mix honest/byzantine), waits for steady-state, kicks off measurement window, collects exclusion events, computes Prop 1/2/3 metrics. |

### New message types (extend uav_swarm_msgs)

- `PeerReputationView.msg` — for inter-UAV R broadcasting:
  ```
  uint64 timestamp
  uint64 voter_id          # who's reporting
  uint64 target_id         # whose R is being reported
  float32 r_value          # voter's view of target's R
  ```
- `ExclusionEvent.msg` — for analysis logging:
  ```
  uint64 timestamp
  uint64 target_id         # excluded peer
  uint64[] voter_ids       # M voters who agreed
  float32 voter_min_r      # min R among voters (must be > T_quorum)
  ```

---

## Implementation task tree

### 2.1 — Extend uav_swarm_msgs (~1 day)

Add 2 messages above to `src/uav_swarm_msgs/msg/`. Update CMakeLists.
Rebuild ros2_ws. Smoke `ros2 interface package uav_swarm_msgs` shows 9
total types.

### 2.2 — `verifier_node` (~2-3 days)

Python ROS2 node. Constructor loads SuperPoint v1 to GPU (skips
gracefully to CPU for unit tests). On `SignedObservation`:
- Verifies Ed25519 signature (mock for Phase 2 — paper trusts signature
  validity; we focus on reputation chain)
- Stores observation in a "to verify later" buffer
- When this verifier's own position enters r_verify=500m of obs.position,
  captures own camera frame, runs SuperPoint+Lowe vs obs.descriptors,
  computes V, compares with T_verify=0.30
- Publishes `ReputationUpdate(target=obs.uav_id, reason=VERIFIED/UNVERIFIED)`

Tests:
- Unit: feed mock honest + byzantine SignedObservations, assert
  correct VERIFIED/UNVERIFIED ratio matches Phase 1 4.6%/0% expectation
- Integration: 2 UAVs (one honest, one byzantine), verifier sees both,
  emits correct updates

### 2.3 — `reputation_manager_node` (~2-3 days)

Per-UAV. Maintains `dict[peer_id, R_value]` initialised at R_init=0.5.
On `ReputationUpdate` for any peer:
- Apply asymmetric update per reason code
- Clamp [0, 1]
- Mark timestamp for decay
On periodic tick (10 Hz):
- Apply temporal decay `R *= exp(-λ Δt)` per peer
On request for own state:
- Inject current `R_per_peer_view` into outgoing `DistilledState`

Tests:
- Unit: feed sequence of 100 VERIFIED + 1 UNVERIFIED → R rises to ~1.0
  then drops by α_neg
- Unit: parameter sensitivity — verify behavior at edge cases
  (R=1.0 + VERIFIED → clamped at 1.0; R=0.0 + UNVERIFIED → stays 0.0)

### 2.4 — `quorum_exclusion_node` (~2 days)

Per-UAV. Subscribes to all peers' `PeerReputationView` broadcasts.
Maintains `dict[target_id, dict[voter_id, (r_value, voter_self_R)]]`.
On every new view OR on periodic tick:
- For each target: collect votes where `voter_self_R > T_quorum` AND
  `view.r_value < T_reject`
- If ≥ M=3 such votes exist (from distinct voters): publish
  `ExclusionEvent` to `/phase2/exclusions/u<my_id>` and add target to
  local excluded-set

Tests:
- Unit: 3 voters all with R=0.8 vote target=5 with r_value=0.1 → emit
  exclusion
- Unit: 2 voters (M-1) — no exclusion
- Unit: 3 voters but one has R=0.5 (< T_quorum) — vote ignored, no
  exclusion

### 2.5 — `signed_observation_publisher_node` (~1-2 days)

Per-UAV. Two modes via param `mode={honest, byzantine}`. Every
ν_verify⁻¹ = 45 s:
- Look up tile at this UAV's current synthetic position
- Honest: extract top-50 SuperPoint descriptors from that tile
- Byzantine: extract top-50 from a *different* tile (~3 km offset)
- Build SignedObservation, mock-sign with Ed25519, publish on
  `/uav<id>/signed_observation`

### 2.6 — `phase2_scenario_runner.py` (~2 days)

Host-side (outside container) orchestrator:
1. Launch via docker exec: N UAVs (e.g. 13 honest + 2 byzantine for M=3, f=2)
2. Each UAV runs: signed_observation_publisher, verifier (for others),
   reputation_manager, quorum_exclusion
3. Wait 60 s steady-state
4. Inject "byzantine starts" marker; record timestamp
5. Subscribe to all `/phase2/exclusions/*` topics
6. Run for 600 s (well above the 215 s expected exclusion time)
7. Collect per-(target, voter) exclusion timestamps
8. Compute: median exclusion time per byzantine target, false-exclusion
   incidents on honest UAVs, M-f cell sweep results

Trials = 30 per (M, f) cell, with cells (M, f) ∈ {(3, 1), (3, 2), (5, 2), (5, 3), (7, 3), (7, 4)} for Prop 2.

### 2.7 — Analysis script (~1 day)

`scripts/phase2-analyze.py` reads all scenario-runner CSVs:
- Per (M, f) cell: median + 95th percentile + min/max exclusion time
- Across all trials: count false-exclusions on honest UAVs (Prop 1)
- Fit measured exclusion times to paper's T_ind formula (Prop 2 within
  ±15%)

### 2.8 — Results doc (~1 day)

`docs/results/phase-2.md` with the same structure as `docs/results/phase-1.md`:
- Headline pass/fail per (M, f) cell × Prop 1/2/3
- Comparison: real-PoO exclusion times vs §VII-IX abstract Monte Carlo
- Implications for paper §VII-IX (real verdicts may give faster
  exclusions because honest verifiers cluster their UNVERIFIED on
  byzantine peers more reliably than random label flips)

---

## Pass criteria

Per VALIDATION_PLAN.md Phase 2:

| Criterion | Required |
|---|---|
| Prop 1 — false exclusion of honest UAV when f ≤ M-1 | **0** across all trials |
| Prop 3 — median exclusion time for byzantine | < 215 s |
| Prop 3 — 95th percentile exclusion time | < 300 s |
| Prop 2 — measured vs predicted T_ind | within ±15% |
| AUC of verdict stream (sanity) | > 0.95 |

---

## Expected outcomes (incl. could-fail-in-good-way)

- **Likely pass**: Phase 1's near-perfect separability + asymmetric R
  update means byzantine peers should accumulate UNVERIFIED quickly.
  Predicted median ≈ 170 s (paper); measured ≤ 215 s passes.
- **Could-fail-in-good-way**: measured exclusion time faster than
  paper's 215 s prediction (because real PoO is more decisive than
  abstract label flips that §VII-IX used). Update paper with measured
  median as a sharper bound.
- **Could-fail**: Prop 1 violated — honest UAV excluded. Would require
  immediate root-cause: likely either (a) honest verifier sometimes
  votes UNVERIFIED on another honest peer (Phase 1 measured this rate
  at 4.6%), and (b) bad-luck cluster of 3 such votes from M=3
  high-R verifiers → false exclusion. Mitigation: increase M, raise
  T_quorum, or use even lower T_verify per Phase 1's operating-envelope
  recommendation.

---

## Out of scope for Phase 2

- Real Ed25519 signature verification — Phase 2 mocks signatures
  (assumes valid). Paper trusts the crypto. Real signing in Phase 6+
  when we measure crypto timing on target accelerator.
- UWB range inconsistency detector — Phase 5 territory (GNSS
  spoofing detection lives there).
- PX4 flight dynamics — UAVs in Phase 2 are stationary or follow a
  scripted path; real flight in Phase 3+.
- Multi-hop position relay — Phase 3 territory.
- 200-UAV scale stats — Tier B (Phase 6 mixed scale).

---

## Decision register

- **2026-05-23** — initial spec written after Phase 1 PASS. PoO config
  locked at K=20 / N=50 / τ=0.7 / T_verify=0.30 per Phase 1 validated
  defaults. Architecture matches paper §IV-B + §IV-C + §IV-F end
  exactly. Verifier node reuses the validated Phase 1 pipeline
  verbatim — only wrapping it in ROS2 callbacks.
