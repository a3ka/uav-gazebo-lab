# Phase 4 — Failover Timing (spec)

**Validates:** Paper Pillar 4 (sub-10 s failover after anchor loss).
**Hardware:** local CPU (headless), runs entirely inside `uav-lab:cpu`.
**Cost:** $0.
**Wall-time estimate:** ~1 wk active dev + ~1 day measurement campaign.

This phase is independent of Phase 1/2/3 (which are GPU-vision-bound)
and can run in parallel while the GPU image / vast.ai setup matures.

---

## Paper anchor (Section IV-F)

Five-phase protocol triggered by anchor loss (destruction, jamming, or
reputation < T_reject):

| Phase | Window | Action |
|---|---|---|
| F1 Detection | 0-5 s | Watchdog declares anchor unavailable after T_timeout = 5 s without DistilledState. Followers dead-reckon on IMU (< 5 m drift @ 30 m/s). |
| F2 REASSIGN_REQUEST | 5-6 s | Orphan follower broadcasts {id, last_position, velocity, battery, sensor_capabilities}. |
| F3 REASSIGN_OFFER | 6-7 s | Surviving anchors respond with {id, position, reputation, available_capacity}. |
| F4 Selection | 7-8 s | Follower computes S_reassign = α_prox/d + α_rep·R + α_cap·(1-L), defaults (α_prox, α_rep, α_cap) = (0.4, 0.35, 0.25). |
| F5 Attachment | 8-10 s | ATTACH / ATTACH_ACK exchange of position + covariance. |

Pass criterion: switching time (anchor death → ATTACH_ACK received) < 10 s.

---

## Test scenarios

Five failure modes to exercise the protocol against:

| ID | Scenario | What's killed / degraded |
|---|---|---|
| S1 | Sudden death | anchor process killed at t=T0 (SIGKILL) |
| S2 | Slow degradation | anchor DistilledState publish rate decays from 10 Hz to 0 over ~3 s before silence |
| S3 | Link failure | network drops 100% of anchor's outbound packets at t=T0 (anchor process still running, but invisible to followers) |
| S4 | Partial partition | anchor reachable by half the followers, lost to the other half |
| S5 | Reputation drop | anchor R falls below T_reject = 0.2; rejection-driven failover (no actual death) |

Each scenario run under two comm conditions:
- **Nominal**: no synthetic packet loss
- **5 % packet loss**: tc / netem applied to ROS2 DDS UDP traffic

Each (scenario × comm) cell run ≥ 30 trials to get a meaningful timing
distribution.

---

## Implementation task tree

### 4.1 — Extend uav_swarm_msgs with failover messages

Three new message types (add to `src/uav_swarm_msgs/msg/`):

- `ReassignRequest.msg`
  - timestamp (uint64), follower_id (uint64)
  - last_position (geometry_msgs/Point)
  - velocity (geometry_msgs/Vector3)
  - battery_pct (float32)
  - sensor_caps (uint32 bitfield)
- `ReassignOffer.msg`
  - timestamp (uint64), anchor_id (uint64)
  - position (geometry_msgs/Point)
  - reputation (float32)
  - capacity_free (uint32)
- `AttachAck.msg`
  - timestamp (uint64), anchor_id (uint64), follower_id (uint64)
  - confirmed_position (geometry_msgs/Point)
  - confirmed_covariance (float32[6])

Re-run colcon build. (~1 hour incl. msg drafts + rebuild + smoke.)

### 4.2 — anchor_node (Python)

Single executable handling both nominal anchor behaviour AND failover
protocol responder role.

Behaviours:
- Publish DistilledState every 100 ms (10 Hz) on `/anchor<id>/distilled_state`
- Subscribe to `/reassign/request`
  - On receipt: respond with `/reassign/offer/<my_id>` carrying anchor's
    current position, R, capacity_free (= target_followers - current_followers)
- Subscribe to `/attach/request/<my_id>`
  - On receipt: publish `/attach/ack/<my_id>` with confirmed position +
    covariance; increment follower count

Parameters: anchor_id, target_followers (default 5), initial_position
(x,y,z), initial_reputation (default 0.8), publish_rate (default 10.0).

For Phase 4 nominal anchors run a synthetic constant-position model (no
flight dynamics yet — that arrives via PX4 in Phase 6+).

### 4.3 — follower_node (Python)

Subscribes to `/anchor<anchor_id>/distilled_state`. Maintains a watchdog
timer. On timeout (no msg for T_timeout = 5 s):
1. Publish ReassignRequest on `/reassign/request`
2. Collect ReassignOffers from `/reassign/offer/<anchor_id>` for
   T_offer_window = 1 s
3. Compute S_reassign for each offer, pick max
4. Send AttachRequest to the chosen anchor
5. On AttachAck: switch subscription to new anchor's DistilledState
6. Log switching time (= t_now - t_anchor_death) to /phase4/timing

Parameters: follower_id, initial_anchor_id, T_timeout (5.0),
T_offer_window (1.0), alpha_prox (0.4), alpha_rep (0.35), alpha_cap (0.25),
target_anchor_capacity_normalisation (default 10.0).

### 4.4 — failover_scenario_runner.py (host-side orchestrator)

Outside-container Python that:
1. Launches N anchors + M followers via docker exec / ros2 launch
2. Waits for steady state (followers attached, DistilledState flowing)
3. Triggers the chosen scenario (S1-S5):
   - S1: docker kill -s SIGKILL <anchor_container>
   - S2: send SIGUSR1 → anchor lowers publish rate
   - S3: iptables / tc drop on anchor's UDP port
   - S4: drop on subset of follower-bound packets
   - S5: signal anchor to publish R = 0.1
4. Reads /phase4/timing topic (or bag file) for follower switching times
5. Writes CSV row per (scenario, comm_cond, trial, follower_id, t_switch)

Repeats trials = 30 per cell.

### 4.5 — Per-scenario smoke (script per S1-S5)

`scripts/smoke-failover-S1.sh` etc., each runs one trial of one scenario
and asserts switching time < 10 s.

### 4.6 — Multi-vehicle scale test (10 UAV per VALIDATION_PLAN.md)

`scripts/phase4-campaign.sh` runs all 5 scenarios × 2 comm conditions ×
30 trials = 300 measurements, accumulates CSV under
`workspaces/phase4-<timestamp>/results.csv`.

### 4.7 — Analysis script

`scripts/phase4-analyse.py` reads the CSV, produces per-scenario
distribution stats (median, 95th, 99th, mean) and per-cell pass/fail
verdict.

### 4.8 — Results doc

`docs/results/phase-4.md` — final timing table, scenario notes, deviations
from paper expectation, pass/fail per cell.

---

## Pass criteria (locked, per VALIDATION_PLAN.md)

Across all 5 scenarios × 2 comm conditions:
- 30-trial median switching time < 10 s
- 30-trial 95th percentile switching time < 12 s (allows graceful
  slack above the design budget)
- Zero false-positive failovers (followers must not switch when the
  current anchor is healthy)

---

## Out of scope for Phase 4

- PX4 integration of follower dead-reckoning (will be revisited in
  Phase 6 when full system runs on multi-vehicle SITL)
- Reputation-driven rejection (scenario S5 uses a forced R drop;
  reputation update mechanics live in Phase 2)
- Anchor election among multiple candidates (load balancing — Phase 6)
- Real wall-clock packet-loss measurement (use ROS2 QoS lifetime
  proxies for now; full network emulation deferred until Phase 6 mixed
  Gazebo/Python tier)

---

## Decision register

- **2026-05-21** — initial lock. Architecture matches paper §IV-F
  5-phase protocol exactly; test scenarios S1-S5 chosen to exercise
  the watchdog under realistic failure modes plus the reputation-drop
  path. Phase 4 stays headless and parallel-eligible per
  VALIDATION_PLAN.md.
