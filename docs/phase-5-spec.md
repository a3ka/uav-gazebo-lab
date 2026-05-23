# Phase 5 — GNSS Spoofing Reaction (spec)

**Validates:** Paper Pillar 5 (spoofing detection via UWB cross-verification).
**Hardware:** local CPU (headless), runs inside `uav-lab:cpu`.
**Cost:** $0.
**Wall-time estimate:** ~1 day active dev + ~30 min measurement campaign.

This phase is independent of Phase 1-4 and can run in parallel.

---

## Paper anchor (Pillar 5)

GNSS-spoofed UAV reports a falsified position. The swarm detects the
discrepancy by cross-checking each UAV's reported (GNSS-derived)
position against UWB-measured peer ranges:

```
For UAV i with reported position p_i and peer j with reported p_j:
  predicted_range_ij = ||p_i - p_j||
  measured_range_ij  = uwb(i, j)
  residual_ij        = |measured_range_ij - predicted_range_ij|

UAV i is "suspect" if residual_ij > T_spoof (e.g. 20 m) for >= M_suspect
peer pairs out of its visible neighbours.
```

Paper claim: spoofing detected and victim flagged in < 5 s from spoof
injection.

---

## Test scenario (paper-faithful default)

| Parameter | Value | Reason |
|---|---|---|
| `n_uavs` | 50 | paper Pillar 5 default |
| `n_spoofed` | 5 | paper "5 spoofed of 50" |
| `spoof_offset_m` | 120.0 | paper-stated offset magnitude |
| `t_inject_s` | 5.0 | injection at t=5 s (after steady state) |
| `t_observe_s` | 10.0 | observation window after injection |
| `T_spoof_m` | 20.0 | residual threshold |
| `M_suspect` | 3 | min peer pairs to declare a UAV suspect |
| `region_size_m` | 300 | uniform square, UAVs Poisson-placed |
| `sigma_gnss_m` | 1.0 | GNSS noise (clean baseline) |
| `sigma_uwb_m` | 0.1 | UWB ranging noise |
| `r_comm_m` | 100 | UWB communication range |

Pass criteria (per trial):
1. **All `n_spoofed` UAVs flagged** within `< 5 s` of injection (paper)
2. **No false positives:** no honest UAV flagged
3. **Median detection time < 5 s** across the campaign

---

## Implementation task tree

### 5.1 — SpoofAlert message + position_broadcaster `spoof_offset` param

- `src/uav_swarm_msgs/msg/SpoofAlert.msg`:
  ```
  uint64 timestamp
  uint64 suspect_uav_id
  uint32 n_suspicious_pairs
  float32 max_residual_m
  ```
- Extend `position_broadcaster_node` with `spoof_offset: float[3]`
  param (default [0,0,0]). When set, ADDED to the published noisy_pose
  position — simulates GNSS spoofing. Set at runtime via `ros2 param
  set` to inject the failure mode.

### 5.2 — spoof_detector_node (single central node, not per-UAV)

- Subscribes:
  - `/uav<i>/noisy_pose` for every i in `known_uav_ids` (GNSS source)
  - `/uwb/range` typed UwbRangeMeasurement bus (Phase 3 reuse)
- For each UwbRangeMeasurement(sender, receiver, range_m):
  - lookup latest reported_pose[sender], reported_pose[receiver]
  - predicted = ||reported_pose[sender] - reported_pose[receiver]||
  - residual = |range_m - predicted|
  - increment per-UAV counters: `suspicious[i] += 1` if residual > T_spoof
- Periodic tick (1 Hz default):
  - for each UAV i with suspicious[i] >= M_suspect → publish SpoofAlert
  - reset sliding window every `window_s` (default 2 s)
- Publishes `/spoof/alert` (SpoofAlert)

### 5.3 — phase5-scenario-runner.py (single-process, like Phase 3)

- Spawn N position_broadcasters (one per UAV, static positions in region)
- Spawn UWB simulators for each in-range pair (auto-discovered from
  Poisson topology)
- Spawn ONE spoof_detector_node
- Spawn metrics collector subscribed to `/spoof/alert`
- At t_steady, inject spoof on the chosen UAVs (`ros2 param set
  /uav_pb_<id> spoof_offset [120,0,0]`)
- Observe for t_observe_s, collect alerts
- Write metrics JSON: per-UAV t_detect (None if undetected), false
  positives list, summary

### 5.4 — phase5-batch-sweep.py

- Iterates over trials with unique random seeds (UAV positions,
  spoof choice, spoof direction)
- 30 trials per (n_uavs, n_spoofed) cell
- Aggregates CSV with rows: (trial, victim_id, t_detect_s,
  n_false_positives, n_total_alerted)

### 5.5 — phase5-analyze.py

- Per-cell median/p95/p99 t_detect, pass rate (all victims flagged in
  budget), false-positive rate
- Plot t_detect distribution
- Write analysis.json

### 5.6 — phase5-campaign.sh wrapper

### 5.7 — docs/results/phase-5.md

---

## Honest scope limits (anticipated)

1. **Static UAVs.** Phase 6+ adds Gazebo flight dynamics.
2. **Clean GNSS noise model.** Real spoofing may include subtle drift
   patterns; here it's a single-step position offset.
3. **No spoof-detection collusion attack.** Detector trusts its own
   GNSS implicitly; if detector's host is the spoof target, detection
   logic fails. Real deployment uses M-of-N distributed detector
   (Phase 7 integration).
4. **No partial spoofing.** Either UAV is at true position or at
   true + offset_vector; no time-varying drift.

---

## Expected outcome / what to do if it fails

| Outcome | Action |
|---|---|
| All 5 victims detected in <5 s, 0 false positives | Pillar 5 VALIDATED. Paper claim holds. |
| Some victims not detected | Investigate T_spoof / M_suspect tuning; may need adaptive thresholds based on UWB noise propagation |
| False positives at high density | Document that detector needs density-aware threshold; v10 caveat |
| Detection time >> 5 s | Paper claim too aggressive; provide measured envelope in v10 erratum |

This is a "could-fail-in-good-way" candidate similar to Phase 3 — the
paper just claims "<5 s reaction"; if reality differs, we measure
actual reaction-time envelope and document.
