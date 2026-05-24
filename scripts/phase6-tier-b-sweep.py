#!/usr/bin/env python3
"""Phase 6 task 6.6 — Tier B batch sweep.

Runs phase6-tier-b-runner.py once per trial (subprocess), then runs
phase6-analyze.py on the timeline CSV, aggregating per-event metrics
into a single sweep CSV + manifest + summary analysis.json.

Default scale: N=200 UAVs (M=10 anchors, 190 followers), 3 attrition
events staggered every 30 s. Paper Pillar 6 default.

CLI:
  scripts/phase6-tier-b-sweep.py \\
      --trials 20 --n-uavs 200 --m-anchors 10 \\
      --run-id phase6-tier-b-prod
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / 'scripts' / 'phase6-tier-b-runner.py'
ANALYZER = ROOT / 'scripts' / 'phase6-analyze.py'


def _profile_for(m_anchors: int, victims: int, t_step_s: float,
                 t_first_s: float = 30.0) -> str:
    """Kill victims = min(victims, m_anchors-1) anchors staggered."""
    n = min(victims, m_anchors - 1)
    parts = []
    for i in range(n):
        parts.append(f'{t_first_s + i * t_step_s},{i},anchor')
    return ';'.join(parts)


def run_one_trial(args_tuple) -> dict:
    (trial, seed, n_uavs, m_anchors, region_m, r_comm_m,
     profile_str, t_mission_s, t_warmup_s, n_followers_init,
     trials_dir, alpha_cap, t_timeout_s) = args_tuple
    out_json = trials_dir / f'trial_{trial:04d}.metrics.json'
    csv_path = trials_dir / f'trial_{trial:04d}.timeline.csv'
    analysis_path = trials_dir / f'trial_{trial:04d}.analysis.json'
    env = os.environ.copy()
    env['ROS_DOMAIN_ID'] = str((os.getpid() % 100) + 1)
    t0 = time.monotonic()
    r1 = subprocess.run(
        ['python3', str(RUNNER),
         '--n-uavs', str(n_uavs), '--m-anchors', str(m_anchors),
         '--region-m', str(region_m), '--r-comm-m', str(r_comm_m),
         '--profile', profile_str,
         '--t-warmup-s', str(t_warmup_s),
         '--t-mission-s', str(t_mission_s),
         '--seed', str(seed),
         '--out', str(out_json),
         '--csv-out', str(csv_path),
         '--alpha-cap', str(alpha_cap),
         '--t-timeout-s', str(t_timeout_s)],
        capture_output=True, env=env, check=False,
    )
    wall = time.monotonic() - t0
    if not csv_path.exists():
        return {
            'trial': trial, 'seed': seed, 'error': 'runner crashed',
            'wall_time_s': round(wall, 2),
            'stderr_tail': r1.stderr.decode()[-500:] if r1.stderr else '',
        }
    r2 = subprocess.run(
        ['python3', str(ANALYZER),
         '--csv', str(csv_path),
         '--out', str(analysis_path),
         '--n-followers-init', str(n_followers_init)],
        capture_output=True, env=env, check=False,
    )
    if not analysis_path.exists():
        return {
            'trial': trial, 'seed': seed, 'error': 'analyzer crashed',
            'wall_time_s': round(wall, 2),
            'stderr_tail': r2.stderr.decode()[-500:] if r2.stderr else '',
        }
    a = json.loads(analysis_path.read_text())
    s = a['summary']
    return {
        'trial': trial, 'seed': seed,
        'n_events': s['n_events'],
        'rebal_latency_median': s['rebal_latency_median'],
        'rebal_latency_max': s['rebal_latency_max'],
        'over_cap_interval_median': s['over_cap_interval_median'],
        'over_cap_interval_max': s['over_cap_interval_max'],
        'pass_rebalance_per_event': s['pass_rebalance_per_event'],
        'pass_over_cap_per_event': s['pass_over_cap_per_event'],
        'mission_survived': s['mission_survived'],
        'total_attached_final': s['total_attached_final'],
        'pass_trial': s['pass_trial'],
        'wall_time_s': round(wall, 2),
    }


def _progress(done: int, total: int, t0: float, row: dict) -> None:
    elapsed = time.monotonic() - t0
    eta = elapsed / done * (total - done) if done else 0.0
    print(f'[sweep] {done:4d}/{total} trial={row.get("trial"):3d}  '
          f'pass={row.get("pass_trial")}  '
          f'rebal_max={row.get("rebal_latency_max")}s  '
          f'oc_max={row.get("over_cap_interval_max")}s  '
          f'eta={eta/60:.1f}min', flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--trials', type=int, default=20)
    p.add_argument('--seed-base', type=int, default=1_000_000)
    p.add_argument('--n-uavs', type=int, default=200)
    p.add_argument('--m-anchors', type=int, default=10)
    p.add_argument('--region-m', type=float, default=400.0)
    p.add_argument('--r-comm-m', type=float, default=100.0)
    p.add_argument('--n-victims', type=int, default=3,
                   help='anchors to kill per trial (capped at m_anchors-1)')
    p.add_argument('--t-first-event-s', type=float, default=30.0)
    p.add_argument('--t-step-s', type=float, default=30.0)
    p.add_argument('--t-warmup-s', type=float, default=8.0)
    p.add_argument('--t-mission-s', type=float, default=120.0)
    p.add_argument('--run-id', required=True)
    p.add_argument('--jobs', type=int, default=1)
    p.add_argument('--keep-trials', action='store_true')
    p.add_argument('--alpha-cap', type=float, default=0.25,
                   help='Phase 7 ABL3: set 0 to disable load-balancing weight')
    p.add_argument('--t-timeout-s', type=float, default=5.0,
                   help='Phase 7 ABL2: set 10000 to disable failover')
    args = p.parse_args()

    run_dir = ROOT / 'workspaces' / args.run_id
    trials_dir = run_dir / 'trials'
    trials_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / 'results.csv'
    manifest_path = run_dir / 'manifest.json'

    n_followers_init = args.n_uavs - args.m_anchors
    profile_str = _profile_for(args.m_anchors, args.n_victims,
                               args.t_step_s, args.t_first_event_s)

    manifest = {
        'run_id': args.run_id, 'phase': 6, 'tier': 'B',
        'trials': args.trials, 'seed_base': args.seed_base,
        'n_uavs': args.n_uavs, 'm_anchors': args.m_anchors,
        'n_followers_init': n_followers_init,
        'region_m': args.region_m, 'r_comm_m': args.r_comm_m,
        'n_victims': args.n_victims, 't_first_event_s': args.t_first_event_s,
        't_step_s': args.t_step_s, 'profile_str': profile_str,
        't_warmup_s': args.t_warmup_s, 't_mission_s': args.t_mission_s,
        'jobs': args.jobs,
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    cols = ['trial', 'seed', 'n_events',
            'rebal_latency_median', 'rebal_latency_max',
            'over_cap_interval_median', 'over_cap_interval_max',
            'pass_rebalance_per_event', 'pass_over_cap_per_event',
            'mission_survived', 'total_attached_final',
            'pass_trial', 'wall_time_s']
    with csv_path.open('w', newline='') as f:
        csv.DictWriter(f, fieldnames=cols, extrasaction='ignore').writeheader()

    work = []
    for t in range(args.trials):
        seed = args.seed_base + t
        work.append((
            t, seed, args.n_uavs, args.m_anchors, args.region_m,
            args.r_comm_m, profile_str, args.t_mission_s,
            args.t_warmup_s, n_followers_init, trials_dir,
            args.alpha_cap, args.t_timeout_s,
        ))

    print(f'[sweep] run_id={args.run_id} total={len(work)} jobs={args.jobs} '
          f'profile={profile_str!r}', flush=True)
    t_global = time.monotonic()
    done = 0
    if args.jobs == 1:
        for w in work:
            row = run_one_trial(w)
            _append(csv_path, cols, row); done += 1
            _progress(done, len(work), t_global, row)
            if not args.keep_trials:
                for ext in ('metrics.json', 'timeline.csv', 'analysis.json'):
                    (trials_dir / f'trial_{w[0]:04d}.{ext}').unlink(missing_ok=True)
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futures = {ex.submit(run_one_trial, w): w for w in work}
            for fut in as_completed(futures):
                row = fut.result()
                _append(csv_path, cols, row); done += 1
                _progress(done, len(work), t_global, row)
                if not args.keep_trials:
                    for ext in ('metrics.json', 'timeline.csv', 'analysis.json'):
                        (trials_dir / f'trial_{row.get("trial", 0):04d}.{ext}').unlink(missing_ok=True)

    manifest['completed'] = done
    manifest['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    manifest['wall_time_s'] = round(time.monotonic() - t_global, 1)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    if not args.keep_trials:
        try: shutil.rmtree(trials_dir)
        except OSError: pass

    print(f'[sweep] done {done}/{len(work)} wall={manifest["wall_time_s"]}s '
          f'csv={csv_path}', flush=True)
    return 0


def _append(csv_path: Path, cols, row) -> None:
    with csv_path.open('a', newline='') as f:
        csv.DictWriter(f, fieldnames=cols, extrasaction='ignore').writerow(row)


if __name__ == '__main__':
    sys.exit(main())
