#!/usr/bin/env python3
"""Phase 5 task 5.5 — GNSS spoofing detection analyzer.

Reads sweep CSV produced by phase5-batch-sweep.py and computes:
  - Per-victim t_detect distribution (median, p95, p99, mean, std)
  - Per-trial pass rate (all spoofed flagged in budget AND zero FP)
  - Overall detection rate
  - False positive rate per trial
  - Optional histogram + scatter plot
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


def _percentile(xs: list[float], p: float) -> float:
    if not xs: return float('nan')
    xs2 = sorted(xs)
    idx = int(min(len(xs2) - 1, max(0, round(p * (len(xs2) - 1)))))
    return xs2[idx]


def _load(csv_path: Path) -> list[dict]:
    rows = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            try:
                t = float(r['t_detect_s']) if r['t_detect_s'] not in ('', 'None') else None
            except (TypeError, ValueError):
                t = None
            rows.append({
                'trial': int(r['trial']),
                'victim_id': int(r['victim_id']),
                't_detect_s': t,
                'detected': r['detected'].lower() in ('true', '1'),
                'n_false_pos': int(r['n_false_pos']),
                'pass_trial': r['pass_trial'].lower() in ('true', '1'),
                'detection_rate': float(r['detection_rate']),
                'n_uavs': int(r['n_uavs']),
                'n_spoofed': int(r['n_spoofed']),
                'n_edges': int(r['n_edges']),
            })
    return rows


def _summarize(rows: list[dict]) -> dict:
    timings = [r['t_detect_s'] for r in rows if r['t_detect_s'] is not None]
    n_total = len(rows)
    n_detected = sum(1 for r in rows if r['detected'])
    # Trial-level stats
    by_trial: dict[int, list[dict]] = {}
    for r in rows: by_trial.setdefault(r['trial'], []).append(r)
    n_trials = len(by_trial)
    n_trial_pass = sum(1 for ts in by_trial.values() if ts[0]['pass_trial'])
    n_trial_with_fp = sum(1 for ts in by_trial.values() if ts[0]['n_false_pos'] > 0)
    sum_fp = sum(ts[0]['n_false_pos'] for ts in by_trial.values())
    mean_n_uavs = sum(r['n_uavs'] for r in rows) / max(len(rows), 1)
    mean_n_edges = sum(r['n_edges'] for r in rows) / max(len(rows), 1)
    return {
        'n_trials': n_trials,
        'n_victims': n_total,
        'n_detected': n_detected,
        'detection_rate_per_victim': round(n_detected / max(n_total, 1), 4),
        'n_trials_passed': n_trial_pass,
        'trial_pass_rate': round(n_trial_pass / max(n_trials, 1), 4),
        'n_trials_with_fp': n_trial_with_fp,
        'total_fp': sum_fp,
        'mean_fp_per_trial': round(sum_fp / max(n_trials, 1), 3),
        't_detect_median_s': round(_percentile(timings, 0.5), 4) if timings else None,
        't_detect_p95_s': round(_percentile(timings, 0.95), 4) if timings else None,
        't_detect_p99_s': round(_percentile(timings, 0.99), 4) if timings else None,
        't_detect_mean_s': round(sum(timings) / len(timings), 4) if timings else None,
        't_detect_std_s': round(_std(timings), 4) if timings else None,
        't_detect_min_s': round(min(timings), 4) if timings else None,
        't_detect_max_s': round(max(timings), 4) if timings else None,
        'mean_n_uavs': round(mean_n_uavs, 1),
        'mean_n_edges': round(mean_n_edges, 1),
    }


def _std(xs: list[float]) -> float:
    if len(xs) < 2: return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _maybe_plot(rows: list[dict], summary: dict, png_path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    timings = [r['t_detect_s'] for r in rows if r['t_detect_s'] is not None]
    if not timings: return False
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(timings, bins=20, color='steelblue', edgecolor='black')
    threshold = 5.0  # paper Pillar 5 criterion
    ax.axvline(threshold, color='red', linestyle='--',
               label=f'paper criterion <{threshold}s')
    median = summary['t_detect_median_s']
    if median is not None:
        ax.axvline(median, color='green', linestyle=':',
                   label=f'median={median}s')
    ax.set_xlabel('detection time (s after spoof injection)')
    ax.set_ylabel('count (victim-detections)')
    ax.set_title(
        f'Phase 5 — GNSS spoofing detection time\n'
        f'detection_rate_per_victim={summary["detection_rate_per_victim"]*100:.1f}%  '
        f'trial_pass_rate={summary["trial_pass_rate"]*100:.1f}%  '
        f'mean_FP/trial={summary["mean_fp_per_trial"]}'
    )
    ax.legend(loc='best', fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)
    return True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--csv', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--plot', type=Path, default=None)
    args = p.parse_args()
    rows = _load(args.csv)
    if not rows:
        print('[analyze] empty CSV', file=sys.stderr); return 1
    summary = _summarize(rows)
    analysis = {'csv': str(args.csv), 'summary': summary}
    args.out.write_text(json.dumps(analysis, indent=2))
    print(f'[analyze] wrote {args.out}')
    print('=== Phase 5 summary ===')
    for k, v in summary.items():
        print(f'  {k:30s}  {v}')
    if args.plot:
        ok = _maybe_plot(rows, summary, args.plot)
        print(f'[analyze] plot: {"wrote " + str(args.plot) if ok else "skipped"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
