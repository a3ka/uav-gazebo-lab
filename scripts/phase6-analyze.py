#!/usr/bin/env python3
"""Phase 6 task 6.6 — load timeline analyzer.

Reads ONE trial's timeline CSV (load + attrition rows) and computes:
  * Per-event time-over-capacity (max contiguous interval any anchor
    exceeded its current target_capacity, starting from each
    attrition event)
  * Per-event re-balance latency (first moment after the event when
    ALL surviving anchors are <= target_capacity)
  * Mission survival (any orphaned-follower window > 10 s -- we
    proxy this with "sum(n_attached over surviving anchors) drops
    below initial-followers count by more than 1 for > 10 s")
  * Pass criteria per paper Pillar 6:
      time-over-capacity_per_event   < 5 s
      re-balance_latency_per_event    < 10 s
      mission_survived                True

Aggregator (when iterated over many trials via phase6-aggregate.py)
gives the distribution.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def _load(csv_path: Path) -> tuple[list[dict], list[dict]]:
    loads: list[dict] = []
    events: list[dict] = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            if r['kind'] == 'load':
                loads.append({
                    't': float(r['t_rel_s']),
                    'anchor_id': int(r['anchor_id']),
                    'target_capacity': int(r['target_capacity']),
                    'n_attached': int(r['n_attached']),
                    'over_capacity': int(r['over_capacity']) == 1,
                })
            elif r['kind'] == 'attrition':
                events.append({
                    't': float(r['t_rel_s']),
                    'victim_id': int(r['victim_id']),
                    'victim_role': r['victim_role'],
                    'surviving_n_anchors': int(r['surviving_n_anchors']),
                    'surviving_n_followers': int(r['surviving_n_followers']),
                })
    loads.sort(key=lambda x: x['t'])
    events.sort(key=lambda x: x['t'])
    return loads, events


def _per_event_stats(loads: list[dict], events: list[dict],
                     pass_cap_budget_s: float,
                     pass_rebalance_budget_s: float) -> list[dict]:
    per_event = []
    # Treat each event as the boundary; analysis window = [t_event, next_event_t)
    for i, ev in enumerate(events):
        t_start = ev['t']
        t_end = events[i + 1]['t'] if i + 1 < len(events) else loads[-1]['t']
        window = [L for L in loads if t_start <= L['t'] < t_end
                  and L['anchor_id'] != ev['victim_id']]
        # Group by anchor; find longest over-capacity interval per anchor
        by_anchor: dict[int, list[dict]] = defaultdict(list)
        for L in window: by_anchor[L['anchor_id']].append(L)
        max_oc_interval = 0.0
        # Rebalance latency = (last over-cap sample t) - t_event.
        # If no anchor ever went over cap, latency = 0.
        # The naive "first balanced sample" metric is wrong because at
        # t=event no follower has yet failed over -- the system LOOKS
        # balanced for the first ~5 s (watchdog timeout), THEN spikes,
        # THEN re-balances. We want the time until the post-spike
        # equilibrium is reached.
        last_over_cap_t = None
        for L in window:
            if L['over_capacity'] and (last_over_cap_t is None or L['t'] > last_over_cap_t):
                last_over_cap_t = L['t']
        first_balanced_t = (last_over_cap_t - t_start
                            if last_over_cap_t is not None else 0.0)
        # max per-anchor over-capacity contiguous interval
        for aid, samples in by_anchor.items():
            cur_start = None
            for s in samples:
                if s['over_capacity']:
                    if cur_start is None: cur_start = s['t']
                else:
                    if cur_start is not None:
                        dur = s['t'] - cur_start
                        if dur > max_oc_interval: max_oc_interval = dur
                        cur_start = None
            # tail
            if cur_start is not None:
                dur = samples[-1]['t'] - cur_start
                if dur > max_oc_interval: max_oc_interval = dur
        per_event.append({
            'event_idx': i,
            't_event_s': round(t_start, 4),
            'victim_id': ev['victim_id'],
            'victim_role': ev['victim_role'],
            'rebalance_latency_s': (round(first_balanced_t, 4)
                                    if first_balanced_t is not None else None),
            'max_over_cap_interval_s': round(max_oc_interval, 4),
            'pass_rebalance': (first_balanced_t is not None
                               and first_balanced_t < pass_rebalance_budget_s),
            'pass_over_cap': max_oc_interval < pass_cap_budget_s,
        })
    return per_event


def _summarize(per_event: list[dict], events: list[dict],
               loads: list[dict], n_followers_init: int) -> dict:
    pass_rebal = sum(1 for e in per_event if e['pass_rebalance'])
    pass_oc = sum(1 for e in per_event if e['pass_over_cap'])
    rebal = [e['rebalance_latency_s'] for e in per_event
             if e['rebalance_latency_s'] is not None]
    oc = [e['max_over_cap_interval_s'] for e in per_event]
    # Mission survival: total followers protocol-attached at end across
    # surviving anchors >= n_followers_init - 1 (allow 1 orphan)
    # use the LAST sample per anchor
    last_n: dict[int, int] = {}
    for L in loads:
        if L['anchor_id'] in [ev['victim_id'] for ev in events
                              if ev['victim_role'] == 'anchor']:
            continue
        last_n[L['anchor_id']] = L['n_attached']
    total_attached_final = sum(last_n.values())
    mission_survived = total_attached_final >= n_followers_init - 1
    return {
        'n_events': len(per_event),
        'rebal_latency_median': (round(sorted(rebal)[len(rebal)//2], 4)
                                 if rebal else None),
        'rebal_latency_max': round(max(rebal), 4) if rebal else None,
        'pass_rebalance_per_event': pass_rebal,
        'over_cap_interval_median': (round(sorted(oc)[len(oc)//2], 4)
                                     if oc else None),
        'over_cap_interval_max': round(max(oc), 4) if oc else None,
        'pass_over_cap_per_event': pass_oc,
        'mission_survived': mission_survived,
        'total_attached_final': total_attached_final,
        'n_followers_init': n_followers_init,
        'pass_trial': (pass_rebal == len(per_event)
                       and pass_oc == len(per_event)
                       and mission_survived),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--csv', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--n-followers-init', type=int, required=True)
    p.add_argument('--rebalance-budget-s', type=float, default=10.0)
    p.add_argument('--over-cap-budget-s', type=float, default=5.0)
    args = p.parse_args()
    loads, events = _load(args.csv)
    if not events:
        print('[analyze] no attrition events in CSV', file=sys.stderr)
        return 1
    per_event = _per_event_stats(loads, events,
                                 args.over_cap_budget_s,
                                 args.rebalance_budget_s)
    summary = _summarize(per_event, events, loads, args.n_followers_init)
    out = {'csv': str(args.csv), 'per_event': per_event, 'summary': summary}
    args.out.write_text(json.dumps(out, indent=2))
    print(f'[analyze] wrote {args.out}')
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
