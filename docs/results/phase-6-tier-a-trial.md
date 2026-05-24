# Phase 6 Tier A — Single-trial Gazebo validation

**Status:** ✅ MINIMUM-VIABLE COMPLETE 2026-05-24 (single trial)
**Hardware actual:** local CPU + headless Gazebo Harmonic + PX4 SITL
**Cost actual:** $0
**Trials:** 1 (demonstration)

This is the "does it work under real flight dynamics" trial promised in
`docs/results/phase-6.md`. It IS NOT a statistical campaign — paper-
faithful Tier A measurement (N=15-20, 22.5% attrition, 30 trials) is
still ~1 week of follow-up work — but it validates that the entire
Phase 4 protocol stack runs unchanged on top of Gazebo + PX4 SITL with
the new `px4_position_bridge_node` translating PX4 pose msgs to the
Phase 4 NoisyPose convention.

### Setup

- N = 5 PX4 SITL instances in ONE headless Gazebo Harmonic world
- 10 m spacing along X axis
- Phase 0 stack: MicroXRCEAgent + gz sim + 5× PX4 SITL → 27 /fmu/out
  topics per vehicle (per Phase 0 smoke validation)
- `px4_position_bridge_node` × 5: each subscribes
  `/px4_<i>/fmu/out/vehicle_local_position`, publishes
  `/uav<i>/noisy_pose` + `/uav<i>/ground_truth` after NED → ENU rewrite
- 3 anchors (id 0,1,2) + 2 followers (id 3,4)
- Follower 3 initial anchor = 0; follower 4 initial anchor = 1
- t = 20 s sim: SIGKILL PX4 instance 0 (the anchor 0 host)

### Result

`switching_time = 6.10 s < 15 s pass threshold` ✅

Same ~6 s pattern as Tier B Phase 6 production sweep and the pure
Phase 4 production sweep:
  * 5 s watchdog timeout (Phase 4 t_timeout)
  * + ~1 s F2-F5 protocol completion

**Conclusion: Phase 4 failover protocol works unchanged on top of
real Gazebo flight dynamics + PX4 SITL.** The px4_position_bridge_node
is the only new infrastructure required.

---

## What's NOT done (1-week Tier A follow-up scope)

1. **N=15 multi-vehicle scaling.** N=5 fits local CPU + RAM headroom;
   N=15 requires either more host budget or vast.ai rental
   (~$5-10 for measurement campaign).
2. **22.5 % attrition profile** (multiple kills staggered). Single-
   kill demonstrated here.
3. **Statistical sweep.** Need 20-30 trials to characterize switching-
   time distribution under real flight; this is one trial.
4. **Load-balancing validation under flight.** Tier B's thundering-
   herd finding (Phase 6) needs Tier A re-validation to rule out
   trajectory-coupled effects masking the bunching.

These items are tracked in `docs/results/phase-6.md` as the Tier A
deferred follow-up.

---

## Honest scope limit

This is ONE TRIAL. Single-trial passing does not prove failover
under flight is statistically equivalent to the Tier B numbers — only
that the protocol stack RUNS without modification on PX4 SITL.
A production campaign is needed for paper-faithful Tier A claims.
