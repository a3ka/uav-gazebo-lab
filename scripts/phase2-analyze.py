#!/usr/bin/env python3
"""Phase 2 analysis -- compute Prop 1/2/3 stats from scenario CSVs.

Reads exclusions.csv files produced by phase2-scenario-runner.py and
emits per-scenario tables + a paper-vs-measured comparison.

Naming convention: `<label>.exclusions.csv` where <label> may encode
(M, f) as in `phase2-m3f1-trial0.exclusions.csv`. Labels without
encoded params are still summarised, just not grouped.

Per-scenario metrics:
  - n_excl_events        total ExclusionEvent records observed
  - n_byzantine_excluded distinct byzantine targets with >= 1 event
  - n_honest_excluded    distinct honest targets with >= 1 event (Prop 1)
  - first_t_per_target   time of first observer's declaration per
                         byzantine target (used for Prop 3)
  - median_t_byz         median across byzantine targets in trial
  - 95th_t_byz           95th percentile of those

Pass criteria (per VALIDATION_PLAN.md Phase 2):
  Prop 1: n_honest_excluded == 0 across all trials/cells
  Prop 3: median_t_byz < 215 s AND 95th_t_byz < 300 s (per cell)

Paper Section IV-C / IV-F formula for predicted T_ind:
  T_ind = (R_init - T_reject) / (alpha_neg * R_bar_honest * nu_verify)
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from statistics import median


def parse_label(name: str) -> dict:
    """Extract (M, f, trial) if encoded as 'm{M}f{F}-trial{N}'."""
    m = re.search(r'm(\d+)f(\d+)(?:-trial(\d+))?', name)
    if not m:
        return {'label': name, 'M': None, 'f': None, 'trial': None}
    return {
        'label': name,
        'M': int(m.group(1)),
        'f': int(m.group(2)),
        'trial': int(m.group(3)) if m.group(3) else None,
    }


def analyze_csv(csv_path: Path, n_honest: int | None, n_byzantine: int | None) -> dict:
    rows = list(csv.DictReader(csv_path.open()))
    if not rows:
        return {
            'n_excl_events': 0, 'n_byz_excluded': 0, 'n_honest_excluded': 0,
            'first_t_per_target': {}, 'median_t_byz': None, 'p95_t_byz': None,
        }

    # first-observation-time per target (across all observers)
    first_t: dict[int, float] = {}
    for r in rows:
        tgt = int(r['target'])
        t = float(r['t_exclusion_s'])
        if tgt not in first_t or t < first_t[tgt]:
            first_t[tgt] = t

    # Classify targets — convention: first n_honest UAV IDs are honest,
    # remainder byzantine (matches phase2-scenario-runner.py)
    if n_honest is not None and n_byzantine is not None:
        honest_set = set(range(n_honest))
        byz_set = set(range(n_honest, n_honest + n_byzantine))
        honest_excluded = honest_set & set(first_t.keys())
        byz_excluded = byz_set & set(first_t.keys())
    else:
        honest_excluded, byz_excluded = set(), set(first_t.keys())

    times_byz = sorted(first_t[t] for t in byz_excluded)
    return {
        'n_excl_events': len(rows),
        'n_byz_excluded': len(byz_excluded),
        'n_honest_excluded': len(honest_excluded),
        'first_t_per_target': first_t,
        'median_t_byz': median(times_byz) if times_byz else None,
        'p95_t_byz': times_byz[int(0.95 * (len(times_byz) - 1))] if times_byz else None,
        'honest_excluded_ids': sorted(honest_excluded),
        'byz_excluded_ids': sorted(byz_excluded),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', type=str, nargs='+', required=True,
                    help='Path(s) to *.exclusions.csv files')
    ap.add_argument('--n-honest', type=int, default=None,
                    help='UAVs 0..n_honest-1 are honest (else cannot classify)')
    ap.add_argument('--n-byzantine', type=int, default=None,
                    help='UAVs n_honest..n_honest+n_byz-1 are byzantine')
    ap.add_argument('--alpha-neg', type=float, default=0.15)
    ap.add_argument('--r-init', type=float, default=0.5)
    ap.add_argument('--t-reject', type=float, default=0.20)
    ap.add_argument('--r-bar-honest', type=float, default=0.8,
                    help='Mean honest R for paper formula')
    ap.add_argument('--nu-verify-s', type=float, default=45.0,
                    help='Verifications per UAV per second (-1 of period)')
    args = ap.parse_args()

    # Paper-predicted T_ind
    nu_per_s = 1.0 / args.nu_verify_s
    t_ind_paper = (args.r_init - args.t_reject) / (
        args.alpha_neg * args.r_bar_honest * nu_per_s
    )
    print(f'Paper-predicted T_ind = (R_init-T_reject) / (alpha_neg * R_bar * nu)')
    print(f'  = {args.r_init - args.t_reject:.2f} / '
          f'({args.alpha_neg} * {args.r_bar_honest} * {nu_per_s:.5f}) = {t_ind_paper:.1f} s')
    print('')

    print('=' * 100)
    print(f'{"label":36s} {"M":>3} {"f":>3} {"events":>7} {"byz_x":>6} {"hon_x":>6} '
          f'{"med_t":>9} {"p95_t":>9} {"Prop1":>6} {"Prop3":>6}')
    print('-' * 100)

    all_med: list[float] = []
    all_p95: list[float] = []
    any_honest_excluded = False

    for csv_str in args.csv:
        p = Path(csv_str)
        label = parse_label(p.stem.replace('.exclusions', ''))
        stats = analyze_csv(p, args.n_honest, args.n_byzantine)

        prop1 = 'PASS' if stats['n_honest_excluded'] == 0 else 'FAIL'
        prop3 = '--'
        if stats['median_t_byz'] is not None:
            ok = stats['median_t_byz'] < 215.0 and (stats['p95_t_byz'] or 0) < 300.0
            prop3 = 'PASS' if ok else 'FAIL'
            all_med.append(stats['median_t_byz'])
            all_p95.append(stats['p95_t_byz'] or 0)
        if stats['n_honest_excluded'] > 0:
            any_honest_excluded = True

        m_str = str(label['M']) if label['M'] else '--'
        f_str = str(label['f']) if label['f'] else '--'
        med_str = f'{stats["median_t_byz"]:.1f}' if stats['median_t_byz'] is not None else '--'
        p95_str = f'{stats["p95_t_byz"]:.1f}' if stats['p95_t_byz'] is not None else '--'

        print(f'{label["label"]:36s} {m_str:>3} {f_str:>3} '
              f'{stats["n_excl_events"]:>7d} {stats["n_byz_excluded"]:>6d} '
              f'{stats["n_honest_excluded"]:>6d} '
              f'{med_str:>9} {p95_str:>9} {prop1:>6} {prop3:>6}')

    print('=' * 100)
    print('')
    if all_med:
        print(f'Aggregate (all scenarios with byz exclusions):')
        print(f'  median(median_t_byz) = {median(all_med):.1f} s   '
              f'(paper predicts {t_ind_paper:.0f} s)')
        print(f'  median(p95_t_byz)    = {median(all_p95):.1f} s')
    print(f'Prop 1 (false exclusion of honest): '
          f'{"FAIL -- at least one trial excluded an honest UAV" if any_honest_excluded else "PASS across all trials"}')


if __name__ == '__main__':
    raise SystemExit(main())
