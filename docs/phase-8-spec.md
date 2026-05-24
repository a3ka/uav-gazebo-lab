# Phase 8 — SwarmRaft Baseline Comparison (spec)

**Validates:** The paper's comparative claim vs prior-art swarm
consensus (SwarmRaft).
**Hardware:** local CPU.
**Cost:** $0.
**Wall-time estimate:** ~2 hours for minimum-viable baseline (this
session); full ROS2-wrap of canonical SwarmRaft impl = 3-7 days
(per VALIDATION_PLAN preflight PF-1, see follow-up).

---

## Minimum-viable scope (this session)

Implement a **Raft-style leader-election baseline** in Python+ROS2
and run the same failover scenario as Phase 4 (S1 sudden death) on
both protocols. Compare median switching time + mission survival
under matched conditions.

The minimum-viable baseline is **not full SwarmRaft** — it's a thin
Raft leader-election whose timing characteristics serve as a
reasonable lower-bound on what any Raft-derived swarm protocol can
do. Faster wins go to our protocol; slower wins on baseline mean we
need full SwarmRaft to overturn the comparison.

---

## Implementation task tree

### 8.1 — `raft_node` (Raft-style baseline node)

Single-role node implementing minimal Raft semantics:
  * **States:** Follower, Candidate, Leader (one of N)
  * **Election timeout:** 5 s (paper Pillar 4 t_timeout match)
  * **Heartbeat:** Leader sends `/raft/heartbeat` every 1 s
  * **Vote request:** Candidate publishes `/raft/vote/req` after
    timeout; gets votes via `/raft/vote/grant/<id>`
  * **Majority quorum:** N/2 + 1 to win election

No log replication (out of scope for failover-time comparison).

### 8.2 — `phase8-scenario-runner.py`

Runs ONE comparison trial:
  * Spawns N raft_nodes
  * Kills the current leader at t_kill_s
  * Measures: time-to-new-leader (next heartbeat after kill)
  * Writes metrics JSON

### 8.3 — Comparison sweep + analyzer

Spawns the same trial with BOTH protocols (ours = Phase 4
anchor_node+follower_node, baseline = raft_node) and outputs side-
by-side comparison table.

### 8.4 — `docs/results/phase-8.md`

Compares:
  * Median switching time (Phase 4 paper-criterion metric)
  * p99 switching time
  * Mission survival rate
  * Wall-time cost per trial

---

## Honest scope limits

1. **Not real SwarmRaft.** Real SwarmRaft adds sharded log + cross-
   shard coordination — our baseline measures leader-election only.
   Reviewers may demand canonical-SwarmRaft validation; that's the
   3-7 day follow-up.
2. **N=10 only.** Real SwarmRaft scaling studies typically N=20-100;
   our baseline doesn't measure scaling.
3. **No comm-failure model.** Both protocols run on clean DDS.

---

## Expected outcome / what to do if it fails

| Outcome | Action |
|---|---|
| Our protocol faster than Raft baseline | Comparative claim KEPT. v10 includes the comparison table. |
| Roughly equal | Comparative claim WEAKENED. v10 caveats that the advantage is marginal at this scale. |
| Our protocol SLOWER | Investigate Phase 4 timing dominators (5s watchdog dominates ours); paper may need to drop the comparative claim. |
