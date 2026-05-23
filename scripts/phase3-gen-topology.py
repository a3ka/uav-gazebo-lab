#!/usr/bin/env python3
"""Phase 3 task 3.6 — multi-anchor topology generator.

Produces a single trial topology suitable for sigma_k(CEP vs hops) refit
runs. Topology = M anchors + a chain of relay followers + a test follower
placed at exactly k UWB hops from the anchor cluster.

Geometry (per trial):
  - M anchors uniformly arranged on a small circle of radius r_anchor
    centred at origin (default M=3, r_anchor=20 m -- mutually visible).
  - For k>=1: a chain of (k-1) relay followers + 1 test follower extends
    along a randomly-rotated direction. Each chain step has length
    `step_m`, and step_m < r_comm so adjacent UWB links hold while
    non-adjacent links are broken (chain hop count is exact).
  - For k=0: test follower IS a 4th anchor (TRN-only, no UWB hop).
  - All UAVs at altitude `altitude_m` (default 50 m).

The output JSON drives `phase3_scenario_runner` (task 3.7), which spawns
position_broadcaster_node + uwb_ranging_simulator_node + trn_anchor_node
+ factor_graph_node per UAV.

Pass --check to assert the produced topology has the expected BFS hop
count from any anchor to the test UAV (sanity check before scenario
launch).

CLI:
  ./phase3-gen-topology.py --k 3 --out topo.json --seed 42
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import deque
from typing import Iterable


def generate_topology(
    k: int,
    *,
    M: int = 3,
    r_anchor_m: float = 20.0,
    r_comm_m: float = 100.0,
    step_m: float = 80.0,
    altitude_m: float = 50.0,
    seed: int = 0,
) -> dict:
    """Build a single trial topology with the test follower at hop k.

    The test follower is always the LAST entry in uavs[] (id = M + k).
    """
    if step_m >= r_comm_m:
        raise ValueError(f'step_m={step_m} must be < r_comm_m={r_comm_m}')
    rng = random.Random(seed)
    uavs: list[dict] = []

    # M anchors on a small circle around origin
    for i in range(M):
        angle = 2 * math.pi * i / M
        x = r_anchor_m * math.cos(angle)
        y = r_anchor_m * math.sin(angle)
        uavs.append({
            'id': i,
            'role': 'anchor',
            'position': [round(x, 3), round(y, 3), float(altitude_m)],
            'hop_target': 0,
        })

    # Chain direction: random unit vector in XY
    theta = rng.uniform(0.0, 2 * math.pi)
    dx, dy = math.cos(theta), math.sin(theta)

    # For k>=1: place (k-1) relays + 1 test follower along the chain.
    # For k=0: the "test follower" is just a 4th anchor co-placed nearby.
    if k == 0:
        # Add a single extra anchor as the test target so we can still
        # measure CEP. Place it at a chain-step away from origin.
        uavs.append({
            'id': M,
            'role': 'anchor',
            'position': [
                round(step_m * dx, 3),
                round(step_m * dy, 3),
                float(altitude_m),
            ],
            'hop_target': 0,
        })
    else:
        for i in range(1, k + 1):
            x = step_m * i * dx
            y = step_m * i * dy
            role = 'follower'
            uavs.append({
                'id': M + i - 1,
                'role': role,
                'position': [round(x, 3), round(y, 3), float(altitude_m)],
                'hop_target': i,
            })

    # Compute UWB edges: any pair within r_comm
    edges = _compute_edges(uavs, r_comm_m)
    test_id = uavs[-1]['id']
    anchor_ids = [u['id'] for u in uavs if u['role'] == 'anchor']
    observed_hop = _bfs_min_hops(test_id, anchor_ids, edges, len(uavs))

    return {
        'k': k,
        'M': M,
        'r_anchor_m': r_anchor_m,
        'r_comm_m': r_comm_m,
        'step_m': step_m,
        'altitude_m': altitude_m,
        'seed': seed,
        'chain_direction': [round(dx, 4), round(dy, 4)],
        'uavs': uavs,
        'edges': edges,
        'test_uav_id': test_id,
        'observed_hop_to_anchor': observed_hop,
    }


def _compute_edges(uavs: list[dict], r_comm_m: float) -> list[list[int]]:
    edges: list[list[int]] = []
    for i, a in enumerate(uavs):
        for b in uavs[i + 1:]:
            dx = a['position'][0] - b['position'][0]
            dy = a['position'][1] - b['position'][1]
            dz = a['position'][2] - b['position'][2]
            if math.sqrt(dx * dx + dy * dy + dz * dz) <= r_comm_m:
                edges.append([a['id'], b['id']])
    return edges


def _bfs_min_hops(
    src: int, dsts: Iterable[int], edges: list[list[int]], n_nodes: int
) -> int:
    adj: dict[int, list[int]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    dst_set = set(dsts)
    if src in dst_set:
        return 0
    dist: dict[int, int] = {src: 0}
    q = deque([src])
    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            if v in dist:
                continue
            dist[v] = dist[u] + 1
            if v in dst_set:
                return dist[v]
            q.append(v)
    return -1  # unreachable


def _check(topo: dict) -> bool:
    expected = topo['k']
    observed = topo['observed_hop_to_anchor']
    ok = (observed == expected) or (expected == 0 and observed in (0,))
    print(
        f'[check] k_target={expected} '
        f'k_observed={observed} {"PASS" if ok else "FAIL"}'
    )
    return ok


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--k', type=int, required=True,
                   help='target hop distance for the test follower')
    p.add_argument('--M', type=int, default=3, help='number of anchors')
    p.add_argument('--r-anchor-m', type=float, default=20.0,
                   help='radius of anchor cluster')
    p.add_argument('--r-comm-m', type=float, default=100.0,
                   help='UWB communication range')
    p.add_argument('--step-m', type=float, default=80.0,
                   help='chain step length (must be < r-comm-m)')
    p.add_argument('--altitude-m', type=float, default=50.0)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--out', type=str, default='-',
                   help='output JSON path (use - for stdout)')
    p.add_argument('--check', action='store_true',
                   help='assert observed hop equals k and exit non-zero on mismatch')
    return p


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    topo = generate_topology(
        k=args.k, M=args.M, r_anchor_m=args.r_anchor_m,
        r_comm_m=args.r_comm_m, step_m=args.step_m,
        altitude_m=args.altitude_m, seed=args.seed,
    )
    out = json.dumps(topo, indent=2)
    if args.out == '-':
        print(out)
    else:
        with open(args.out, 'w') as f:
            f.write(out + '\n')
        print(f'wrote {args.out}  uavs={len(topo["uavs"])} edges={len(topo["edges"])}')
    if args.check:
        return 0 if _check(topo) else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
