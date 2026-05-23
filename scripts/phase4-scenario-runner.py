#!/usr/bin/env python3
"""Phase 4 task 4.4 — failover scenario runner.

One trial = (scenario, N anchors, M followers, comm condition, trial id).

Spawns ROS2 nodes via subprocess (so SIGKILL works for S1), waits for
steady state, triggers the chosen failure mode, listens on
/phase4/timing/f* for each follower's switching_time, and writes a
metrics JSON.

Scenarios (paper IV-F):
  S1  sudden death       SIGKILL on victim anchor's process group
  S2  slow degradation   ros2 param set publish_rate (10 -> 1 -> 0)
                         over ~3 s
  S3  link failure       ros2 param set publish_rate -> 0  (anchor
                         process keeps running but DistilledState
                         stream silenced -- proxy for outbound packet
                         drop without needing CAP_NET_ADMIN)
  S5  reputation drop    ros2 param set reputation -> 0.1
                         (S4 partial partition requires per-follower
                          DDS filtering -- deferred to integration phase)

Outputs metrics JSON with one entry per follower:
  switching_time_s    (None if no /phase4/timing/fX arrived in time)
  detection_ok        bool (switching_time < t_timeout + t_pass_budget)
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCENARIOS = ('S1', 'S2', 'S3', 'S5')


class TrialProcess:
    """Tracks a single ROS2 node subprocess (setsid -> own pgid)."""
    def __init__(self, proc: subprocess.Popen, label: str) -> None:
        self.proc = proc
        self.label = label
        self.pgid = os.getpgid(proc.pid)

    def kill_group(self) -> None:
        try:
            os.killpg(self.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def terminate(self) -> None:
        try:
            os.killpg(self.pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _spawn(args: list[str], label: str, log_path: Path) -> TrialProcess:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open('w')
    proc = subprocess.Popen(
        args, stdout=log_file, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return TrialProcess(proc, label)


def _spawn_anchor(anchor_id: int, pos: tuple[float, float, float],
                  log_dir: Path) -> TrialProcess:
    # __node:=anchorN remaps the runtime node name; without this all
    # anchors register as /anchor_node and ros2 param set can't target
    # one of them (collides / picks random).
    return _spawn(
        ['ros2', 'run', 'uav_swarm_nodes', 'anchor_node',
         '--ros-args',
         '-r', f'__node:=anchor{anchor_id}',
         '-p', f'anchor_id:={anchor_id}',
         '-p', f'initial_position:=[{pos[0]}, {pos[1]}, {pos[2]}]',
         '-p', 'target_capacity:=10',
         '-p', 'reputation:=0.8',
         '-p', 'publish_rate:=10.0'],
        label=f'anchor{anchor_id}',
        log_path=log_dir / f'anchor{anchor_id}.log',
    )


def _spawn_follower(follower_id: int, initial_anchor: int,
                    known_anchors: list[int], t_timeout_s: float,
                    log_dir: Path) -> TrialProcess:
    known_str = '[' + ', '.join(str(a) for a in known_anchors) + ']'
    return _spawn(
        ['ros2', 'run', 'uav_swarm_nodes', 'follower_node',
         '--ros-args',
         '-r', f'__node:=follower{follower_id}',
         '-p', f'follower_id:={follower_id}',
         '-p', f'initial_anchor_id:={initial_anchor}',
         '-p', f'known_anchor_ids:={known_str}',
         '-p', f't_timeout:={t_timeout_s}',
         '-p', 't_offer_window:=1.0'],
        label=f'follower{follower_id}',
        log_path=log_dir / f'follower{follower_id}.log',
    )


def _trigger_failure(scenario: str, victim_id: int) -> None:
    """Apply scenario-specific failure to victim anchor."""
    node = f'/anchor{victim_id}'
    if scenario == 'S1':
        # Handled separately (SIGKILL on process group) -- not via param.
        return
    if scenario == 'S2':
        # Slow degradation: 10 Hz -> 1 Hz now, -> 0 Hz after 2 s.
        subprocess.run(['ros2', 'param', 'set', node, 'publish_rate', '1.0'],
                       check=False, capture_output=True)
        time.sleep(2.0)
        subprocess.run(['ros2', 'param', 'set', node, 'publish_rate', '0.0'],
                       check=False, capture_output=True)
    elif scenario == 'S3':
        # Link failure proxy: silence outbound by zeroing publish rate
        subprocess.run(['ros2', 'param', 'set', node, 'publish_rate', '0.0'],
                       check=False, capture_output=True)
    elif scenario == 'S5':
        # Reputation drop below T_reject = 0.2
        subprocess.run(['ros2', 'param', 'set', node, 'reputation', '0.1'],
                       check=False, capture_output=True)


def _start_collectors(
    follower_ids: list[int], t_budget_s: float
) -> dict[int, subprocess.Popen]:
    """Spawn one `ros2 topic echo --once` per follower BEFORE the
    trigger fires. Critical for fast-trigger scenarios (S5) where the
    follower publishes /phase4/timing/fX within ~1 s of the trigger --
    subscribing AFTER the trigger introduces a race that loses the
    first published msg if subscription discovery lands after publish.
    """
    procs: dict[int, subprocess.Popen] = {}
    for fid in follower_ids:
        procs[fid] = subprocess.Popen(
            ['timeout', str(t_budget_s),
             'ros2', 'topic', 'echo', '--once',
             f'/phase4/timing/f{fid}', 'std_msgs/msg/Float64'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    # Give the subscriptions time to discover their publishers before
    # the trigger fires. ROS2 DDS discovery is typically <500 ms but
    # we add a bit of margin.
    time.sleep(0.8)
    return procs


def _finalize_collectors(
    procs: dict[int, subprocess.Popen]
) -> dict[int, float | None]:
    results: dict[int, float | None] = {}
    for fid, p in procs.items():
        out, _ = p.communicate()
        results[fid] = _parse_float64(out)
    return results


def _parse_float64(text: str) -> float | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('data:'):
            try:
                return float(line.split(':', 1)[1].strip())
            except ValueError:
                return None
    return None


def run_trial(
    *, scenario: str, n_anchors: int, n_followers: int,
    victim_anchor_id: int, t_steady_s: float, t_failure_s: float,
    t_pass_budget_s: float, t_timeout_s: float,
    log_dir: Path,
) -> dict:
    t_trial_start = time.monotonic()
    procs: list[TrialProcess] = []
    try:
        # 1. Spawn anchors (spaced 50 m apart along X)
        for aid in range(n_anchors):
            procs.append(_spawn_anchor(
                aid, (aid * 50.0, 0.0, 50.0), log_dir,
            ))
        time.sleep(4.0)  # DDS discovery + first DistilledState

        # 2. Spawn followers. Each follower attaches initially to victim
        #    anchor; alternative anchors are the rest. Distributing the
        #    initial attachment across anchors would make the trial
        #    measure ONLY the victim's followers' failover -- equivalent
        #    when victim != 0 but with extra book-keeping. Simpler:
        #    every follower attaches to victim, every follower fails over.
        known = list(range(n_anchors))
        for fid in range(n_followers):
            procs.append(_spawn_follower(
                fid, victim_anchor_id, known, t_timeout_s, log_dir,
            ))
        time.sleep(t_steady_s)

        # 3. Start collectors BEFORE triggering. The trigger-then-subscribe
        #    order races for fast scenarios (S5 publishes /phase4/timing
        #    within ~1 s; subscription discovery takes ~500 ms).
        budget = t_pass_budget_s + t_timeout_s + 5.0
        follower_ids = list(range(n_followers))
        collectors = _start_collectors(follower_ids, budget)

        # 4. Trigger failure
        t_death = time.time()
        if scenario == 'S1':
            victim = next(p for p in procs if p.label == f'anchor{victim_anchor_id}')
            victim.kill_group()
        else:
            _trigger_failure(scenario, victim_anchor_id)

        # 5. Finalize collectors -- blocks until each `ros2 topic echo`
        #    receives its msg or hits its `timeout` wrapper budget.
        timings = _finalize_collectors(collectors)
    finally:
        # 5. Tear down everything (including the victim if it survived S2-S5)
        for p in procs:
            p.terminate()
        time.sleep(0.5)
        for p in procs:
            p.kill_group()
        # extra belt-and-braces sweep
        subprocess.run(['pkill', '-u', os.environ.get('USER', 'root'),
                        '-f', 'uav_swarm_nodes'],
                       capture_output=True)

    pass_threshold = t_timeout_s + t_pass_budget_s
    per_follower = []
    for fid, t in timings.items():
        per_follower.append({
            'follower_id': fid,
            'switching_time_s': t,
            'detection_ok': (t is not None and t < pass_threshold),
        })

    valid = [r['switching_time_s'] for r in per_follower if r['switching_time_s'] is not None]
    n_pass = sum(1 for r in per_follower if r['detection_ok'])
    return {
        'scenario': scenario,
        'n_anchors': n_anchors,
        'n_followers': n_followers,
        'victim_anchor_id': victim_anchor_id,
        't_death_unix': round(t_death, 3),
        't_steady_s': t_steady_s,
        't_pass_budget_s': t_pass_budget_s,
        't_timeout_s': t_timeout_s,
        'pass_threshold_s': pass_threshold,
        'wall_time_s': round(time.monotonic() - t_trial_start, 2),
        'per_follower': per_follower,
        'n_pass': n_pass,
        'n_total': len(per_follower),
        'pass_rate': round(n_pass / max(len(per_follower), 1), 4),
        'switching_time_median_s': (
            round(sorted(valid)[len(valid) // 2], 4) if valid else None
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--scenario', required=True, choices=SCENARIOS)
    p.add_argument('--n-anchors', type=int, default=2)
    p.add_argument('--n-followers', type=int, default=1)
    p.add_argument('--victim-anchor-id', type=int, default=0)
    p.add_argument('--t-steady-s', type=float, default=4.0)
    p.add_argument('--t-failure-s', type=float, default=4.0,
                   help='alias for t-steady-s; spec used this name')
    p.add_argument('--t-pass-budget-s', type=float, default=10.0,
                   help='paper criterion <10s after watchdog timeout')
    p.add_argument('--t-timeout-s', type=float, default=5.0,
                   help='follower watchdog timeout for missing DistilledState')
    p.add_argument('--out', required=True, help='metrics JSON path')
    p.add_argument('--log-dir', required=True, help='per-node stdout/err dir')
    args = p.parse_args()

    metrics = run_trial(
        scenario=args.scenario,
        n_anchors=args.n_anchors,
        n_followers=args.n_followers,
        victim_anchor_id=args.victim_anchor_id,
        t_steady_s=args.t_steady_s,
        t_failure_s=args.t_failure_s,
        t_pass_budget_s=args.t_pass_budget_s,
        t_timeout_s=args.t_timeout_s,
        log_dir=Path(args.log_dir),
    )
    Path(args.out).write_text(json.dumps(metrics, indent=2))
    print(f'[runner] {args.scenario} n_pass={metrics["n_pass"]}/{metrics["n_total"]} '
          f'median={metrics["switching_time_median_s"]}s -> {args.out}',
          flush=True)
    return 0 if metrics['n_pass'] == metrics['n_total'] else 1


if __name__ == '__main__':
    sys.exit(main())
