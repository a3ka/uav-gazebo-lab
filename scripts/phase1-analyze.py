#!/usr/bin/env python3
"""Phase 1 batch sweep -- ROC + sensitivity analysis.

Reads every CSV produced by scripts/phase1-batch-sweep.sh under
workspaces/phase1-sweep/ and emits:
  - per-variant T_verify sweep table (FAR, FRR at each T)
  - per-variant best operating point that meets pass criteria
    (FAR<5%, FRR<10%)
  - per-variant ROC AUC
  - cross-variant comparison summary

Usage:
    python3 scripts/phase1-analyze.py
    python3 scripts/phase1-analyze.py --dir workspaces/phase1-sweep
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def roc_table(honest: list[float], byz: list[float], step: float = 0.025):
    """Returns list of (T, FAR, FRR) tuples sweeping T in [0, 1]."""
    out = []
    t = 0.0
    while t <= 1.0 + 1e-9:
        far = sum(1 for v in byz if v > t) / max(len(byz), 1)
        frr = sum(1 for v in honest if v <= t) / max(len(honest), 1)
        out.append((t, far, frr))
        t += step
    return out


def auc_wmw(honest: list[float], byz: list[float]) -> float:
    """ROC AUC via Wilcoxon-Mann-Whitney: P(V_honest > V_byzantine), ties = 0.5.
    Mathematically equivalent to the geometric trapezoidal AUC but cleaner
    when many tied values exist (which we do at V=0 for byzantine).
    """
    if not honest or not byz:
        return 0.0
    wins = ties = 0
    for h in honest:
        for b in byz:
            if h > b:
                wins += 1
            elif h == b:
                ties += 1
    return (wins + 0.5 * ties) / (len(honest) * len(byz))


def best_operating(roc, far_max=0.05, frr_max=0.10):
    """Find lowest FRR subject to FAR<far_max AND FRR<frr_max."""
    candidates = [(t, far, frr) for t, far, frr in roc if far < far_max and frr < frr_max]
    if not candidates:
        return None
    return min(candidates, key=lambda x: x[2])


def summarize(name: str, csv_path: Path):
    rows = list(csv.DictReader(csv_path.open()))
    honest = [float(r['V_score']) for r in rows if r['label'] == 'honest']
    byz    = [float(r['V_score']) for r in rows if r['label'] == 'byzantine']
    roc = roc_table(honest, byz)
    auc = auc_wmw(honest, byz)
    best = best_operating(roc)
    # FAR/FRR at paper-locked T=0.30
    far_03 = sum(1 for v in byz if v > 0.30) / max(len(byz), 1)
    frr_03 = sum(1 for v in honest if v <= 0.30) / max(len(honest), 1)
    return {
        'name': name,
        'n_honest': len(honest),
        'n_byz': len(byz),
        'honest_median': sorted(honest)[len(honest) // 2] if honest else 0.0,
        'honest_mean':   sum(honest) / max(len(honest), 1),
        'byz_max':       max(byz) if byz else 0.0,
        'byz_mean':      sum(byz) / max(len(byz), 1),
        'auc':           auc,
        'far_at_03':     far_03,
        'frr_at_03':     frr_03,
        'best_t':        best[0] if best else None,
        'best_far':      best[1] if best else None,
        'best_frr':      best[2] if best else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='workspaces/phase1-sweep')
    args = ap.parse_args()

    sweep_dir = Path(args.dir)
    csvs = sorted(sweep_dir.glob('*.csv'))
    if not csvs:
        print(f'No CSVs found in {sweep_dir}')
        return 1

    print(f'Analyzing {len(csvs)} variants from {sweep_dir}')
    print('')

    summaries = []
    for csv_path in csvs:
        s = summarize(csv_path.stem, csv_path)
        summaries.append(s)

    print('=' * 100)
    print(f'{"variant":24s} {"n_h":>5} {"n_b":>5} {"H_med":>6} {"H_mean":>7} {"B_max":>6} {"B_mean":>7} {"AUC":>7} {"FAR@03":>7} {"FRR@03":>7} {"best_T":>7} {"best_FRR":>9}')
    print('-' * 100)
    for s in summaries:
        best_t = f'{s["best_t"]:.3f}' if s['best_t'] is not None else '   -- '
        best_frr = f'{s["best_frr"]*100:.2f}%' if s['best_frr'] is not None else '   -- '
        print(f'{s["name"]:24s} {s["n_honest"]:>5d} {s["n_byz"]:>5d} '
              f'{s["honest_median"]:>6.3f} {s["honest_mean"]:>7.3f} '
              f'{s["byz_max"]:>6.3f} {s["byz_mean"]:>7.3f} '
              f'{s["auc"]:>7.4f} '
              f'{s["far_at_03"]*100:>6.2f}% {s["frr_at_03"]*100:>6.2f}% '
              f'{best_t:>7} {best_frr:>9}')
    print('=' * 100)

    print('')
    print('Reading guide:')
    print('  n_h/n_b      -- honest / byzantine trial count')
    print('  H_med/H_mean -- honest V_score median / mean')
    print('  B_max/B_mean -- byzantine V_score max / mean')
    print('  AUC          -- ROC area-under-curve (1.0 = perfect separability)')
    print('  FAR@03/FRR@03 -- at paper-locked T_verify=0.3')
    print('  best_T        -- threshold giving lowest FRR with FAR<5% and FRR<10%')
    print('  best_FRR      -- the FRR achieved at best_T')


if __name__ == '__main__':
    raise SystemExit(main())
