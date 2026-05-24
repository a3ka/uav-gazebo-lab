#!/usr/bin/env python3
"""Phase 6 task 6.5 — Tier B single-trial Python MC scenario runner.

Drives a single attrition-trial WITHOUT Gazebo/PX4:
  * N PositionBroadcasterNode (static; placeholders for IMU truth)
  * M AnchorNode + (N-M) FollowerNode (Phase 4 nodes reused)
  * MultiUwbSimulatorNode for all-pair UWB (Phase 5 reuse)
  * AttritionOrchestratorNode firing scheduled events
  * LoadMonitorNode writing the per-tick CSV
  * In-runner /attrition/event subscriber that:
      - destroys the victim node in-process (anchor or follower)
      - re-computes target_capacity = ceil(n_followers / surviving_M)
        and pushes it onto every surviving anchor via set_parameters()

Single-process design pulled from Phase 3 / Phase 5 — all rclpy nodes
spin via one MultiThreadedExecutor; subprocess-per-node would dominate
runtime at N=200.

CLI:
  scripts/phase6-tier-b-runner.py \\
      --n-uavs 20 --m-anchors 4 --attrition-yaml-style "30,0,anchor;60,1,anchor" \\
      --t-mission-s 120 --out workspaces/phase6-dev/m.json
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

from uav_swarm_msgs.msg import AttritionEvent
from uav_swarm_nodes.anchor_node import AnchorNode
from uav_swarm_nodes.attrition_orchestrator_node import AttritionOrchestratorNode
from uav_swarm_nodes.follower_node import FollowerNode
from uav_swarm_nodes.load_monitor_node import LoadMonitorNode
from uav_swarm_nodes.multi_uwb_simulator_node import MultiUwbSimulatorNode
from uav_swarm_nodes.position_broadcaster_node import PositionBroadcasterNode


def _params(d: dict[str, Any]) -> list[Parameter]:
    return [Parameter(k, value=v) for k, v in d.items()]


def _parse_profile(s: str) -> list[dict]:
    out: list[dict] = []
    for token in s.split(';'):
        token = token.strip()
        if not token:
            continue
        parts = token.split(',')
        if len(parts) != 3:
            raise ValueError(f'bad profile entry: {token!r} (expect t,id,role)')
        out.append({
            't_s': float(parts[0]),
            'victim_uav_id': int(parts[1]),
            'victim_role': parts[2].strip(),
        })
    return out


def _layout(n: int, region_m: float, altitude_m: float, seed: int) -> list[dict]:
    rng = random.Random(seed)
    return [{
        'id': i,
        'position': [
            round(rng.uniform(0.0, region_m), 3),
            round(rng.uniform(0.0, region_m), 3),
            float(altitude_m),
        ],
    } for i in range(n)]


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


class AttritionEnforcer(Node):
    """Subscribes to /attrition/event and enforces the kill in-process.

    Tier B kill semantics:
      - victim_role == 'anchor': destroy node; re-compute and push new
        target_capacity = ceil(n_followers_init / new_surviving_anchors)
        onto every surviving anchor via set_parameters
      - victim_role == 'follower': destroy node
    """

    def __init__(self, anchors: dict[int, AnchorNode],
                 followers: dict[int, FollowerNode],
                 executor: MultiThreadedExecutor,
                 n_followers_init: int) -> None:
        super().__init__('phase6_attrition_enforcer')
        self.anchors = anchors
        self.followers = followers
        self.executor = executor
        self.n_followers_init = n_followers_init
        self.events_handled: list[dict] = []
        self.create_subscription(
            AttritionEvent, '/attrition/event', self._on_event, 50
        )

    def _on_event(self, msg: AttritionEvent) -> None:
        vid = int(msg.victim_uav_id)
        role = str(msg.victim_role)
        if role == 'anchor' and vid in self.anchors:
            node = self.anchors.pop(vid)
            self.executor.remove_node(node)
            try: node.destroy_node()
            except Exception: pass
            # Re-balance target_capacity on survivors
            surviving = max(len(self.anchors), 1)
            new_cap = max(1, math.ceil(self.n_followers_init / surviving))
            for a in self.anchors.values():
                try:
                    a.set_parameters([Parameter('target_capacity', value=int(new_cap))])
                except Exception:
                    pass
                a.target_capacity = int(new_cap)
            self.get_logger().warning(
                f'killed anchor {vid}, surviving={surviving}, '
                f'new target_capacity={new_cap}'
            )
            self.events_handled.append({
                't_recv': time.monotonic(), 'victim_id': vid, 'role': role,
                'new_target_capacity': new_cap,
            })
        elif role == 'follower' and vid in self.followers:
            node = self.followers.pop(vid)
            self.executor.remove_node(node)
            try: node.destroy_node()
            except Exception: pass
            self.get_logger().warning(f'killed follower {vid}')
            self.events_handled.append({
                't_recv': time.monotonic(), 'victim_id': vid, 'role': role,
                'new_target_capacity': None,
            })


def run_trial(*, n_uavs: int, m_anchors: int, region_m: float,
              r_comm_m: float, altitude_m: float, sigma_uwb_m: float,
              profile: list[dict], t_mission_s: float, t_warmup_s: float,
              seed: int, csv_out: Path,
              t_timeout_s: float = 5.0,
              alpha_cap: float = 0.25) -> dict[str, Any]:
    n_followers = n_uavs - m_anchors
    uavs = _layout(n_uavs, region_m, altitude_m, seed)
    edges = _edges(uavs, r_comm_m)
    # First m_anchors are anchors, rest followers
    anchor_ids = [u['id'] for u in uavs[:m_anchors]]
    follower_ids = [u['id'] for u in uavs[m_anchors:]]
    initial_capacity = max(1, math.ceil(n_followers / max(m_anchors, 1)))
    # Assign each follower to an initial anchor round-robin
    init_anchor_of: dict[int, int] = {
        fid: anchor_ids[i % m_anchors] for i, fid in enumerate(follower_ids)
    }

    rclpy.init()
    # No PositionBroadcasterNode in Tier B -- followers + anchors do
    # not subscribe to /uav*/noisy_pose for the load-balancing protocol
    # (Phase 4 selection uses anchor position from DistilledState, not
    # UWB-derived poses). Spawning N=200 broadcasters @ 10Hz = 4000
    # msg/s of pure overhead that drowned the single-threaded rclpy
    # executor, causing DistilledState callbacks to lag past the 5-s
    # watchdog and spurious failover storms.
    pb_nodes: list[Node] = []

    # Phase 6 load-balancing does NOT use UWB. The follower's
    # offer-selection score (paper IV-F) uses alpha_prox/d where d is
    # computed from the follower's last_known_position and the offer's
    # advertised anchor position -- no UWB ranges enter the formula.
    # Spawning a MultiUwbSimulatorNode at N=200 would publish ~9950
    # pair ranges at 2Hz = 19900 msg/s -- pure overhead. Skipping.
    uwb_sim = None

    # Reduced DistilledState rate (10 Hz -> 5 Hz) for Tier B at scale.
    # 5-s watchdog still sees ~25 msgs per window -- plenty for failure
    # detection, half the executor pressure.
    anchor_publish_rate = 5.0
    anchors: dict[int, AnchorNode] = {}
    for u in uavs[:m_anchors]:
        x, y, z = u['position']
        anchors[u['id']] = AnchorNode(
            node_name=f'anchor_{u["id"]}',
            parameter_overrides=_params({
                'anchor_id': int(u['id']),
                'initial_position': [float(x), float(y), float(z)],
                'target_capacity': int(initial_capacity),
                'reputation': 0.8,
                'publish_rate': float(anchor_publish_rate),
            }),
        )

    followers: dict[int, FollowerNode] = {}
    for u in uavs[m_anchors:]:
        followers[u['id']] = FollowerNode(
            node_name=f'follower_{u["id"]}',
            parameter_overrides=_params({
                'follower_id': int(u['id']),
                'initial_anchor_id': int(init_anchor_of[u['id']]),
                'known_anchor_ids': [int(a) for a in anchor_ids],
                't_timeout': float(t_timeout_s),
                't_offer_window': 1.0,
                't_reject': 0.20,
                'alpha_cap': float(alpha_cap),
            }),
        )

    monitor = LoadMonitorNode(parameter_overrides=_params({
        'out_csv': str(csv_out),
        'flush_every_n': 25,
    }))

    orchestrator = AttritionOrchestratorNode(parameter_overrides=_params({
        'profile_json': json.dumps(profile),
        'trigger_label': 'scheduled',
        'n_anchors_init': int(m_anchors),
        'n_followers_init': int(n_followers),
        'tick_period_s': 0.1,
    }))

    exe = MultiThreadedExecutor()
    enforcer = AttritionEnforcer(anchors, followers, exe, n_followers)
    for n in pb_nodes: exe.add_node(n)
    if uwb_sim is not None:
        exe.add_node(uwb_sim)
    for a in list(anchors.values()): exe.add_node(a)
    for f in list(followers.values()): exe.add_node(f)
    exe.add_node(monitor)
    exe.add_node(orchestrator)
    exe.add_node(enforcer)

    stop = threading.Event()
    def _spin():
        while not stop.is_set():
            try: exe.spin_once(timeout_sec=0.1)
            except Exception: pass
    t = threading.Thread(target=_spin, daemon=True)
    t.start()

    t_start = time.monotonic()
    time.sleep(t_warmup_s)
    # orchestrator's internal t0 is from its own __init__; subtract any
    # warmup so scheduled events fire t_s seconds AFTER warmup ends.
    # (Simpler convention: events in profile are relative to warmup-end.)
    # We re-init orchestrator's t0 by setting an internal offset.
    orchestrator.t0 = time.monotonic()
    time.sleep(t_mission_s)
    stop.set()
    t.join(timeout=2.0)

    # Snapshot survivors before destroy
    surviving_anchor_ids = sorted(anchors.keys())
    surviving_follower_ids = sorted(followers.keys())
    n_events_handled = len(enforcer.events_handled)

    for n in pb_nodes:
        try: exe.remove_node(n); n.destroy_node()
        except Exception: pass
    teardown = [n for n in (uwb_sim, monitor, orchestrator, enforcer) if n is not None]
    for nd in teardown:
        try: exe.remove_node(nd); nd.destroy_node()
        except Exception: pass
    for a in list(anchors.values()):
        try: exe.remove_node(a); a.destroy_node()
        except Exception: pass
    for f in list(followers.values()):
        try: exe.remove_node(f); f.destroy_node()
        except Exception: pass
    exe.shutdown()
    rclpy.shutdown()

    return {
        'seed': seed, 'n_uavs': n_uavs, 'm_anchors': m_anchors,
        'n_followers': n_followers, 'n_edges': len(edges),
        'region_m': region_m, 'r_comm_m': r_comm_m,
        'initial_target_capacity': initial_capacity,
        'profile': profile, 't_mission_s': t_mission_s,
        't_warmup_s': t_warmup_s,
        'n_events_handled': n_events_handled,
        'n_events_scheduled': len(profile),
        'surviving_n_anchors': len(surviving_anchor_ids),
        'surviving_n_followers': len(surviving_follower_ids),
        'surviving_anchor_ids': surviving_anchor_ids,
        'csv_out': str(csv_out),
        'wall_time_s': round(time.monotonic() - t_start, 2),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--n-uavs', type=int, default=20)
    p.add_argument('--m-anchors', type=int, default=4)
    p.add_argument('--region-m', type=float, default=150.0)
    p.add_argument('--r-comm-m', type=float, default=100.0)
    p.add_argument('--altitude-m', type=float, default=50.0)
    p.add_argument('--sigma-uwb-m', type=float, default=0.1)
    p.add_argument('--profile', type=str, default='15,0,anchor;30,1,anchor',
                   help='semicolon-separated t_s,victim_id,victim_role')
    p.add_argument('--t-warmup-s', type=float, default=6.0)
    p.add_argument('--t-mission-s', type=float, default=60.0)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--out', required=True)
    p.add_argument('--csv-out', required=True)
    # Ablation knobs (Phase 7): t-timeout=10000 disables failover;
    # alpha-cap=0.0 disables load-balancing weight in selection.
    p.add_argument('--t-timeout-s', type=float, default=5.0)
    p.add_argument('--alpha-cap', type=float, default=0.25)
    args = p.parse_args()

    profile = _parse_profile(args.profile)
    metrics = run_trial(
        n_uavs=args.n_uavs, m_anchors=args.m_anchors,
        region_m=args.region_m, r_comm_m=args.r_comm_m,
        altitude_m=args.altitude_m, sigma_uwb_m=args.sigma_uwb_m,
        profile=profile, t_mission_s=args.t_mission_s,
        t_warmup_s=args.t_warmup_s, seed=args.seed,
        csv_out=Path(args.csv_out),
        t_timeout_s=args.t_timeout_s,
        alpha_cap=args.alpha_cap,
    )
    Path(args.out).write_text(json.dumps(metrics, indent=2))
    print(f'[tier-b] events={metrics["n_events_handled"]}/'
          f'{metrics["n_events_scheduled"]} '
          f'surviving_anchors={metrics["surviving_n_anchors"]}/{args.m_anchors} '
          f'wall={metrics["wall_time_s"]}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
