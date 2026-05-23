#!/usr/bin/env python3
"""Phase 4 task 4.6 — batch failover sweep.

Iterates over scenarios × trials, running phase4-scenario-runner.py
once per (scenario, trial), and aggregates results into a CSV.

S4 (partial partition) deferred to integration phase — requires
CAP_NET_ADMIN for iptables / tc rules.
Packet-loss comm condition deferred for same reason.

CLI:
  scripts/phase4-batch-sweep.py \
      --scenarios S1 S2 S3 S5 \
      --trials-per-scenario 30 \
      --n-anchors 3 --n-followers 10 \
      --run-id phase4-prod \
      --jobs 1
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
RUNNER = ROOT / 'scripts' / 'phase4-scenario-runner.py'


def run_one_trial(args_tuple) -> list[dict]:
    (scenario, trial, n_anchors, n_followers, victim_id,
     t_steady, t_pass_budget, t_timeout, trials_dir) = args_tuple
    metrics_path = trials_dir / f'{scenario}_t{trial:03d}.json'
    log_dir = trials_dir / f'{scenario}_t{trial:03d}.logs'
    env = os.environ.copy()
    env['ROS_DOMAIN_ID'] = str((os.getpid() % 100) + 1)
    t0 = time.monotonic()
    subprocess.run(
        ['python3', str(RUNNER),
         '--scenario', scenario,
         '--n-anchors', str(n_anchors),
         '--n-followers', str(n_followers),
         '--victim-anchor-id', str(victim_id),
         '--t-steady-s', str(t_steady),
         '--t-pass-budget-s', str(t_pass_budget),
         '--t-timeout-s', str(t_timeout),
         '--out', str(metrics_path),
         '--log-dir', str(log_dir)],
        capture_output=True, env=env, check=False,
    )
    wall = time.monotonic() - t0
    if not metrics_path.exists():
        return [{'scenario': scenario, 'trial': trial, 'follower_id': -1,
                 'switching_time_s': None, 'detection_ok': False,
                 'wall_time_s': round(wall, 2), 'error': 'runner crashed'}]
    m = json.loads(metrics_path.read_text())
    rows = []
    for r in m['per_follower']:
        rows.append({
            'scenario': scenario,
            'trial': trial,
            'follower_id': r['follower_id'],
            'switching_time_s': r['switching_time_s'],
            'detection_ok': r['detection_ok'],
            'n_anchors': m['n_anchors'],
            'n_followers': m['n_followers'],
            'pass_threshold_s': m['pass_threshold_s'],
            'wall_time_s': m['wall_time_s'],
        })
    return rows


def _progress(done: int, total: int, t0: float, rows: list[dict]) -> None:
    elapsed = time.monotonic() - t0
    pct = 100.0 * done / total
    eta = elapsed / done * (total - done) if done else 0.0
    sc = rows[0]['scenario']
    trial = rows[0]['trial']
    pass_n = sum(1 for r in rows if r['detection_ok'])
    valid_t = [r['switching_time_s'] for r in rows if r['switching_time_s'] is not None]
    med = round(sorted(valid_t)[len(valid_t) // 2], 3) if valid_t else None
    print(
        f'[sweep] {done:4d}/{total} ({pct:5.1f}%) '
        f'{sc} t={trial:03d} pass={pass_n}/{len(rows)} med={med}s '
        f'eta={eta/60:.1f}min',
        flush=True,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--scenarios', nargs='+', default=['S1', 'S2', 'S3', 'S5'])
    p.add_argument('--trials-per-scenario', type=int, default=30)
    p.add_argument('--n-anchors', type=int, default=3)
    p.add_argument('--n-followers', type=int, default=10)
    p.add_argument('--victim-anchor-id', type=int, default=0)
    p.add_argument('--t-steady-s', type=float, default=5.0)
    p.add_argument('--t-pass-budget-s', type=float, default=10.0)
    p.add_argument('--t-timeout-s', type=float, default=5.0)
    p.add_argument('--run-id', type=str, required=True)
    p.add_argument('--jobs', type=int, default=1)
    p.add_argument('--keep-logs', action='store_true',
                   help='do not delete per-trial logs after CSV append')
    args = p.parse_args()

    run_dir = ROOT / 'workspaces' / args.run_id
    trials_dir = run_dir / 'trials'
    trials_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / 'results.csv'
    manifest_path = run_dir / 'manifest.json'

    manifest = {
        'run_id': args.run_id,
        'phase': 4,
        'scenarios': args.scenarios,
        'trials_per_scenario': args.trials_per_scenario,
        'n_anchors': args.n_anchors,
        'n_followers': args.n_followers,
        'victim_anchor_id': args.victim_anchor_id,
        't_steady_s': args.t_steady_s,
        't_pass_budget_s': args.t_pass_budget_s,
        't_timeout_s': args.t_timeout_s,
        'jobs': args.jobs,
        'total_trials': len(args.scenarios) * args.trials_per_scenario,
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    columns = ['scenario', 'trial', 'follower_id', 'switching_time_s',
               'detection_ok', 'n_anchors', 'n_followers',
               'pass_threshold_s', 'wall_time_s']
    with csv_path.open('w', newline='') as f:
        csv.DictWriter(f, fieldnames=columns, extrasaction='ignore').writeheader()

    work: list[tuple] = []
    for sc in args.scenarios:
        for t in range(args.trials_per_scenario):
            work.append((
                sc, t, args.n_anchors, args.n_followers,
                args.victim_anchor_id, args.t_steady_s,
                args.t_pass_budget_s, args.t_timeout_s, trials_dir,
            ))

    print(f'[sweep] run_id={args.run_id} total={len(work)} jobs={args.jobs}',
          flush=True)
    t_global = time.monotonic()
    done = 0

    if args.jobs == 1:
        for w in work:
            rows = run_one_trial(w)
            _append_rows(csv_path, columns, rows)
            done += 1
            _progress(done, len(work), t_global, rows)
            if not args.keep_logs:
                _cleanup_trial(trials_dir, rows[0]['scenario'], rows[0]['trial'])
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futures = {ex.submit(run_one_trial, w): w for w in work}
            for fut in as_completed(futures):
                rows = fut.result()
                _append_rows(csv_path, columns, rows)
                done += 1
                _progress(done, len(work), t_global, rows)
                if not args.keep_logs:
                    _cleanup_trial(trials_dir, rows[0]['scenario'], rows[0]['trial'])

    manifest['completed'] = done
    manifest['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    manifest['wall_time_s'] = round(time.monotonic() - t_global, 1)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    if not args.keep_logs:
        try:
            shutil.rmtree(trials_dir)
        except OSError:
            pass
    print(f'[sweep] done {done}/{len(work)} wall={manifest["wall_time_s"]}s csv={csv_path}',
          flush=True)
    return 0


def _append_rows(csv_path: Path, columns, rows: list[dict]) -> None:
    with csv_path.open('a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        for r in rows:
            w.writerow(r)


def _cleanup_trial(trials_dir: Path, scenario: str, trial: int) -> None:
    (trials_dir / f'{scenario}_t{trial:03d}.json').unlink(missing_ok=True)
    log_dir = trials_dir / f'{scenario}_t{trial:03d}.logs'
    if log_dir.exists():
        shutil.rmtree(log_dir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
