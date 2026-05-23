# Phase 3 — CEP vs Hops + Relay Formula Refit (spec)

**Validates:** paper headline accuracy claim (CEP < 100 m up to k=3 under
multi-anchor fusion) AND empirically refits the relay formula
σ_k = σ_anchor × (1+δ)^k from paper §IV-D against real factor-graph
estimation.

**Hardware:** CPU for dev (~2-3 wk) + **vast.ai GPU for final
measurement campaign** (real camera-driven TRN + GTSAM iSAM2 on GPU
for batched optimisation).

**Cost:** ~$30-100 GPU rental.
**Wall-time:** ~3-4 wk total (heaviest dev task in the project).

This is the **headline-result** phase. Phase 1 + Phase 2 closed the
PoO + reputation chain; Phase 3 closes the navigation accuracy claim.

---

## Paper anchors

| Claim | Section | Number |
|---|---|---|
| Headline: CEP < 100 m up to k=3 under multi-anchor fusion | §I abstract + §IV-D | 100 m |
| Per-hop relay sigma | §IV-D eq. 9 | σ_k = σ_anchor (1+δ)^k, δ=0.15 |
| Reputation-weighted prior noise | §IV-D | σ_j = σ_base/(R_j + ε), σ_base=50, ε=0.01 |
| UWB ranging factor | §IV-D | σ_range = 0.1 m |
| Optimisation budget | §IV-D | iSAM2 < 50 ms per update |
| Anchor-vs-follower role anisotropy | §IV-D | diag(σ², σ², (σ/2)²) lat/lon/alt |

---

## Architecture

```
                  ┌────────────────────────────────────┐
                  │ Multi-anchor scenario (Gazebo Sim) │
                  │ - K anchors with TRN+GNSS          │
                  │ - M followers, k=0..5 hops away    │
                  │ - UWB ranging fabric all-to-all    │
                  └─────────────┬──────────────────────┘
                                │
                                │ ground truth + sensor streams
                                ▼
   ┌──────────────────────────────────────────────────────────┐
   │ Per-UAV pipeline (new factor_graph_node + existing P2)   │
   │                                                          │
   │ DistilledState  ────►  reputation-weighted prior factor  │
   │ (from peers)            σ_j = σ_base/(R_j+ε)             │
   │                                                          │
   │ UWB range       ────►  ranging factor                    │
   │ (pairwise)              σ_range = 0.1 m                  │
   │                                                          │
   │ IMU pre-int     ────►  motion factor (standard art)      │
   │                                                          │
   │ Camera frame    ────►  TRN factor (re-uses Phase 1 PoO)  │
   │ (anchors only)          per-anchor absolute fix          │
   │                                                          │
   │ iSAM2 fixed-lag smoother  -->  MAP estimate X_i^*        │
   └──────────────────────────────────────────────────────────┘
                                │
                                ▼
                  per-UAV position estimate -> CEP measurement
```

### New nodes (Phase 3 build list)

| Node | Phase 3 role |
|---|---|
| `factor_graph_node` | Per-UAV. Wraps GTSAM Python iSAM2 fixed-lag smoother. Subscribes DistilledState, NoisyPose (UWB ranges), IMU pre-integration topic. Builds reputation-weighted priors per paper §IV-D. Publishes estimated pose + covariance every 20 Hz. |
| `trn_anchor_node` | Anchors only. Re-uses Phase 1 PoO pipeline. Every 0.1 Hz (10 s) captures camera frame, runs SuperPoint match against staged satellite tile, emits an "absolute TRN fix" factor for the local graph (essentially a GPS-equivalent constraint). |
| `uwb_ranging_simulator_node` (existing) | Already built in Phase 0 item 7. Re-use unchanged. |
| `phase3_scenario_runner.py` | Like phase2 runner but spawns: K anchors + M followers, varies hop topology (k=0,1,2,3,5), runs 200 trials per hop tier, logs estimated pose vs ground truth → CEP. |
| `phase3-analyze.py` | Per-hop tier: CEP_50, CEP_95. Empirical refit of σ_k vs k: fit both √k (independent hops) AND (1+δ)^k (paper conservative bound), report R² + winner. |

### New message types (extend uav_swarm_msgs)

- `UwbRangeMeasurement.msg` — already Float32 in Phase 0 utility node;
  upgrade to typed message for factor graph consumption:
  ```
  uint64 timestamp
  uint64 sender_id
  uint64 receiver_id
  float32 range_m
  float32 sigma_m   # currently 0.1 per paper, but allow per-link
  ```
- `EstimatedPose.msg` — per-UAV factor-graph output:
  ```
  uint64 timestamp
  uint64 uav_id
  geometry_msgs/Point position
  float32[6] position_covariance   # 3x3 sym, lat/lon/alt
  uint32 n_hops_from_anchor        # for CEP-vs-hops grouping
  uint32 n_active_anchors          # how many anchors contributed
  ```

---

## Implementation task tree

### 3.1 — GTSAM Python smoke (~1 day)

Confirm `import gtsam; iSAM2()` works in our CPU/GPU images, build a
toy 5-pose loop closure example, measure latency.

### 3.2 — Extend uav_swarm_msgs with UwbRangeMeasurement + EstimatedPose (~1 day)

Add msgs + CMakeLists + rebuild ws + smoke `ros2 interface package`
shows 11 types total.

### 3.3 — `factor_graph_node` skeleton (~4-5 days)

Per-UAV. Mock-only first (no real GTSAM optimisation), but topology
+ ROS callbacks wired. Then plug in GTSAM iSAM2 fixed-lag smoother.

Factor types per paper §IV-D:
- `PriorFactor<Point3>` per-peer DistilledState with noise σ_j
- `BetweenFactor<Point3>` UWB range with σ=0.1 m (range-only via
  `RangeFactor<Point3>`)
- `PriorFactor<Point3>` TRN absolute fix on anchors (when trn_anchor
  emits)
- IMU pre-integration factor (standard `PreintegratedImuMeasurements`)

Reputation weighting: σ_j = σ_base / (R_peer + ε), R_peer fetched
from local reputation_manager_node's broadcast.

### 3.4 — `trn_anchor_node` (~3 days)

Anchors only. Subscribes to `/anchor<id>/camera` (mocked in Phase 3 by
re-using Zurich tile lookup at synthetic pose; real Gazebo camera in
Phase 6+). Runs Phase 1 PoO pipeline on captured frame. Emits absolute
TRN fix message that factor_graph_node consumes as a strong prior.

### 3.5 — Upgrade uwb_ranging_simulator_node to typed message (~1 day)

Replace Float32 output with UwbRangeMeasurement. Backward-compat
shim if Phase 0 smokes still need Float32.

### 3.6 — Multi-anchor scenario topology generator (~2 days)

Helper that generates UAV positions for K anchors + M followers in a
chain or grid layout, with controllable hop-depth k for each follower.
Outputs a scenario JSON consumed by phase3_scenario_runner.py.

### 3.7 — `phase3_scenario_runner.py` (~3-4 days)

Like Phase 2 runner but:
- Launches K anchors (trn_anchor_node + reputation_manager + factor_graph)
- Launches M followers (factor_graph + reputation_manager)
- UWB fabric: uwb_ranging_simulator_node for each (i, j) pair within
  500 m
- Records EstimatedPose vs ground-truth per follower
- Per-trial CSV: trial_id, follower_id, hop_depth, t_sample,
  est_x, est_y, est_z, gt_x, gt_y, gt_z, error_xy, error_z

### 3.8 — Batch runner: hop tier sweep (~1 day)

Iterates k ∈ {0, 1, 2, 3, 5} × 200 trials. Output per-tier CSV folder
ready for analyzer.

### 3.9 — `phase3-analyze.py` (~2-3 days)

CEP computation per hop tier:
- CEP_50 = median radial position error in the lat/lon plane
- CEP_95 = 95th percentile
- Per-tier pass/fail: CEP_50 < 100 m at k=3 ⇒ headline PASS

σ_k refit:
- For each hop tier k, extract per-trial empirical σ_k
- Fit two models: σ_k = α·√k vs σ_k = β·(1+δ)^k
- Report R² for each, AIC comparison, winner

### 3.10 — Results doc (~1 day)

`docs/results/phase-3.md` with CEP-vs-hops table, σ_k empirical curve,
implications for paper §IV-D (likely: relay formula is conservative
GDOP bound, not physical decay).

---

## Pass criteria (locked, per VALIDATION_PLAN.md)

| Criterion | Required |
|---|---|
| CEP_50 at k=3 under multi-anchor fusion | < 100 m |
| σ_k regression reports both √k and (1+δ)^k forms with R² + winner | (delivered) |

---

## Expected outcomes (explicit, incl. could-fail-in-good-way)

- **Likely outcome:** measured σ_k grows ~√k (independent hop noise), not
  (1+0.15)^k. Paper's formula is conservative worst-case GDOP, not
  physical decay. **This is not a failure** — it is the expected
  refit. Paper response: keep (1+0.15)^k as worst-case bound (cited
  as such), publish measured √k as v10 update.
- CEP_50 < 100 m at k=3: headline stands.
- CEP_50 ≥ 100 m at k=3: headline must be revised before any paper
  publication. STOP.

---

## Out of scope for Phase 3

- Real Gazebo camera capture for TRN — Phase 6+ when full flight
  dynamics integrated. Phase 3 uses synthetic-pose-→-tile lookup
  (same shortcut as Phase 1/2).
- 200-UAV Tier B scale stats — Phase 6 mixed-tier territory.
- PX4 SITL flight dynamics — Phase 6+.
- Spoofing-fallback factor graph reconfiguration — Phase 5 produces
  the spoofing detector; Phase 3 just trusts honest TRN.

---

## Decision register

- **2026-05-23** — initial spec written after Phase 2 PASS. Reuses
  validated PoO config (K=20, N=50, τ=0.7, T_verify=0.30) and
  reputation chain (Phase 2 nodes + msgs). New nodes:
  factor_graph_node, trn_anchor_node. New msgs:
  UwbRangeMeasurement, EstimatedPose. GTSAM 4.2 in image as
  source-built (Phase 0 item 0 + gtsam pip wheel for Python bindings).
