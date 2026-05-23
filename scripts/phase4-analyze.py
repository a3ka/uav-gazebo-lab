#!/usr/bin/env python3
"""Phase 4 task 4.7 — failover distribution analyzer.

Reads results.csv produced by phase4-batch-sweep.py and produces:
  - Per-scenario distribution stats (median, p95, p99, mean, std, n)
  - Per-scenario pass rate (% of followers that switched within
    pass_threshold_s = t_timeout + t_pass_budget)
  - Optional matplotlib histogram per scenario

CLI:
  scripts/phase4-analyze.py \
      --csv workspaces/phase4-prod/results.csv \
      --out workspaces/phase4-prod/analysis.json \
      --plot workspaces/phase4-prod/switching_distributions.png
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float('nan')
    xs2 = sorted(xs)
    idx = int(min(len(xs2) - 1, max(0, round(p * (len(xs2) - 1)))))
    return xs2[idx]


def _summarize(rows: list[dict]) -> dict:
    per: dict[str, list[dict]] = {}
    for r in rows:
        per.setdefault(r['scenario'], []).append(r)
    out: list[dict] = []
    for sc in sorted(per):
        bucket = per[sc]
        timings = [r['t'] for r in bucket if r['t'] is not None]
        passes = sum(1 for r in bucket if r['ok'])
        threshold = bucket[0]['threshold']
        if timings:
            mean = sum(timings) / len(timings)
            var = sum((t - mean) ** 2 for t in timings) / max(len(timings) - 1, 1)
            std = math.sqrt(var)
        else:
            mean = float('nan'); std = float('nan')
        out.append({
            'scenario': sc,
            'n_total': len(bucket),
            'n_pass': passes,
            'pass_rate': round(passes / max(len(bucket), 1), 4),
            'pass_threshold_s': threshold,
            'switch_time_median': round(_percentile(timings, 0.5), 4) if timings else None,
            'switch_time_p95': round(_percentile(timings, 0.95), 4) if timings else None,
            'switch_time_p99': round(_percentile(timings, 0.99), 4) if timings else None,
            'switch_time_mean': round(mean, 4) if timings else None,
            'switch_time_std': round(std, 4) if timings else None,
            'switch_time_min': round(min(timings), 4) if timings else None,
            'switch_time_max': round(max(timings), 4) if timings else None,
        })
    return out


def _load(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            t = r.get('switching_time_s')
            ok = r.get('detection_ok', '').lower() in ('true', '1', 'yes')
            try:
                t = float(t) if t not in ('', 'None', None) else None
            except (TypeError, ValueError):
                t = None
            rows.append({
                'scenario': r['scenario'],
                't': t,
                'ok': ok,
                'threshold': float(r.get('pass_threshold_s', 15.0) or 15.0),
            })
    return rows


def _maybe_plot(rows: list[dict], png_path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    per: dict[str, list[float]] = {}
    for r in rows:
        if r['t'] is not None:
            per.setdefault(r['scenario'], []).append(r['t'])
    if not per:
        return False
    sc_keys = sorted(per)
    fig, axes = plt.subplots(1, len(sc_keys), figsize=(4 * len(sc_keys), 4),
                             sharey=False)
    if len(sc_keys) == 1:
        axes = [axes]
    threshold = rows[0]['threshold']
    for ax, sc in zip(axes, sc_keys):
        xs = per[sc]
        ax.hist(xs, bins=20, color='steelblue', edgecolor='black')
        ax.axvline(threshold, color='red', linestyle='--',
                   label=f'pass <{threshold}s')
        ax.set_title(f'{sc}  n={len(xs)}  median={sorted(xs)[len(xs)//2]:.2f}s')
        ax.set_xlabel('switching_time (s)')
        ax.set_ylabel('count')
        ax.legend(loc='best', fontsize=8)
        ax.grid(True, alpha=0.3)
    fig.suptitle('Phase 4 -- failover switching time per scenario')
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
        print('[analyze] no rows', file=sys.stderr); return 1
    summary = _summarize(rows)
    analysis = {
        'csv': str(args.csv),
        'total_measurements': len(rows),
        'per_scenario': summary,
    }
    args.out.write_text(json.dumps(analysis, indent=2))
    print(f'[analyze] wrote {args.out}')
    print(f"{'scenario':<6} {'n':>4} {'pass%':>6} {'med':>8} {'p95':>8} {'p99':>8} {'mean':>8}")
    for s in summary:
        med = s['switch_time_median'] if s['switch_time_median'] is not None else float('nan')
        p95 = s['switch_time_p95'] if s['switch_time_p95'] is not None else float('nan')
        p99 = s['switch_time_p99'] if s['switch_time_p99'] is not None else float('nan')
        mn = s['switch_time_mean'] if s['switch_time_mean'] is not None else float('nan')
        print(f"{s['scenario']:<6} {s['n_total']:>4} {s['pass_rate']*100:>5.1f}% "
              f"{med:>7.3f}s {p95:>7.3f}s {p99:>7.3f}s {mn:>7.3f}s")
    if args.plot:
        ok = _maybe_plot(rows, args.plot)
        print(f'[analyze] plot: {"wrote " + str(args.plot) if ok else "skipped (no matplotlib or no data)"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
