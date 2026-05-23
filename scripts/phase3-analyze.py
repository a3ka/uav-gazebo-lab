#!/usr/bin/env python3
"""Phase 3 task 3.9 — CEP-vs-hops analyzer + sigma_k refit.

Reads a sweep CSV produced by phase3-batch-sweep.py and:
  1. Aggregates per-k stats: mean / median / std of CEP_50, n_trials.
  2. Refits sigma_k formula candidates:
     - paper conservative (GDOP)  sigma_k = sigma_uwb * (1 + delta)^k
     - independent-hops sqrt       sigma_k = sigma_0 * sqrt(k + 1)
     - linear                      sigma_k = a + b * k
  3. Reports residual sum-of-squares + AIC for each candidate; identifies
     best fit.
  4. Writes analysis.json + (optional) matplotlib PNG plot.

Designed to be runnable on the CPU image WITHOUT ROS -- pure pandas /
numpy / scipy. Plot module is optional (skipped if matplotlib unavail).

CLI:
  scripts/phase3-analyze.py \
      --csv workspaces/phase3-2026-05-23/sweep.csv \
      --out workspaces/phase3-2026-05-23/analysis.json \
      --plot workspaces/phase3-2026-05-23/cep_vs_hops.png
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


def _load(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            # Skip any failed trials (cep_50 empty / None)
            if not r.get('cep_50') or r['cep_50'] in ('None', ''):
                continue
            rows.append({
                'k': int(r['k']),
                'trial': int(r['trial']),
                'cep_50': float(r['cep_50']),
                'cep_95': float(r['cep_95']),
                'mean_err': float(r['mean_err']),
                'std_err': float(r['std_err']),
                'n_samples': int(r['n_samples']),
                'observed_hop': int(r['observed_hop']),
                'n_uavs': int(r['n_uavs']),
                'n_edges': int(r['n_edges']),
            })
    return rows


def _by_k(rows: list[dict]) -> dict[int, list[dict]]:
    g: dict[int, list[dict]] = {}
    for r in rows:
        g.setdefault(r['k'], []).append(r)
    return g


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float('nan')
    xs2 = sorted(xs)
    idx = int(min(len(xs2) - 1, max(0, round(p * (len(xs2) - 1)))))
    return xs2[idx]


def _summarize_per_k(grouped: dict[int, list[dict]]) -> list[dict]:
    summary: list[dict] = []
    for k in sorted(grouped):
        ceps = [r['cep_50'] for r in grouped[k]]
        cep95s = [r['cep_95'] for r in grouped[k]]
        mean = sum(ceps) / len(ceps)
        var = sum((c - mean) ** 2 for c in ceps) / max(len(ceps) - 1, 1)
        summary.append({
            'k': k,
            'n_trials': len(ceps),
            'cep50_mean': round(mean, 4),
            'cep50_median': round(_percentile(ceps, 0.5), 4),
            'cep50_std': round(math.sqrt(var), 4),
            'cep50_p25': round(_percentile(ceps, 0.25), 4),
            'cep50_p75': round(_percentile(ceps, 0.75), 4),
            'cep95_mean': round(sum(cep95s) / len(cep95s), 4),
        })
    return summary


# ── model candidates ────────────────────────────────────────────────

def _aic(rss: float, n: int, n_params: int) -> float:
    # Gaussian-residual AIC up to a constant: n*ln(rss/n) + 2*n_params
    if n == 0 or rss <= 0:
        return float('inf')
    return n * math.log(rss / n) + 2 * n_params


def _fit_gdop(per_k: list[dict]) -> dict:
    """sigma_k = sigma_0 * (1 + delta)^k. Two params: sigma_0, delta.

    Fit in log-space: log(cep) = log(sigma_0) + k * log(1+delta)
    """
    xs, ys = [], []
    for s in per_k:
        if s['cep50_median'] > 0:
            xs.append(s['k'])
            ys.append(math.log(s['cep50_median']))
    n = len(xs)
    if n < 2:
        return {'model': 'gdop', 'error': 'need >=2 data points'}
    # Linear regression on (xs, ys)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx > 0 else 0.0
    intercept = my - slope * mx
    sigma_0 = math.exp(intercept)
    delta = math.exp(slope) - 1.0
    # RSS in original space (cep vs prediction)
    pred = [sigma_0 * (1 + delta) ** s['k'] for s in per_k]
    obs = [s['cep50_median'] for s in per_k]
    rss = sum((p - o) ** 2 for p, o in zip(pred, obs))
    return {
        'model': 'gdop',
        'formula': 'cep(k) = sigma_0 * (1+delta)^k',
        'sigma_0': round(sigma_0, 4),
        'delta': round(delta, 4),
        'rss': round(rss, 6),
        'aic': round(_aic(rss, len(per_k), 2), 4),
        'predictions': [round(p, 4) for p in pred],
    }


def _fit_sqrt(per_k: list[dict]) -> dict:
    """sigma_k = sigma_0 * sqrt(k + 1). One param: sigma_0."""
    # Closed-form least-squares for y = a * sqrt(k+1)
    # a* = sum(y * sqrt(k+1)) / sum(k+1)
    xs = [math.sqrt(s['k'] + 1) for s in per_k]
    ys = [s['cep50_median'] for s in per_k]
    num = sum(x * y for x, y in zip(xs, ys))
    den = sum(x * x for x in xs)
    sigma_0 = num / den if den > 0 else 0.0
    pred = [sigma_0 * x for x in xs]
    rss = sum((p - y) ** 2 for p, y in zip(pred, ys))
    return {
        'model': 'sqrt_hop',
        'formula': 'cep(k) = sigma_0 * sqrt(k + 1)',
        'sigma_0': round(sigma_0, 4),
        'rss': round(rss, 6),
        'aic': round(_aic(rss, len(per_k), 1), 4),
        'predictions': [round(p, 4) for p in pred],
    }


def _fit_linear(per_k: list[dict]) -> dict:
    """sigma_k = a + b * k. Two params."""
    xs = [s['k'] for s in per_k]
    ys = [s['cep50_median'] for s in per_k]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx > 0 else 0.0
    a = my - b * mx
    pred = [a + b * x for x in xs]
    rss = sum((p - y) ** 2 for p, y in zip(pred, ys))
    return {
        'model': 'linear',
        'formula': 'cep(k) = a + b * k',
        'a': round(a, 4),
        'b': round(b, 4),
        'rss': round(rss, 6),
        'aic': round(_aic(rss, len(per_k), 2), 4),
        'predictions': [round(p, 4) for p in pred],
    }


def _maybe_plot(per_k: list[dict], fits: dict, png_path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    ks = [s['k'] for s in per_k]
    medians = [s['cep50_median'] for s in per_k]
    p25 = [s['cep50_p25'] for s in per_k]
    p75 = [s['cep50_p75'] for s in per_k]
    err_low = [m - lo for m, lo in zip(medians, p25)]
    err_high = [hi - m for m, hi in zip(medians, p75)]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(ks, medians, yerr=[err_low, err_high], fmt='o', capsize=4,
                color='black', label='CEP_50 median (Q1-Q3)')
    ks_fine = list(range(min(ks), max(ks) + 1))
    for key, label in [
        ('gdop',     'paper GDOP: sigma_0*(1+delta)^k'),
        ('sqrt_hop', 'empirical: sigma_0*sqrt(k+1)'),
        ('linear',   'linear: a+b*k'),
    ]:
        f = fits[key]
        if 'error' in f:
            continue
        if key == 'gdop':
            ys = [f['sigma_0'] * (1 + f['delta']) ** k for k in ks_fine]
        elif key == 'sqrt_hop':
            ys = [f['sigma_0'] * math.sqrt(k + 1) for k in ks_fine]
        else:
            ys = [f['a'] + f['b'] * k for k in ks_fine]
        ax.plot(ks_fine, ys, '-', label=f'{label}  AIC={f["aic"]}')
    ax.set_xlabel('hop count k')
    ax.set_ylabel('CEP_50 (m)')
    ax.set_title('Phase 3 -- CEP vs hops + sigma_k refit')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=9)
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
        print('[analyze] no rows in CSV', file=sys.stderr)
        return 1
    grouped = _by_k(rows)
    per_k = _summarize_per_k(grouped)

    fits = {
        'gdop': _fit_gdop(per_k),
        'sqrt_hop': _fit_sqrt(per_k),
        'linear': _fit_linear(per_k),
    }
    valid = {k: v for k, v in fits.items() if 'error' not in v}
    best = min(valid, key=lambda k: valid[k]['aic']) if valid else None

    analysis = {
        'csv': str(args.csv),
        'total_trials': sum(s['n_trials'] for s in per_k),
        'per_k': per_k,
        'fits': fits,
        'best_fit_model': best,
        'paper_pass_at_k3': _check_paper_pass(per_k),
    }
    args.out.write_text(json.dumps(analysis, indent=2))
    print(f'[analyze] wrote {args.out}')
    print(f'[analyze] best fit: {best} (AIC = {valid[best]["aic"] if best else "n/a"})')
    for s in per_k:
        print(f'  k={s["k"]:2d}  n={s["n_trials"]:4d}  '
              f'CEP_50 median={s["cep50_median"]:7.3f}m  '
              f'(Q1={s["cep50_p25"]:.2f}  Q3={s["cep50_p75"]:.2f}  std={s["cep50_std"]:.2f})')
    if args.plot:
        ok = _maybe_plot(per_k, fits, args.plot)
        print(f'[analyze] plot: {"wrote " + str(args.plot) if ok else "matplotlib unavailable, skipped"}')
    return 0


def _check_paper_pass(per_k: list[dict]) -> dict:
    """Paper criterion: CEP_50 < 100 m at k=3 (see VALIDATION_PLAN.md)."""
    s = next((s for s in per_k if s['k'] == 3), None)
    if s is None:
        return {'k3_available': False}
    return {
        'k3_available': True,
        'k3_cep50_median': s['cep50_median'],
        'k3_cep50_mean': s['cep50_mean'],
        'n_trials': s['n_trials'],
        'threshold_m': 100.0,
        'pass': s['cep50_median'] < 100.0,
    }


if __name__ == '__main__':
    sys.exit(main())
