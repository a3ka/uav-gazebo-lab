#!/usr/bin/env python3
"""Phase 2 scenario runner -- orchestrate N UAVs + record exclusion events.

For each UAV i (honest or byzantine):
  - signed_observation_publisher_node (mode honest|byzantine)
  - verifier_node (verifies OTHERS' OBS, applies T_verify=0.30)
  - reputation_manager_node (asymmetric R update + decay)
  - quorum_exclusion_node (declares ExclusionEvent on M-quorum)

The 4N subprocesses share /signed_observation (broadcast) +
/reputation/update (broadcast) + /reputation/view (broadcast) +
/distilled_state (broadcast). Each verifier ignores its own OBS.

This script subscribes to /phase2/exclusions/u<i> for ALL i and
records the (observer_uav, target_uav, t_exclusion) tuples to a CSV.
On scenario end, writes the CSV and prints per-(M, f) summary.

Usage (inside container after `source install/setup.bash`):
    python3 scripts/phase2-scenario-runner.py \
        --n-honest 7 --n-byzantine 1 --m-quorum 3 \
        --duration-s 300 --output workspaces/phase2-run.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import ExclusionEvent, ReputationUpdate


PROCESSES: list[subprocess.Popen] = []


def spawn(cmd: list[str], log_path: Path) -> subprocess.Popen:
    log = log_path.open('w')
    p = subprocess.Popen(
        cmd, stdout=log, stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,  # own process group so we can kill the tree
    )
    PROCESSES.append(p)
    return p


def cleanup() -> None:
    for p in PROCESSES:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


class Phase2Recorder(Node):
    def __init__(self, uav_ids: list[int], t_start: float):
        super().__init__('phase2_recorder')
        self.t_start = t_start
        self.exclusion_events: list[dict] = []
        self.reputation_events: list[dict] = []

        for uid in uav_ids:
            # Per-observer exclusion subscription
            self.create_subscription(
                ExclusionEvent,
                f'/phase2/exclusions/u{uid}',
                lambda msg, observer=uid: self._on_excl(observer, msg),
                10,
            )
        # Also record every ReputationUpdate seen on broadcast channel
        self.create_subscription(
            ReputationUpdate, '/reputation/update', self._on_rep, 50
        )

    def _on_excl(self, observer: int, msg: ExclusionEvent) -> None:
        t = time.monotonic() - self.t_start
        self.exclusion_events.append({
            'observer': observer,
            'target': int(msg.target_id),
            't_exclusion_s': t,
            'n_voters': len(msg.voter_ids),
            'min_voter_r': float(msg.voter_min_r),
        })
        self.get_logger().warning(
            f'[t={t:.1f}s] EXCL observer={observer} target={msg.target_id} '
            f'voters={len(msg.voter_ids)} min_R={msg.voter_min_r:.3f}'
        )

    def _on_rep(self, msg: ReputationUpdate) -> None:
        t = time.monotonic() - self.t_start
        self.reputation_events.append({
            't_s': t,
            'reporter': int(msg.reporter_id),
            'target': int(msg.target_id),
            'reason': int(msg.reason),
        })


def launch_uav(uid: int, mode: str, m_quorum: int, dataset_dir: str) -> None:
    """Launch the 4-node stack for one UAV."""
    pos = [float(uid) * 1.0, 0.0, 50.0]  # x = uid * 1 m so verifier/publisher tile lookup varies
    log_dir = Path('/tmp/phase2-logs')
    log_dir.mkdir(exist_ok=True)

    common_pos_str = f'[{pos[0]}, {pos[1]}, {pos[2]}]'

    # 1. publisher
    spawn(
        ['ros2', 'run', 'uav_swarm_nodes', 'signed_observation_publisher_node',
         '--ros-args',
         '-p', f'uav_id:={uid}',
         '-p', f'mode:={mode}',
         '-p', 'publish_period_s:=10.0',  # faster than paper 45s for shorter scenario
         '-p', f'initial_position:={common_pos_str}',
         '-p', f'dataset_dir:={dataset_dir}'],
        log_dir / f'u{uid}-publisher.log',
    )
    # 2. verifier
    spawn(
        ['ros2', 'run', 'uav_swarm_nodes', 'verifier_node',
         '--ros-args',
         '-p', f'verifier_id:={uid}',
         '-p', f'initial_position:={common_pos_str}',
         '-p', f'dataset_dir:={dataset_dir}'],
        log_dir / f'u{uid}-verifier.log',
    )
    # 3. reputation manager
    spawn(
        ['ros2', 'run', 'uav_swarm_nodes', 'reputation_manager_node',
         '--ros-args',
         '-p', f'uav_id:={uid}',
         '-p', f'initial_position:={common_pos_str}'],
        log_dir / f'u{uid}-repmgr.log',
    )
    # 4. quorum exclusion
    spawn(
        ['ros2', 'run', 'uav_swarm_nodes', 'quorum_exclusion_node',
         '--ros-args',
         '-p', f'uav_id:={uid}',
         '-p', f'm_quorum:={m_quorum}'],
        log_dir / f'u{uid}-quorum.log',
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--n-honest', type=int, default=7)
    ap.add_argument('--n-byzantine', type=int, default=1)
    ap.add_argument('--m-quorum', type=int, default=3)
    ap.add_argument('--duration-s', type=float, default=300.0)
    ap.add_argument('--dataset-dir', default='/datasets/zurich-z16')
    ap.add_argument('--output', default='/run-data/phase2-run.csv')
    args = ap.parse_args()

    n_total = args.n_honest + args.n_byzantine
    uav_ids = list(range(n_total))
    # First N_honest are honest, last N_byzantine are byzantine
    modes = ['honest'] * args.n_honest + ['byzantine'] * args.n_byzantine

    print(f'=== Phase 2 scenario runner ===')
    print(f'  N_total = {n_total} (honest = {args.n_honest}, byzantine = {args.n_byzantine})')
    print(f'  M_quorum = {args.m_quorum}, duration = {args.duration_s} s')
    print(f'  dataset = {args.dataset_dir}')

    print('[1/4] Spawning 4N processes...')
    for uid, mode in zip(uav_ids, modes):
        launch_uav(uid, mode, args.m_quorum, args.dataset_dir)
    print(f'  {len(PROCESSES)} processes spawned')
    time.sleep(15)  # let nodes start + SuperPoint load
    alive = sum(1 for p in PROCESSES if p.poll() is None)
    print(f'  {alive}/{len(PROCESSES)} alive after 15 s')
    if alive < len(PROCESSES):
        print(f'  WARNING: {len(PROCESSES) - alive} processes died early')

    print('[2/4] Starting recorder + steady-state wait (60 s)...')
    rclpy.init()
    t_start = time.monotonic()
    rec = Phase2Recorder(uav_ids, t_start)
    end = t_start + 60.0
    while time.monotonic() < end:
        rclpy.spin_once(rec, timeout_sec=0.5)

    print(f'[3/4] Steady-state reached. Measurement window: {args.duration_s - 60.0:.1f} s...')
    end = t_start + args.duration_s
    last_print = time.monotonic()
    while time.monotonic() < end:
        rclpy.spin_once(rec, timeout_sec=1.0)
        if time.monotonic() - last_print > 30.0:
            elapsed = time.monotonic() - t_start
            print(f'  ... t={elapsed:.0f}s  exclusions={len(rec.exclusion_events)}  '
                  f'rep_events={len(rec.reputation_events)}')
            last_print = time.monotonic()

    print('[4/4] Writing CSV + summary...')
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Exclusion CSV
    excl_csv = out_path.with_suffix('.exclusions.csv')
    with excl_csv.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['observer', 'target', 't_exclusion_s', 'n_voters', 'min_voter_r'])
        w.writeheader()
        for r in rec.exclusion_events:
            w.writerow(r)
    print(f'  exclusions -> {excl_csv}')

    # Reputation events CSV
    rep_csv = out_path.with_suffix('.rep_events.csv')
    with rep_csv.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['t_s', 'reporter', 'target', 'reason'])
        w.writeheader()
        for r in rec.reputation_events:
            w.writerow(r)
    print(f'  rep events -> {rep_csv}')

    # Summary
    print('')
    print('=== Summary ===')
    print(f'  Total exclusion events: {len(rec.exclusion_events)}')
    if rec.exclusion_events:
        per_target: dict[int, list[float]] = {}
        for e in rec.exclusion_events:
            per_target.setdefault(e['target'], []).append(e['t_exclusion_s'])
        byz_ids = uav_ids[args.n_honest:]
        honest_ids = uav_ids[:args.n_honest]
        false_excl_count = sum(1 for tid in honest_ids if tid in per_target)
        print(f'  False exclusions of honest UAVs (Prop 1): {false_excl_count}  '
              f'{"PASS" if false_excl_count == 0 else "FAIL"}')
        excl_times_byz: list[float] = []
        for bid in byz_ids:
            times = per_target.get(bid, [])
            if times:
                t_excl = min(times)  # first observer to declare
                excl_times_byz.append(t_excl)
                print(f'  byzantine target={bid} first-excluded at t={t_excl:.1f}s '
                      f'(by {len(times)} observers)')
            else:
                print(f'  byzantine target={bid} NOT EXCLUDED -- FAIL (Prop 3)')
        if excl_times_byz:
            med = sorted(excl_times_byz)[len(excl_times_byz) // 2]
            print(f'  Median first-exclusion time (Prop 3): {med:.1f}s  '
                  f'{"PASS" if med < 215.0 else "FAIL (>215 s)"}')

    cleanup()
    rclpy.shutdown()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    finally:
        cleanup()
