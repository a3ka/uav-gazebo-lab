#!/usr/bin/env python3
"""Phase 3 task 3.7 — single-trial scenario runner.

Read a topology JSON (from phase3-gen-topology.py), spawn ALL needed
ROS2 nodes in a single rclpy process (faster + cleaner than subprocess
per node × per trial), run for warmup_s + trial_s seconds, collect the
test follower's EstimatedPose stream, compute radial error vs. ground
truth, and write metrics.json.

Single-process design rationale: a hop=5 trial spawns ~30 nodes; the
batch sweep runs 200 trials × 5 k-values = 1000 trials. Subprocess
spawn at ~1-2 s each would dominate runtime. rclpy supports
parameter_overrides via NodeOptions, so we can reuse the existing node
classes with custom params — provided each class accepts **kwargs in
its constructor (patched in this commit).

Inputs:
  --topology     JSON path
  --warmup-s     seconds to let iSAM2 + UWB converge (default 5)
  --trial-s      seconds of estimate collection (default 30)
  --sigma-uwb-m  UWB measurement stddev (default 0.1, paper IV-D)
  --sigma-trn-m  TRN absolute-fix stddev (default 5.0, paper IV-D)
  --trn-period-s TRN broadcast period (default 10.0, paper IV-D)
  --out          metrics JSON path

Output JSON:
  topology_seed, k, test_uav_id, ground_truth, warmup_s, trial_s,
  n_samples, cep_50, cep_95, mean_err, std_err, raw_errors[]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import threading
import time
from typing import Any

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter

from uav_swarm_msgs.msg import EstimatedPose
from uav_swarm_nodes.factor_graph_node import FactorGraphNode
from uav_swarm_nodes.position_broadcaster_node import PositionBroadcasterNode
from uav_swarm_nodes.trn_anchor_node import TrnAnchorNode
from uav_swarm_nodes.uwb_ranging_simulator_node import UwbRangingSimulatorNode


class MetricsCollector(Node):
    """Subscribes to test follower's EstimatedPose and stores samples."""

    def __init__(self, test_uav_id: int) -> None:
        super().__init__('phase3_metrics_collector')
        self.test_uav_id = test_uav_id
        self.samples: list[tuple[float, float, float, float]] = []
        self._t0 = time.monotonic()
        self._collecting = False
        self.create_subscription(
            EstimatedPose, f'/estimate/u{test_uav_id}/pose', self._on_est, 50
        )

    def start_collecting(self) -> None:
        self._collecting = True
        self._t0 = time.monotonic()

    def _on_est(self, msg: EstimatedPose) -> None:
        if not self._collecting:
            return
        t = time.monotonic() - self._t0
        self.samples.append((t, msg.position.x, msg.position.y, msg.position.z))


def _params(d: dict[str, Any]) -> list[Parameter]:
    out: list[Parameter] = []
    for k, v in d.items():
        out.append(Parameter(k, value=v))
    return out


def build_nodes(
    topo: dict, *, sigma_uwb_m: float, sigma_trn_m: float, trn_period_s: float
) -> tuple[list[Node], MetricsCollector]:
    nodes: list[Node] = []

    # Position broadcasters -- one per UAV, STATIC (radius=0)
    for u in topo['uavs']:
        x, y, z = u['position']
        nodes.append(PositionBroadcasterNode(
            node_name=f'pb_u{u["id"]}',
            parameter_overrides=_params({
                'uav_id': int(u['id']),
                'radius': 0.0,
                'center': [float(x), float(y)],
                'altitude': float(z),
                'sigma_inject': 0.0,
                'sigma_report': 50.0,
                'publish_rate': 10.0,
            }),
        ))

    # TRN anchor nodes -- one per anchor
    for u in topo['uavs']:
        if u['role'] != 'anchor':
            continue
        x, y, z = u['position']
        nodes.append(TrnAnchorNode(
            node_name=f'trn_u{u["id"]}',
            parameter_overrides=_params({
                'uav_id': int(u['id']),
                'initial_position': [float(x), float(y), float(z)],
                'position_topic': f'/uav{u["id"]}/noisy_pose',
                'trn_period_s': float(trn_period_s),
                'sigma_trn_m': float(sigma_trn_m),
                'seed': int(topo.get('seed', 0)) * 1000 + int(u['id']),
            }),
        ))

    # UWB ranging simulators -- one per edge
    edge_seed_base = int(topo.get('seed', 0)) * 100_000
    for i, (a, b) in enumerate(topo['edges']):
        nodes.append(UwbRangingSimulatorNode(
            node_name=f'uwb_{a}_{b}',
            parameter_overrides=_params({
                'uav_id_a': int(a),
                'uav_id_b': int(b),
                'sigma_range': float(sigma_uwb_m),
                'publish_rate': 10.0,
                'emit_typed': True,
                'seed': edge_seed_base + i + 1,
            }),
        ))

    # Follower init = truth + N(0, sigma_init_m). Mocks IMU pre-
    # integration in a real deployment: short-duration flight gives a
    # rough position estimate within a few metres of truth, NOT a
    # blind (0,0,50) guess. Without this, every follower starts at
    # the anchor centroid -- iSAM2 then has to relinearize across
    # huge errors (~hundreds of metres at high hop counts) and gets
    # stuck in local minima or hits range-factor Jacobian singularities
    # when multiple keys co-locate. Phase 3 measures CEP propagation
    # *given a reasonable starting belief* -- that is the realistic
    # operating regime; Phase 6+ swaps the noise mock for true PX4
    # IMU pre-integration.
    init_rng = random.Random(int(topo.get('seed', 0)) * 7919 + 1)
    sigma_follower_init = 2.0
    # Anchors also get off-truth init -- without this, even wide
    # anchor_self_sigma left iSAM2's linearization point AT truth so
    # disabling TRN paradoxically IMPROVED CEP (Phase 7 ABL4-v2
    # artefact). 30m init noise (mimics "anchor took off, IMU drifted
    # before TRN lock") forces the system to actually USE TRN factors.
    sigma_anchor_init = 30.0

    # Factor graph -- one per UAV
    for u in topo['uavs']:
        x, y, z = u['position']
        is_anchor = u['role'] == 'anchor'
        s_init = sigma_anchor_init if is_anchor else sigma_follower_init
        init = [
            float(x) + init_rng.gauss(0.0, s_init),
            float(y) + init_rng.gauss(0.0, s_init),
            float(z),
        ]
        # anchor_self_sigma=50m (NOT 1m). Tight self-prior at truth was
        # a scaffold artifact: real-world anchors do NOT know their own
        # position -- they MUST rely on TRN to estimate it. With a 1m
        # self-prior at truth, the TRN factor was redundant and the
        # measured CEP collapsed to sub-meter values that are
        # physically impossible (Phase 7 ABL4 finding). 50m self-prior
        # means TRN noise actually propagates to the swarm estimate.
        nodes.append(FactorGraphNode(
            node_name=f'fg_u{u["id"]}',
            parameter_overrides=_params({
                'uav_id': int(u['id']),
                'is_anchor': bool(is_anchor),
                'initial_position': init,
                'update_rate_hz': 20.0,
                'sigma_base': 50.0,
                'reputation_eps': 0.01,
                'anchor_self_sigma': 50.0,
                'follower_self_sigma': 200.0,
            }),
        ))

    collector = MetricsCollector(int(topo['test_uav_id']))
    return nodes, collector


def compute_cep(
    samples: list[tuple[float, float, float, float]],
    gt: tuple[float, float, float],
) -> dict[str, Any]:
    if not samples:
        return {'n_samples': 0, 'cep_50': None, 'cep_95': None,
                'mean_err': None, 'std_err': None, 'raw_errors': []}
    errs: list[float] = []
    for _, x, y, z in samples:
        dx, dy, dz = x - gt[0], y - gt[1], z - gt[2]
        errs.append(math.sqrt(dx * dx + dy * dy + dz * dz))
    errs_sorted = sorted(errs)
    n = len(errs)
    cep_50 = errs_sorted[n // 2]
    cep_95 = errs_sorted[min(n - 1, int(0.95 * n))]
    return {
        'n_samples': n,
        'cep_50': round(cep_50, 4),
        'cep_95': round(cep_95, 4),
        'mean_err': round(statistics.fmean(errs), 4),
        'std_err': round(statistics.pstdev(errs) if n > 1 else 0.0, 4),
        'raw_errors': [round(e, 4) for e in errs],
    }


def run_trial(
    topo: dict, *, warmup_s: float, trial_s: float,
    sigma_uwb_m: float, sigma_trn_m: float, trn_period_s: float,
) -> dict[str, Any]:
    rclpy.init()
    nodes, collector = build_nodes(
        topo, sigma_uwb_m=sigma_uwb_m,
        sigma_trn_m=sigma_trn_m, trn_period_s=trn_period_s,
    )
    exe = MultiThreadedExecutor()
    for n in nodes:
        exe.add_node(n)
    exe.add_node(collector)

    stop = threading.Event()

    def _spin():
        while not stop.is_set():
            exe.spin_once(timeout_sec=0.1)

    t = threading.Thread(target=_spin, daemon=True)
    t.start()

    time.sleep(warmup_s)
    collector.start_collecting()
    time.sleep(trial_s)

    stop.set()
    t.join(timeout=2.0)

    # Snapshot samples before shutdown
    samples = list(collector.samples)
    gt = tuple(next(u['position'] for u in topo['uavs']
                    if u['id'] == topo['test_uav_id']))

    for n in nodes:
        exe.remove_node(n)
        n.destroy_node()
    exe.remove_node(collector)
    collector.destroy_node()
    exe.shutdown()
    rclpy.shutdown()

    metrics = compute_cep(samples, gt)
    metrics.update({
        'topology_seed': topo.get('seed'),
        'k': topo['k'],
        'M': topo['M'],
        'test_uav_id': topo['test_uav_id'],
        'observed_hop_to_anchor': topo['observed_hop_to_anchor'],
        'ground_truth': list(gt),
        'warmup_s': warmup_s,
        'trial_s': trial_s,
        'sigma_uwb_m': sigma_uwb_m,
        'sigma_trn_m': sigma_trn_m,
        'trn_period_s': trn_period_s,
        'n_uavs': len(topo['uavs']),
        'n_edges': len(topo['edges']),
    })
    return metrics


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--topology', required=True, help='topology JSON path')
    p.add_argument('--warmup-s', type=float, default=5.0)
    p.add_argument('--trial-s', type=float, default=30.0)
    p.add_argument('--sigma-uwb-m', type=float, default=0.1)
    p.add_argument('--sigma-trn-m', type=float, default=5.0)
    p.add_argument('--trn-period-s', type=float, default=10.0)
    p.add_argument('--out', required=True, help='metrics JSON path')
    p.add_argument('--quiet', action='store_true')
    return p


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    with open(args.topology) as f:
        topo = json.load(f)
    if not args.quiet:
        print(f'[runner] k={topo["k"]} uavs={len(topo["uavs"])} '
              f'edges={len(topo["edges"])} test={topo["test_uav_id"]} '
              f'warmup={args.warmup_s}s trial={args.trial_s}s', flush=True)
    metrics = run_trial(
        topo,
        warmup_s=args.warmup_s, trial_s=args.trial_s,
        sigma_uwb_m=args.sigma_uwb_m,
        sigma_trn_m=args.sigma_trn_m,
        trn_period_s=args.trn_period_s,
    )
    with open(args.out, 'w') as f:
        json.dump(metrics, f, indent=2)
    if not args.quiet:
        print(f'[runner] cep_50={metrics["cep_50"]} cep_95={metrics["cep_95"]} '
              f'n={metrics["n_samples"]} -> {args.out}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
