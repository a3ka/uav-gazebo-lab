# Phase 4 — Failover Timing results

**Status:** ✅ COMPLETE 2026-05-23
**Hardware actual:** local CPU (headless, `uav-lab:cpu` image), JOBS=4
**Cost actual:** $0 (no vast.ai)
**Trials:** 120 (4 scenarios × 30 trials × 10 followers = 1200 follower-switches)
**Wall time:** 8 min 52 s
**Spec source:** `docs/phase-4-spec.md`

### Reproducibility

| Artefact | Pin |
|---|---|
| Docker image | `uav-lab:cpu` (local, from `docker/Dockerfile.cpu`) |
| Git commit at sweep start | will be `<HEAD>` of this commit |
| Sweep config | scenarios=[S1, S2, S3, S5], trials/scenario=30, n_anchors=3, n_followers=10, victim=anchor 0, t_steady=5s, t_pass_budget=10s, t_timeout=5s |
| Raw data | `workspaces/phase4-prod/{results.csv, manifest.json, analysis.json, switching_distributions.png}` |
| Parallelism | JOBS=4 ProcessPoolExecutor; unique ROS_DOMAIN_ID per worker PID for DDS isolation |

This document follows the structure of `docs/results/phase-{1,2,3}.md`.
Architecture sections are final; production-sweep tables get filled in
after the campaign run completes.

---

## Architecture validation (dev complete)

The Phase 4 stack (per-UAV: anchor_node + follower_node, failover
messages ReassignRequest/ReassignOffer/AttachAck) plus the
scenario-driving orchestrator have been validated end-to-end on CPU
through the following smokes (all PASS):

| Smoke | Driver | Verdict |
|---|---|---|
| S1 sudden death (SIGKILL anchor) | `smoke-failover-S1.sh` + `phase4-scenario-runner.py --scenario S1` | ✅ switching = 6.07-6.08 s < 10 s |
| S2 slow degradation (publish_rate 10→1→0 over 2 s) | `phase4-scenario-runner.py --scenario S2` | ✅ switching = 6.09 s < 10 s |
| S3 link failure (publish_rate→0, anchor still alive) | `phase4-scenario-runner.py --scenario S3` | ✅ switching = 6.02 s < 10 s |
| S5 reputation drop (R→0.1 < T_reject=0.2) | `phase4-scenario-runner.py --scenario S5` | ✅ switching = **1.00 s** (immediate trigger, no watchdog wait) |

**S4 (partial partition) DEFERRED.** S4 requires per-follower DDS UDP
filtering (iptables / tc / netem rules), which needs `CAP_NET_ADMIN` on
the container. Running this inside a default `docker run` requires
`--cap-add=NET_ADMIN` and host-side coordination. Deferred to Phase 7
(integration) where the full multi-container setup already exists.
The remaining 4 scenarios cover the bulk of the failover state-machine
paths (silence-triggered detection AND reputation-triggered detection
AND graceful degradation AND sudden death).

**Packet-loss comm condition (5 %) DEFERRED** for the same reason
(needs `tc qdisc add ... netem loss 5%` which is `CAP_NET_ADMIN`).
Nominal (no loss) is the only comm condition in this campaign.

---

## Implementation deviations from spec (decision register)

| Change | Reason |
|---|---|
| Anchor / follower node names remapped via `__node:=anchorN` (ROS2 remapping) at launch time | Original anchor_node.py hard-codes `super().__init__('anchor_node')`. With N anchors all registering as `/anchor_node`, `ros2 param set /anchor0 ...` cannot target a specific one — S2/S3/S5 triggers broke. Remapping is the no-code-change fix. |
| follower_node now checks `msg.reputation < T_reject` in `_on_distilled` and fires failover immediately | The original watchdog only triggered on silence. Without this check, scenario S5 would never fire because the anchor keeps publishing valid DistilledState (with low R) and watchdog never times out. Paper IV-C says "anchor with R<T_reject triggers immediate failover" — code now matches. |
| anchor_node's `_param_cb` now destroys old timer unconditionally before checking rate | Original `if rate > 0` guard left the old timer running when `rate=0` was set, so scenarios S2 (slow degradation) and S3 (link failure) silently kept publishing at 10 Hz and the silence watchdog never fired. |
| S3 implementation = `publish_rate→0` (not iptables) | Avoids CAP_NET_ADMIN. Semantically equivalent for the follower (which only sees that the anchor's DistilledState went silent); for paper claims about packet-loss-tolerance specifically, Phase 7 integration test is the authoritative case. |

---

## Production sweep — RUNNING

Launched via `JOBS=4 bash scripts/phase4-campaign.sh` (see
`scripts/phase4-campaign.sh` for the env-var contract).

Per-cell config:
- N_anchors = 3 (3-anchor topology, smallest paper-faithful M from Phase 2)
- N_followers = 10 (paper Pillar 4 scale)
- victim_anchor_id = 0 (every trial kills anchor 0; followers all initially attached to anchor 0; failover paths exercised maximally)
- t_steady = 5 s (DDS discovery + initial DistilledState flow)
- t_pass_budget = 10 s (paper criterion)
- t_timeout = 5 s (follower watchdog silence threshold)
- pass_threshold = t_timeout + t_pass_budget = **15 s**

### Results matrix

| Scenario | n_total | pass rate | median (s) | p95 (s) | p99 (s) | mean (s) | std (s) | Pass criterion (p99 < 15 s) |
|---|---|---|---|---|---|---|---|---|
| S1 sudden death | 300 | **100.0 %** | 6.079 | 6.165 | 6.193 | 6.078 | 0.05 | ✅ **PASS** (8.8 s under) |
| S2 slow degradation | 300 | **100.0 %** | 6.069 | 6.175 | 6.236 | 6.075 | 0.06 | ✅ **PASS** (8.8 s under) |
| S3 link failure | 300 | **100.0 %** | 6.065 | 6.167 | 6.225 | 6.074 | 0.05 | ✅ **PASS** (8.8 s under) |
| S5 reputation drop | 300 | **100.0 %** | 1.030 | 1.413 | 1.936 | 1.104 | 0.10 | ✅ **PASS** (13.1 s under) |

`n_total = trials_per_scenario (30) × n_followers (10) = 300`

**Headline:** all 1200 follower-switch measurements pass the paper
criterion `< 10 s of failover budget after watchdog timeout` (here
re-stated as p99 < t_timeout + t_pass_budget = 15 s). The silence-
triggered scenarios (S1/S2/S3) cluster tightly at ~6.1 s = 5 s watchdog
+ ~1.0 s F2-F5 protocol completion (REASSIGN_REQUEST → OFFER → ATTACH
→ ATTACH_ACK). S5 (reputation trigger) skips the 5 s watchdog
entirely → 5-6× faster median.

### Distribution plot

`workspaces/phase4-prod/switching_distributions.png`

S1/S2/S3 histograms are extremely tight (σ ~ 0.05 s) — the protocol
timing is deterministic once the trigger fires. The 5 s watchdog
dominates; F2-F5 itself is consistently ~1.0 s. S5 has a small tail to
~2 s coming from random offer-collection variation (1 s window + DDS
delivery jitter for `ros2 param set` reaching the anchor and
propagating the next DistilledState to the follower).

### Runner race-condition fix (decision register)

A first run of the same sweep showed S5 pass-rate at 88.7 % despite
100 % of measured timings being < 1.2 s. Root cause: the runner
subscribed to `/phase4/timing/fX` AFTER triggering the failure. For
fast scenarios (S5 takes ~1 s end-to-end) some `ros2 topic echo --once`
subprocesses missed the message because DDS subscription discovery
took longer than the follower's protocol completion. **Fix:** spawn
all collector subprocesses before triggering, sleep 0.8 s for DDS
discovery, then trigger. After the fix: 300/300 PASS on S5 (the
33 missed-message cases were runner artefacts, not protocol failures).
S1/S2/S3 were unaffected by the original race (5 s watchdog timeout
gave the collectors plenty of time to discover).

---

## Honest scope limits

1. **All UAVs static, no flight dynamics.** Phase 6+ adds Gazebo motion.
2. **No comm-failure model (5 % loss).** Pending Phase 7 integration.
3. **S4 (partial partition) not measured.** See above.
4. **Failure trigger is exogenous.** Real-world failures cluster around mission stress events (battery low, GPS jam). Phase 6+ adds stress-driven failure.
5. **DDS as the only transport.** Production deployments may use mavlink / multicast custom protocols.
