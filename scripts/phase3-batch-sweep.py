#!/usr/bin/env python3
"""Phase 3 task 3.8 — batch CEP-vs-hops sweep runner.

For each k in --k-list × --trials-per-k repetitions:
  1. Generate a topology (seed unique per (k, trial))
  2. Run phase3-scenario-runner.py as a SUBPROCESS (fresh rclpy context
     per trial — safer than reusing one process across trials, where
     ROS DDS state can contaminate)
  3. Parse the per-trial metrics.json
  4. Append a CSV row aggregating: k, trial, seed, cep_50, cep_95,
     mean_err, std_err, n_samples, observed_hop, n_uavs, n_edges,
     wall_time_s

Output:
  workspaces/<run_id>/trials/k<K>_t<T>.json   per-trial raw metrics
  workspaces/<run_id>/sweep.csv               aggregated rows
  workspaces/<run_id>/manifest.json           run params, completion %

The sweep is deterministic: same --k-list, --trials-per-k, --seed-base
reproduces identical results (each trial's UWB/TRN noise is seeded
from a deterministic function of k+trial+seed_base).

CPU-only (Phase 3 has no vision/PoO -- TRN is mocked, see task 3.4).
Phase 6+ will swap TRN mock for real Phase 1 pipeline (GPU).

CLI:
  scripts/phase3-batch-sweep.py \
      --k-list 0 1 2 3 5 \
      --trials-per-k 200 \
      --warmup-s 10 --trial-s 30 \
      --run-id phase3-2026-05-23 \
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
GEN = ROOT / 'scripts' / 'phase3-gen-topology.py'
RUNNER = ROOT / 'scripts' / 'phase3-scenario-runner.py'


def _trial_seed(k: int, trial: int, seed_base: int) -> int:
    # Stable per-cell seed; collision-free across k=[0..15], trial=[0..9999].
    return seed_base + k * 100_000 + trial


def run_one_trial(args_tuple) -> dict:
    (k, trial, seed_base, trials_dir, warmup_s, trial_s,
     sigma_uwb_m, sigma_trn_m, trn_period_s, m_relay) = args_tuple
    seed = _trial_seed(k, trial, seed_base)
    topo_path = trials_dir / f'topo_k{k}_t{trial:04d}.json'
    metrics_path = trials_dir / f'metrics_k{k}_t{trial:04d}.json'
    # Unique ROS_DOMAIN_ID per WORKER process (not per trial).
    # Workers run trials sequentially -> sequential trials in the same
    # worker share a domain (no DDS overlap since prior scenario exits
    # before the next launches). Parallel workers get different domains
    # so concurrent /uwb/range, /trn/fix etc. don't cross-talk.
    env = os.environ.copy()
    env['ROS_DOMAIN_ID'] = str((os.getpid() % 100) + 1)
    t0 = time.monotonic()
    # 1. topology
    gen_args = ['python3', str(GEN), '--k', str(k), '--seed', str(seed),
                '--out', str(topo_path), '--check']
    if m_relay is not None:
        gen_args += ['--m-relay', str(m_relay)]
    subprocess.run(gen_args, check=True, capture_output=True, env=env)
    # 2. scenario
    subprocess.run(
        ['python3', str(RUNNER),
         '--topology', str(topo_path), '--out', str(metrics_path),
         '--warmup-s', str(warmup_s), '--trial-s', str(trial_s),
         '--sigma-uwb-m', str(sigma_uwb_m),
         '--sigma-trn-m', str(sigma_trn_m),
         '--trn-period-s', str(trn_period_s),
         '--quiet'],
        check=True, capture_output=True, env=env,
    )
    wall = time.monotonic() - t0
    m = json.loads(metrics_path.read_text())
    return {
        'k': k, 'trial': trial, 'seed': seed,
        'observed_hop': m['observed_hop_to_anchor'],
        'cep_50': m['cep_50'], 'cep_95': m['cep_95'],
        'mean_err': m['mean_err'], 'std_err': m['std_err'],
        'n_samples': m['n_samples'],
        'n_uavs': m['n_uavs'], 'n_edges': m['n_edges'],
        'wall_time_s': round(wall, 2),
        'test_uav_id': m['test_uav_id'],
        'ground_truth_x': m['ground_truth'][0],
        'ground_truth_y': m['ground_truth'][1],
        'ground_truth_z': m['ground_truth'][2],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--k-list', nargs='+', type=int, default=[0, 1, 2, 3, 5])
    p.add_argument('--trials-per-k', type=int, default=200)
    p.add_argument('--seed-base', type=int, default=1_000_000)
    p.add_argument('--warmup-s', type=float, default=10.0)
    p.add_argument('--trial-s', type=float, default=30.0)
    p.add_argument('--sigma-uwb-m', type=float, default=0.1)
    p.add_argument('--sigma-trn-m', type=float, default=5.0)
    p.add_argument('--trn-period-s', type=float, default=10.0)
    p.add_argument('--run-id', type=str, required=True)
    p.add_argument('--jobs', type=int, default=1,
                   help='parallel trials (CPU-bound; rclpy is single-thread per proc)')
    p.add_argument('--keep-topologies', action='store_true',
                   help='do not delete per-trial topology + metrics JSON after CSV append')
    p.add_argument('--m-relay', type=int, default=None,
                   help='UAVs per follower level; None=M (triangulated), 1=linear sparse chain')
    args = p.parse_args()

    run_dir = ROOT / 'workspaces' / args.run_id
    trials_dir = run_dir / 'trials'
    trials_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / 'sweep.csv'
    manifest_path = run_dir / 'manifest.json'

    manifest = {
        'run_id': args.run_id,
        'phase': 3,
        'k_list': args.k_list,
        'trials_per_k': args.trials_per_k,
        'seed_base': args.seed_base,
        'warmup_s': args.warmup_s,
        'trial_s': args.trial_s,
        'sigma_uwb_m': args.sigma_uwb_m,
        'sigma_trn_m': args.sigma_trn_m,
        'trn_period_s': args.trn_period_s,
        'jobs': args.jobs,
        'total_trials': len(args.k_list) * args.trials_per_k,
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'completed': 0,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    columns = [
        'k', 'trial', 'seed', 'observed_hop',
        'cep_50', 'cep_95', 'mean_err', 'std_err',
        'n_samples', 'n_uavs', 'n_edges',
        'test_uav_id', 'ground_truth_x', 'ground_truth_y', 'ground_truth_z',
        'wall_time_s',
    ]
    with csv_path.open('w', newline='') as f:
        csv.DictWriter(f, fieldnames=columns).writeheader()

    work: list[tuple] = []
    for k in args.k_list:
        for t in range(args.trials_per_k):
            work.append((
                k, t, args.seed_base, trials_dir,
                args.warmup_s, args.trial_s,
                args.sigma_uwb_m, args.sigma_trn_m, args.trn_period_s,
                args.m_relay,
            ))

    print(f'[sweep] run_id={args.run_id} total={len(work)} jobs={args.jobs}', flush=True)
    t_global = time.monotonic()
    done = 0
    if args.jobs == 1:
        for w in work:
            row = run_one_trial(w)
            _append_row(csv_path, columns, row)
            done += 1
            _progress(done, len(work), t_global, row)
            if not args.keep_topologies:
                (trials_dir / f'topo_k{row["k"]}_t{row["trial"]:04d}.json').unlink(missing_ok=True)
                (trials_dir / f'metrics_k{row["k"]}_t{row["trial"]:04d}.json').unlink(missing_ok=True)
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futures = {ex.submit(run_one_trial, w): w for w in work}
            for fut in as_completed(futures):
                row = fut.result()
                _append_row(csv_path, columns, row)
                done += 1
                _progress(done, len(work), t_global, row)
                if not args.keep_topologies:
                    (trials_dir / f'topo_k{row["k"]}_t{row["trial"]:04d}.json').unlink(missing_ok=True)
                    (trials_dir / f'metrics_k{row["k"]}_t{row["trial"]:04d}.json').unlink(missing_ok=True)

    manifest['completed'] = done
    manifest['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    manifest['wall_time_s'] = round(time.monotonic() - t_global, 1)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    if not args.keep_topologies:
        # Trials dir may be empty -- clean it up
        try:
            shutil.rmtree(trials_dir)
        except OSError:
            pass

    print(f'[sweep] done {done}/{len(work)} wall={manifest["wall_time_s"]}s csv={csv_path}',
          flush=True)
    return 0


def _append_row(csv_path: Path, columns, row: dict) -> None:
    with csv_path.open('a', newline='') as f:
        csv.DictWriter(f, fieldnames=columns).writerow(row)


def _progress(done: int, total: int, t0: float, row: dict) -> None:
    elapsed = time.monotonic() - t0
    pct = 100.0 * done / total
    eta = elapsed / done * (total - done) if done else 0.0
    print(
        f'[sweep] {done:4d}/{total} ({pct:5.1f}%) '
        f'k={row["k"]} t={row["trial"]:4d} cep_50={row["cep_50"]:6.2f}m '
        f'wall={row["wall_time_s"]:.1f}s eta={eta/60:.1f}min',
        flush=True,
    )


if __name__ == '__main__':
    sys.exit(main())
