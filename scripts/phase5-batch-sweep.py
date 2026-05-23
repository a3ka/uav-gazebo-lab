#!/usr/bin/env python3
"""Phase 5 task 5.4 — batch GNSS-spoofing sweep.

Runs phase5-scenario-runner.py once per trial with deterministic seed,
appends per-victim rows to CSV, aggregates manifest + pass-rate stats.

Default scale (N=20, F=2) chosen because the central Python detector +
per-pair UWB publishers DDS-overload at N=50; documented in
docs/results/phase-5.md. Run --n-uavs 50 --n-spoofed 5 with --jobs 1
if you want to reproduce the scaling-limit observation.

CLI:
  scripts/phase5-batch-sweep.py --trials 30 --run-id phase5-prod
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
RUNNER = ROOT / 'scripts' / 'phase5-scenario-runner.py'


def run_one_trial(args_tuple) -> list[dict]:
    (trial, seed, n_uavs, n_spoofed, region_m, t_steady_s, t_observe_s,
     window_s, m_suspect, spoof_offset_m, t_spoof_m, t_pass_budget_s,
     trials_dir) = args_tuple
    metrics_path = trials_dir / f'trial_{trial:04d}.json'
    env = os.environ.copy()
    env['ROS_DOMAIN_ID'] = str((os.getpid() % 100) + 1)
    t0 = time.monotonic()
    proc = subprocess.run(
        ['python3', str(RUNNER),
         '--n-uavs', str(n_uavs),
         '--n-spoofed', str(n_spoofed),
         '--region-m', str(region_m),
         '--t-steady-s', str(t_steady_s),
         '--t-observe-s', str(t_observe_s),
         '--window-s', str(window_s),
         '--m-suspect', str(m_suspect),
         '--spoof-offset-m', str(spoof_offset_m),
         '--t-spoof-m', str(t_spoof_m),
         '--t-pass-budget-s', str(t_pass_budget_s),
         '--seed', str(seed),
         '--out', str(metrics_path),
         '--quiet'],
        capture_output=True, env=env, check=False,
    )
    wall = time.monotonic() - t0
    if not metrics_path.exists():
        return [{
            'trial': trial, 'seed': seed, 'victim_id': -1,
            'spoofed': False, 't_detect_s': None, 'detected': False,
            'wall_time_s': round(wall, 2),
            'n_false_pos': -1, 'detection_rate': -1.0,
            'pass_trial': False, 'error': 'runner crashed',
        }]
    m = json.loads(metrics_path.read_text())
    rows = []
    for v in m['per_victim']:
        rows.append({
            'trial': trial, 'seed': seed,
            'victim_id': v['victim_id'],
            'spoofed': True,
            't_detect_s': v['t_detect_s'],
            'detected': v['detected'],
            'wall_time_s': m['wall_time_s'],
            'n_false_pos': m['n_false_pos'],
            'detection_rate': m['detection_rate'],
            'pass_trial': m['pass_all_in_budget'],
            'n_uavs': m['n_uavs'],
            'n_spoofed': m['n_spoofed'],
            'n_edges': m['n_edges'],
        })
    return rows


def _progress(done: int, total: int, t0: float, rows: list[dict]) -> None:
    elapsed = time.monotonic() - t0
    pct = 100.0 * done / total
    eta = elapsed / done * (total - done) if done else 0.0
    if rows:
        r = rows[0]
        sample = (f"trial={r['trial']:3d} pass={r['pass_trial']} "
                  f"rate={r['detection_rate']:.2f} fp={r['n_false_pos']}")
    else:
        sample = '?'
    print(f'[sweep] {done:4d}/{total} ({pct:5.1f}%) {sample} '
          f'eta={eta/60:.1f}min', flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--trials', type=int, default=30)
    p.add_argument('--seed-base', type=int, default=1_000_000)
    p.add_argument('--n-uavs', type=int, default=20)
    p.add_argument('--n-spoofed', type=int, default=2)
    p.add_argument('--region-m', type=float, default=200.0)
    p.add_argument('--t-steady-s', type=float, default=4.0)
    p.add_argument('--t-observe-s', type=float, default=8.0)
    p.add_argument('--window-s', type=float, default=3.0)
    p.add_argument('--m-suspect', type=int, default=3)
    p.add_argument('--spoof-offset-m', type=float, default=120.0)
    p.add_argument('--t-spoof-m', type=float, default=20.0)
    p.add_argument('--t-pass-budget-s', type=float, default=5.0)
    p.add_argument('--run-id', required=True)
    p.add_argument('--jobs', type=int, default=1)
    p.add_argument('--keep-trials', action='store_true')
    args = p.parse_args()

    run_dir = ROOT / 'workspaces' / args.run_id
    trials_dir = run_dir / 'trials'
    trials_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / 'results.csv'
    manifest_path = run_dir / 'manifest.json'

    manifest = {
        'run_id': args.run_id, 'phase': 5,
        'trials': args.trials, 'seed_base': args.seed_base,
        'n_uavs': args.n_uavs, 'n_spoofed': args.n_spoofed,
        'region_m': args.region_m,
        't_steady_s': args.t_steady_s, 't_observe_s': args.t_observe_s,
        'window_s': args.window_s, 'm_suspect': args.m_suspect,
        'spoof_offset_m': args.spoof_offset_m, 't_spoof_m': args.t_spoof_m,
        't_pass_budget_s': args.t_pass_budget_s,
        'jobs': args.jobs,
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    columns = ['trial', 'seed', 'victim_id', 'spoofed', 't_detect_s',
               'detected', 'n_false_pos', 'detection_rate',
               'pass_trial', 'n_uavs', 'n_spoofed', 'n_edges',
               'wall_time_s']
    with csv_path.open('w', newline='') as f:
        csv.DictWriter(f, fieldnames=columns, extrasaction='ignore').writeheader()

    work = []
    for t in range(args.trials):
        seed = args.seed_base + t
        work.append((
            t, seed, args.n_uavs, args.n_spoofed, args.region_m,
            args.t_steady_s, args.t_observe_s, args.window_s,
            args.m_suspect, args.spoof_offset_m, args.t_spoof_m,
            args.t_pass_budget_s, trials_dir,
        ))

    print(f'[sweep] run_id={args.run_id} total={len(work)} jobs={args.jobs}',
          flush=True)
    t_global = time.monotonic()
    done = 0
    if args.jobs == 1:
        for w in work:
            rows = run_one_trial(w)
            _append(csv_path, columns, rows); done += 1
            _progress(done, len(work), t_global, rows)
            if not args.keep_trials:
                (trials_dir / f'trial_{w[0]:04d}.json').unlink(missing_ok=True)
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futures = {ex.submit(run_one_trial, w): w for w in work}
            for fut in as_completed(futures):
                rows = fut.result()
                _append(csv_path, columns, rows); done += 1
                _progress(done, len(work), t_global, rows)
                if not args.keep_trials:
                    (trials_dir / f'trial_{rows[0]["trial"]:04d}.json').unlink(missing_ok=True)

    manifest['completed'] = done
    manifest['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    manifest['wall_time_s'] = round(time.monotonic() - t_global, 1)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    if not args.keep_trials:
        try: shutil.rmtree(trials_dir)
        except OSError: pass
    print(f'[sweep] done {done}/{len(work)} wall={manifest["wall_time_s"]}s csv={csv_path}',
          flush=True)
    return 0


def _append(csv_path: Path, cols, rows) -> None:
    with csv_path.open('a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        for r in rows: w.writerow(r)


if __name__ == '__main__':
    sys.exit(main())
