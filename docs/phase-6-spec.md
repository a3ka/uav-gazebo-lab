# Phase 6 — Progressive Attrition + Load Balancing (spec)

**Validates:** Paper Pillar 6 (load balancing under attrition) + Pillar 2
(dynamic role rotation). Subsumes part of Pillar 4 at scale.
**Hardware:** mixed two-tier — Tier B (Python MC) local CPU; Tier A
(Gazebo) local CPU first, vast.ai GPU only if rendering scale exceeds
host. Phase 3-5 TRN-mock convention kept (no real vision in the loop)
so no GPU rental needed for measurement campaign.
**Estimated cost:** $0 local; $5-20 if Tier A needs rental.
**Wall-time estimate:** ~3-5 days dev + 2 days measurement campaign.

Phase 6 is the FIRST phase that uses real Gazebo+PX4 flight dynamics.
All previous phases were headless ROS2 nodes; Phase 6 keeps that
infrastructure but layers it on top of Gazebo Harmonic with PX4 SITL
providing physics-grounded UAV motion.

---

## Paper anchor

| Pillar | Claim |
|---|---|
| **Pillar 6** | Mission survives 22.5 % progressive attrition with load auto-rebalanced across surviving anchors. Each surviving anchor's `target_capacity` updated as UAVs are lost. |
| **Pillar 2** | Followers reassigned to lower-load anchors dynamically; no anchor exceeds `target_capacity` for > 5 s post-event. |

Pass criteria (per trial):
1. **Mission completion** = all surviving followers retain an anchor
   for the full mission duration (no "orphaned" follower for >10 s).
2. **Capacity invariant** = no anchor exceeds its `target_capacity`
   for > 5 s after each attrition event.
3. **Re-balance latency** = median time to "rebalanced state" after
   each event < 10 s.

---

## Two-tier scaling (paper IV-B convention)

| Tier | What it measures | Scale | Stack |
|---|---|---|---|
| **A** | Mechanism validation under realistic flight | 15-20 UAV | Gazebo Harmonic + PX4 SITL + uXRCE-DDS + ROS2 stack from Phases 0-5 |
| **B** | Statistical envelope at paper-claimed scale | 200 UAV | Python/GTSAM Monte Carlo (no Gazebo) — reuses Phase 3 `position_broadcaster` + `factor_graph_node` |

Tier A produces "yes the protocol works under flight dynamics" with a
small sample. Tier B produces "this is the success-rate envelope at
N=200 over 100s of trials" without the per-UAV Gazebo cost. Together
they validate the paper claim with both fidelity AND scale, neither
of which is achievable single-tier.

---

## Implementation task tree

### 6.1 — `attrition_orchestrator_node`

A new ROS2 node (per-UAV not needed — one central) that drives the
attrition timeline:
- Reads a YAML attrition profile (list of `{t_s, victim_uav_id}` or
  `{t_s, victim_role}`).
- At each `t_s`, sends SIGKILL to victim's PX4 / anchor_node process
  via process-group lookup (mirrors Phase 4 S1 scenario).
- Publishes `/attrition/event` (new `AttritionEvent.msg`) so other
  monitor nodes can timestamp the event.

### 6.2 — Capacity-aware re-balance in `anchor_node`

Patch existing `anchor_node.py`:
- New runtime param `target_capacity` (already exists) becomes
  load-balancing input.
- Anchor publishes its CURRENT load (n_attached) in DistilledState as
  the existing `position_covariance` field is fine, but we add a new
  field or just include in ReassignOffer (already there).
- On REASSIGN_REQUEST: anchor offer = capacity_free as before. The
  follower's selection function (already in `follower_node`) prefers
  low-load (α_cap weight). Phase 4 already implements this — Phase 6
  validates at scale + with attrition events that change the load
  landscape.

NO new logic needed in `follower_node` (Phase 4's selection already
uses α_cap). Phase 6 just measures whether the existing protocol
self-balances under attrition.

### 6.3 — `load_monitor_node`

Per-trial monitor that subscribes to all anchors' DistilledState +
follower attachment events; emits CSV row per timestep:
- `t_s, anchor_id, n_attached, target_capacity, over_capacity_flag`

Used by analyzer to compute "time over capacity" per event.

### 6.4 — Tier A Gazebo scenario runner (`phase6-gazebo-runner.py`)

Inside `uav-lab:cpu` container:
1. Launch N PX4 SITL instances in headless Gazebo Harmonic (one world,
   N x500 vehicles spawned with `PX4_GZ_STANDALONE=1` + `-i <id>`).
2. Bridge their `/fmu/out/vehicle_local_position` → `/uav<id>/noisy_pose`
   so existing Phase 5 nodes (UWB sim, detector, factor graph) just
   work without modification.
3. Spawn `anchor_node` for M anchors + `follower_node` for N-M
   followers (same as Phase 4) — they DON'T need to know they're
   running over real Gazebo.
4. Spawn `attrition_orchestrator_node` with the YAML profile.
5. Spawn `load_monitor_node`.
6. Run for `t_mission_s` (default 120 s) covering all attrition events
   + recovery time.
7. Write `metrics.json` + `load_timeline.csv` per trial.

### 6.5 — Tier B Python MC scenario runner (`phase6-mc-runner.py`)

Same logic as Tier A but uses Phase 3-style `position_broadcaster_node`
instead of PX4 — so 200 UAVs fit in one process. No Gazebo. Faster:
~30 s per trial vs ~5 min Tier A. Used for statistical sweeps.

### 6.6 — Batch sweep / analyzer / campaign

Mirrors Phase 4 / Phase 5 conventions:
- `phase6-batch-sweep.py` — iterates trials, aggregates CSV
- `phase6-analyze.py` — per-event re-balance latency, time-over-capacity,
  mission-survival rate
- `phase6-campaign.sh` — env-var-driven wrapper

### 6.7 — `docs/results/phase-6.md`

Two production sweeps:
- **Tier A:** 5 trials × N=15 UAV (4 anchors, 11 followers), 22.5%
  attrition profile (3 anchors die, staggered 30 s apart)
- **Tier B:** 100 trials × N=200 UAV (M=10 anchors, 190 followers), same
  attrition rate

---

## Attrition profile (paper-faithful default)

22.5 % attrition over a 120-s mission. With N=15: ~3 UAVs killed,
staggered every 30 s.

| Event | Time (s) | Victim | Type |
|---|---|---|---|
| E1 | 30 | anchor 0 | SIGKILL |
| E2 | 60 | anchor 1 | SIGKILL |
| E3 | 90 | follower (random honest one) | SIGKILL |

Tier B scales this proportionally: N=200, kill ~45 UAVs (~30 anchors
of M=40, staggered).

---

## Honest scope limits (anticipated)

1. **Attrition triggered by orchestrator, not stress-induced.** Real
   missions lose UAVs from battery, GPS jam, etc. Phase 6 fires
   pre-scheduled SIGKILLs — adequate proxy but documented.
2. **No motion-controller in loop.** PX4 SITL flies a trivial hover
   waypoint; we don't push complex trajectories. Load-balancing is
   independent of trajectory, so this is OK.
3. **Tier B uses no flight dynamics** — UAVs static, IMU mocked
   (Phase 3 convention). Captures load-balancing logic at scale but
   not trajectory-coupled effects.
4. **Failover protocol from Phase 4 reused** — Phase 6 validates that
   the existing protocol scales, not a new failover algorithm.

---

## Expected outcome / what to do if it fails

| Outcome | Action |
|---|---|
| All trials PASS (mission complete + capacity invariant held) | Pillar 6 + Pillar 2 VALIDATED |
| Capacity invariant violated for > 5 s | Tune α_cap weight in follower selection; re-run |
| Mission fails (orphan follower > 10 s) | Investigate failover protocol throughput under multi-anchor death; possible Phase 4 limitation surfaces |
| Tier B and Tier A disagree | Investigate which one is wrong (likely Tier B's static-UAV assumption); document |

This phase is the largest implementation effort yet — multi-vehicle
Gazebo orchestration is genuinely new infrastructure. The Python MC
fallback (Tier B) makes the schedule resilient: if Tier A hits Gazebo
scaling walls, Tier B still produces the paper-relevant statistics.
