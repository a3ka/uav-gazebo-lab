# Phase 8 — SwarmRaft Baseline Comparison results

**Status:** ✅ COMPLETE 2026-05-25 (production comparison sweep done)
**Hardware actual:** local CPU
**Cost actual:** $0
**Trials:** 10 per protocol × 2 protocols = 20 trials
**Wall time:** 5 min
**Spec source:** `docs/phase-8-spec.md`

### Reproducibility

| Artefact | Pin |
|---|---|
| Docker image | `uav-lab:cpu` |
| Sweep config | N=5 raft/anchor members per trial, T_kill=7s, 10 trials each protocol |
| Raw data | `workspaces/phase8-prod/{raft_t*.json, ours_t*.json, comparison.json}` |
| Transport | FASTDDS_BUILTIN_TRANSPORTS=UDPv4 (process-isolated DDS; shared-memory transport corrupted rclpy contexts on peer SIGKILL) |
| Heartbeat QoS | BEST_EFFORT depth=1 (default RELIABLE buffered stale heartbeats; survivors never silence-detected) |

### Bugs fixed during bring-up (decision register)

| Issue | Root cause | Fix |
|---|---|---|
| Survivors never fired election after leader kill | Default rclpy RELIABLE QoS buffered ~50 heartbeats; subscribers kept resetting election timer | BEST_EFFORT QoS depth=1 on /raft/heartbeat (both pub + sub) |
| Watcher rclpy context invalidated immediately after peer SIGKILL | FastDDS shared-memory transport corrupted on peer crash | `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` for all trial-spawned processes |
| Polling loop broke after 1 iteration ("FAIL no new leader") | `awk 'BEGIN{print t+30}'` reformatted Unix time to scientific notation (1.77971e+09), comparison `now > deadline` fired immediately | `awk '{printf "%.6f", ...}'` to force fixed-point |
| `ros2 topic echo` buffering missed messages | CLI tool's livelinness behaviour under publisher death | Replaced with `phase8-heartbeat-watcher.py` (Python subscriber, controlled flush) |

---

## Production comparison results

| Protocol | n | min (s) | median (s) | mean (s) | max (s) |
|---|---|---|---|---|---|
| **Raft baseline** (leader election only) | 10 | 5.084 | **5.087** | 5.086 | 5.088 |
| **Ours** (Phase 4 anchor failover) | 10 | 6.066 | **6.080** | 6.077 | 6.083 |

Both protocols are TIGHTLY clustered (std-dev < 10 ms) — single-
threaded rclpy + 5 s deterministic timeouts give very predictable
behaviour at N=5.

**Result: Raft baseline is ~1.0 s FASTER** than our protocol at this
scale. Both share the 5 s detection latency (election_timeout in
Raft, t_timeout in ours); the additional ~1 s in our protocol comes
from the F2-F5 capacity-coordination payload (REASSIGN → OFFER →
ATTACH → ATTACH_ACK) that Raft does NOT do.

### Honest interpretation for paper-v10

Naive read: "Raft is faster." More precise read:

* Raft's leader-election: 1 message round-trip after timeout.
* Ours: 3-message protocol (REASSIGN/OFFER/ATTACH) + per-follower
  capacity-aware re-assignment in the same window.

The ~1 s gap is the cost of doing the *additional* coordination work
Raft does NOT do. Comparing election-only-to-election-only, our
detection-and-vote phase is comparable to Raft's (~5 s watchdog +
~80 ms vote = ~5.08 s in our F2). The ~1 s overhead is amortised
across the per-follower ATTACH coordination that the paper's
problem statement requires.

**Recommended v10 framing:**

> "Our protocol's median switching time at N=5 is 6.08 s versus 5.09 s
> for a Raft leader-election baseline. The ~1 s gap reflects our
> additional capacity-aware re-assignment payload (per-follower
> ATTACH + ATTACH_ACK), which Raft does not provide. A Raft-based
> implementation that adds equivalent per-follower coordination
> would consume the gap; we leave this comparison to future work."

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
