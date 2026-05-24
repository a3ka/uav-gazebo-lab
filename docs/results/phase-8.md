# Phase 8 — SwarmRaft Baseline Comparison results

**Status:** 🟡 INFRASTRUCTURE COMPLETE, comparison campaign DEFERRED
**Hardware actual:** local CPU
**Cost actual:** $0
**Spec source:** `docs/phase-8-spec.md`

This phase implemented a minimum-viable Raft-style leader-election
baseline (`raft_node`) and the comparison-trial scaffolding
(`phase8-raft-trial.sh`, `phase8-campaign.sh`), but did not produce
the production comparison-sweep numbers. The Raft node passes
INITIAL leader election cleanly; the recovery-after-leader-kill path
hits a heartbeat-queue / executor-scheduling artifact under
single-process rclpy that prevents reliable measurement.

---

## What works (validated)

| Component | Status | Smoke result |
|---|---|---|
| 3 new msgs (RaftHeartbeat, RaftVoteRequest, RaftVoteGrant) | ✅ | colcon build OK |
| `raft_node` initial election | ✅ | 5 nodes elect a leader within ~5-6 s (election_timeout + 1 s) |
| Heartbeat broadcast at 1 Hz from leader | ✅ | `ros2 topic echo /raft/heartbeat` shows `leader_id=X, term=1` continuously |
| Multi-node clustering | ✅ | 5-node cluster reaches steady state with single leader, all followers reset election timers on heartbeat |
| `phase8-raft-trial.sh` scaffolding | ✅ | spawns nodes, detects initial leader, kills leader by pkill-pattern match |
| `phase8-campaign.sh` (both protocols) | ✅ | code-path complete; comparison-sweep numbers pending |

---

## What does NOT work (deferred)

**Recovery election after leader kill is unstable** at the
single-process rclpy scale. Direct-shell tests show new leader
emerges within 5 s post-kill for SOME seed combinations
(`leader_id` transitions visible in `/raft/heartbeat`), but for
other seeds the survivors do not fire their election timer at all
in 20 s of observation -- only the startup INFO line appears in
their logs. Investigation indicates a heartbeat-message-queue or
DDS livelinness interaction: stale heartbeats from the dead leader
appear to keep resetting the survivors' election timer past the
expected silence-detection window.

Two follow-up paths to unblock production comparison:
1. **Add explicit liveliness assertion** to raft_node's heartbeat
   publisher (TOPIC_AUTOMATIC + lease_duration < election_timeout)
   so subscribers receive liveliness-lost notification when leader
   dies and can fire elections deterministically.
2. **Wrap the canonical SwarmRaft impl** (kapeldev/SwarmRaft per
   `docs/preflight/pf-1-swarmraft.md`) in ROS2 -- 3-7 day effort
   that gives the paper its actual comparative claim.

Both are tractable but out of scope for this session.

---

## Implementation deviations from spec

| Change | Reason |
|---|---|
| Raft trial uses `ros2 topic echo` with `stdbuf -oL` + temp file (instead of `--once` polling) | Polling-with-recreate exhausted DDS endpoints; need persistent subscription with unbuffered output to capture heartbeat stream across the kill event. |
| Kill via `pkill -9 -f "node_id:=N "` not `kill -KILL -- -PID` | setsid+ros2 run+python forking made the original `$!` pgid mismatch the actual python child's pgid. Pattern-match is robust. |
| seed=`i*7919 + 1` (avoid 0) | Original `seed=0` triggered the non-deterministic `Random()` branch in raft_node init; deterministic seed required for reproducible election timing across trial replicas. |

---

## Comparable claim status for paper-v10

**Cannot produce comparison-table numbers in this session.** The
paper's "we are faster than SwarmRaft" claim must either be:

1. **DEFERRED to v11** with an honest scope note: "comparative
   evaluation against canonical SwarmRaft pending (see
   `docs/preflight/pf-1-swarmraft.md` for implementation source)".
2. **DROPPED from v10** and replaced with an absolute
   characterization of our protocol's failover timing (which we
   have from Phase 4: 6 s median, 6.2 s p99).
3. **Estimated only from our partial Raft baseline**: initial-
   election timing ~5-6 s, comparable to our Phase 4. Our protocol
   wins on the failover budget because the watchdog timeout is
   the same in both (5 s) but our protocol does NOT require a
   3-phase voting cycle on top — see Phase 4 measured 1 s post-
   watchdog vs. Raft's measured ~1 s post-watchdog. Comparable
   at this scale; advantage probably grows with M (more anchors
   = more vote-collection rounds for Raft).

---

## Honest scope limits

1. **No production comparison sweep.** All numbers above are dev
   smoke; no statistical campaign run.
2. **Not real SwarmRaft.** Our baseline is generic Raft leader-
   election, not SwarmRaft's sharded multi-leader semantics.
   Reviewers may not accept the comparison.
3. **Recovery-election stability issue documented above** is
   load-bearing for any future re-attempt; the production
   campaign cannot run until that's resolved.
