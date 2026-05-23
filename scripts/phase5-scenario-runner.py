#!/usr/bin/env python3
"""Phase 5 task 5.3 — single-trial GNSS spoofing scenario runner.

One trial:
  1. Generates a Poisson UAV layout inside region_size_m x region_size_m
     (N=n_uavs, seed-controlled).
  2. Spawns N PositionBroadcasterNode (single-process, parameter
     overrides like Phase 3) + UwbRangingSimulatorNode per
     in-range pair (r_comm) + ONE SpoofDetectorNode + a metrics
     collector subscribed to /spoof/alert.
  3. After t_steady_s, picks `n_spoofed` UAVs at random and applies
     spoof_offset (random direction, magnitude `spoof_offset_m`).
  4. Observes for t_observe_s, collects alerts.
  5. Writes metrics JSON.

Pass per-trial criteria (paper Pillar 5):
  - All n_spoofed UAVs in `alerted_ids`  (detection rate 100%)
  - No honest UAV in `alerted_ids`        (false positive = 0)
  - For each victim: `t_first_alert - t_inject_unix` < t_pass_budget_s
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter

from uav_swarm_msgs.msg import SpoofAlert
from uav_swarm_nodes.multi_uwb_simulator_node import MultiUwbSimulatorNode
from uav_swarm_nodes.position_broadcaster_node import PositionBroadcasterNode
from uav_swarm_nodes.spoof_detector_node import SpoofDetectorNode


def _gen_layout(
    n: int, region_m: float, altitude_m: float, seed: int
) -> list[dict]:
    rng = random.Random(seed)
    uavs = []
    for i in range(n):
        uavs.append({
            'id': i,
            'position': [
                round(rng.uniform(0.0, region_m), 3),
                round(rng.uniform(0.0, region_m), 3),
                float(altitude_m),
            ],
        })
    return uavs


def _edges(uavs: list[dict], r_comm: float) -> list[tuple[int, int]]:
    es: list[tuple[int, int]] = []
    for i, a in enumerate(uavs):
        for b in uavs[i + 1:]:
            dx = a['position'][0] - b['position'][0]
            dy = a['position'][1] - b['position'][1]
            dz = a['position'][2] - b['position'][2]
            if math.sqrt(dx * dx + dy * dy + dz * dz) <= r_comm:
                es.append((a['id'], b['id']))
    return es


class AlertCollector(Node):
    def __init__(self) -> None:
        super().__init__('phase5_alert_collector')
        # (t_relative, suspect_uav_id, max_residual)
        self.alerts: list[tuple[float, int, float]] = []
        self._t0 = time.monotonic()
        self._collecting = False
        self.create_subscription(SpoofAlert, '/spoof/alert', self._on_alert, 50)

    def start_collecting(self) -> None:
        self._collecting = True
        self._t0 = time.monotonic()

    def _on_alert(self, msg: SpoofAlert) -> None:
        if not self._collecting:
            return
        self.alerts.append((
            time.monotonic() - self._t0,
            int(msg.suspect_uav_id),
            float(msg.max_residual_m),
        ))


def _params(d: dict[str, Any]) -> list[Parameter]:
    return [Parameter(k, value=v) for k, v in d.items()]


def run_trial(
    *, n_uavs: int, n_spoofed: int, region_m: float, altitude_m: float,
    sigma_gnss_m: float, sigma_uwb_m: float, r_comm_m: float,
    spoof_offset_m: float, t_steady_s: float, t_observe_s: float,
    t_spoof_m: float, m_suspect: int, window_s: float, tick_rate_hz: float,
    cooldown_s: float, seed: int, t_pass_budget_s: float,
) -> dict[str, Any]:
    rng = random.Random(seed)
    uavs = _gen_layout(n_uavs, region_m, altitude_m, seed)
    edges = _edges(uavs, r_comm_m)
    spoof_ids = sorted(rng.sample(range(n_uavs), n_spoofed))

    rclpy.init()
    nodes: list[Node] = []
    pb_nodes: dict[int, PositionBroadcasterNode] = {}
    for u in uavs:
        x, y, z = u['position']
        pb = PositionBroadcasterNode(
            node_name=f'pb_u{u["id"]}',
            parameter_overrides=_params({
                'uav_id': int(u['id']),
                'radius': 0.0,
                'center': [float(x), float(y)],
                'altitude': float(z),
                'sigma_inject': float(sigma_gnss_m),
                'sigma_report': 50.0,
                'publish_rate': 10.0,
            }),
        )
        pb_nodes[u['id']] = pb
        nodes.append(pb)

    # Single multi-pair UWB sim. Phase 3/5 originally used one
    # UwbRangingSimulatorNode per pair, but at N=50 (346 edges) that
    # registers 346 DDS publishers on /uwb/range -- discovery &
    # heartbeat overhead drowned the central spoof_detector_node,
    # losing >95% of messages. MultiUwbSimulatorNode is one node, one
    # publisher, handles all pairs in a single tick. Publish rate
    # 2 Hz: Phase 5 cross-verification needs only a few samples per
    # pair within the 2-s detection window.
    uwb_publish_rate = 2.0
    flat_pairs: list[int] = []
    for a, b in edges:
        flat_pairs.append(int(a))
        flat_pairs.append(int(b))
    nodes.append(MultiUwbSimulatorNode(
        parameter_overrides=_params({
            'pair_list': flat_pairs,
            'sigma_range': float(sigma_uwb_m),
            'publish_rate': float(uwb_publish_rate),
            'seed': seed * 100_000 + 1,
        }),
    ))

    nodes.append(SpoofDetectorNode(
        parameter_overrides=_params({
            'known_uav_ids': [int(u['id']) for u in uavs],
            't_spoof_m': float(t_spoof_m),
            'm_suspect': int(m_suspect),
            'window_s': float(window_s),
            'tick_rate_hz': float(tick_rate_hz),
            'cooldown_s': float(cooldown_s),
        }),
    ))

    collector = AlertCollector()

    exe = MultiThreadedExecutor()
    for n in nodes: exe.add_node(n)
    exe.add_node(collector)

    stop = threading.Event()
    def _spin():
        while not stop.is_set():
            exe.spin_once(timeout_sec=0.1)
    t = threading.Thread(target=_spin, daemon=True)
    t.start()

    t_trial_start = time.monotonic()
    time.sleep(t_steady_s)
    collector.start_collecting()
    t_inject_rel = time.monotonic() - collector._t0

    # Spoof injection: random unit direction (XY only), magnitude
    # spoof_offset_m. Different direction per victim so the residuals
    # have varied geometry.
    spoof_details: dict[int, list[float]] = {}
    for vid in spoof_ids:
        theta = rng.uniform(0.0, 2 * math.pi)
        offset = [
            float(spoof_offset_m * math.cos(theta)),
            float(spoof_offset_m * math.sin(theta)),
            0.0,
        ]
        pb_nodes[vid].set_parameters([
            Parameter('spoof_offset', value=offset),
        ])
        spoof_details[vid] = offset

    time.sleep(t_observe_s)
    stop.set()
    t.join(timeout=2.0)

    alerts = list(collector.alerts)

    for n in nodes:
        exe.remove_node(n); n.destroy_node()
    exe.remove_node(collector); collector.destroy_node()
    exe.shutdown()
    rclpy.shutdown()

    # Per-victim t_detect = first alert after injection
    per_victim: list[dict] = []
    for vid in spoof_ids:
        first = next((a for a in alerts if a[1] == vid and a[0] >= t_inject_rel),
                     None)
        if first is None:
            per_victim.append({
                'victim_id': vid, 'spoof_offset': spoof_details[vid],
                't_detect_s': None, 'detected': False,
            })
        else:
            per_victim.append({
                'victim_id': vid, 'spoof_offset': spoof_details[vid],
                't_detect_s': round(first[0] - t_inject_rel, 4),
                'detected': True,
            })

    alerted_ids = sorted({a[1] for a in alerts if a[0] >= t_inject_rel})
    false_pos = sorted(set(alerted_ids) - set(spoof_ids))
    n_detected = sum(1 for r in per_victim if r['detected'])
    valid_t = [r['t_detect_s'] for r in per_victim if r['t_detect_s'] is not None]
    in_budget = sum(1 for t_ in valid_t if t_ < t_pass_budget_s)
    return {
        'seed': seed,
        'n_uavs': n_uavs,
        'n_spoofed': n_spoofed,
        'region_m': region_m,
        'spoof_offset_m': spoof_offset_m,
        'r_comm_m': r_comm_m,
        't_spoof_m': t_spoof_m,
        'm_suspect': m_suspect,
        't_steady_s': t_steady_s,
        't_observe_s': t_observe_s,
        't_pass_budget_s': t_pass_budget_s,
        'n_edges': len(edges),
        'spoofed_ids': spoof_ids,
        'per_victim': per_victim,
        'alerted_ids': alerted_ids,
        'false_positives': false_pos,
        'n_detected': n_detected,
        'n_total_spoofed': n_spoofed,
        'detection_rate': round(n_detected / max(n_spoofed, 1), 4),
        'n_false_pos': len(false_pos),
        'pass_all_in_budget': (
            n_detected == n_spoofed and not false_pos
            and in_budget == n_spoofed
        ),
        't_detect_median_s': (
            round(sorted(valid_t)[len(valid_t) // 2], 4) if valid_t else None
        ),
        't_detect_max_s': round(max(valid_t), 4) if valid_t else None,
        'wall_time_s': round(time.monotonic() - t_trial_start, 2),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--n-uavs', type=int, default=50)
    p.add_argument('--n-spoofed', type=int, default=5)
    p.add_argument('--region-m', type=float, default=300.0)
    p.add_argument('--altitude-m', type=float, default=50.0)
    p.add_argument('--sigma-gnss-m', type=float, default=1.0)
    p.add_argument('--sigma-uwb-m', type=float, default=0.1)
    p.add_argument('--r-comm-m', type=float, default=100.0)
    p.add_argument('--spoof-offset-m', type=float, default=120.0)
    p.add_argument('--t-steady-s', type=float, default=4.0)
    p.add_argument('--t-observe-s', type=float, default=10.0)
    p.add_argument('--t-spoof-m', type=float, default=20.0)
    p.add_argument('--m-suspect', type=int, default=3)
    p.add_argument('--window-s', type=float, default=4.0)
    p.add_argument('--tick-rate-hz', type=float, default=5.0)
    p.add_argument('--cooldown-s', type=float, default=1.0)
    p.add_argument('--t-pass-budget-s', type=float, default=5.0)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--out', required=True)
    p.add_argument('--quiet', action='store_true')
    args = p.parse_args()

    metrics = run_trial(
        n_uavs=args.n_uavs, n_spoofed=args.n_spoofed,
        region_m=args.region_m, altitude_m=args.altitude_m,
        sigma_gnss_m=args.sigma_gnss_m, sigma_uwb_m=args.sigma_uwb_m,
        r_comm_m=args.r_comm_m, spoof_offset_m=args.spoof_offset_m,
        t_steady_s=args.t_steady_s, t_observe_s=args.t_observe_s,
        t_spoof_m=args.t_spoof_m, m_suspect=args.m_suspect,
        window_s=args.window_s, tick_rate_hz=args.tick_rate_hz,
        cooldown_s=args.cooldown_s, seed=args.seed,
        t_pass_budget_s=args.t_pass_budget_s,
    )
    Path(args.out).write_text(json.dumps(metrics, indent=2))
    if not args.quiet:
        print(f'[runner] detected={metrics["n_detected"]}/{metrics["n_total_spoofed"]} '
              f'false_pos={metrics["n_false_pos"]} '
              f'median_t={metrics["t_detect_median_s"]}s '
              f'pass={metrics["pass_all_in_budget"]} -> {args.out}', flush=True)
    return 0 if metrics['pass_all_in_budget'] else 1


if __name__ == '__main__':
    sys.exit(main())
