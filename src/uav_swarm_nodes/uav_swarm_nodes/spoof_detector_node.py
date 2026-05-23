"""Phase 5 GNSS spoofing detector node (paper Pillar 5).

ONE central node (not per-UAV) that:
  1. Subscribes to /uav<i>/noisy_pose for every i in known_uav_ids
     (treats this as the GNSS-reported position).
  2. Subscribes to /uwb/range (typed UwbRangeMeasurement, Phase 3 reuse).
  3. For each UWB range msg with (sender, receiver, range_m):
       predicted = ||reported_pose[sender] - reported_pose[receiver]||
       residual  = |range_m - predicted|
     If residual > T_spoof, both endpoints get a "suspicious pair" tick
     against them in a sliding window.
  4. Periodic tick (default 1 Hz): for each UAV i whose suspicious-pair
     count >= M_suspect within the last `window_s`, publish SpoofAlert
     on /spoof/alert.

Single central detector instead of per-UAV: simpler bookkeeping, full
visibility into all peer pairs, fits the "trusted ground station" or
"M-of-N distributed detector" abstraction. Phase 7 integration will
shard this across N detectors to validate Byzantine-tolerance of the
detection layer itself.

Parameters:
  known_uav_ids        int[]   default []   -- must enumerate every UAV
                                              we should subscribe to
  t_spoof_m            float   default 20.0 -- residual threshold (m)
  m_suspect            int     default 3    -- min suspicious peer pairs
                                              to declare a UAV suspect
  window_s             float   default 2.0  -- sliding window length
  tick_rate_hz         float   default 5.0  -- alert-evaluation tick
  cooldown_s           float   default 1.0  -- after firing an alert,
                                              don't re-alert same UAV
                                              for this long
"""
from __future__ import annotations

import math
import time
from collections import deque

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import NoisyPose, SpoofAlert, UwbRangeMeasurement


class SpoofDetectorNode(Node):
    def __init__(self, node_name: str = 'spoof_detector_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('known_uav_ids', [0])
        self.declare_parameter('t_spoof_m', 20.0)
        self.declare_parameter('m_suspect', 3)
        self.declare_parameter('window_s', 2.0)
        self.declare_parameter('tick_rate_hz', 5.0)
        self.declare_parameter('cooldown_s', 1.0)

        self.known = [int(x) for x in self.get_parameter('known_uav_ids').value]
        self.t_spoof = float(self.get_parameter('t_spoof_m').value)
        self.m_suspect = int(self.get_parameter('m_suspect').value)
        self.window_s = float(self.get_parameter('window_s').value)
        tick_rate = float(self.get_parameter('tick_rate_hz').value)
        self.cooldown = float(self.get_parameter('cooldown_s').value)

        # Latest reported (GNSS) position per UAV
        self.reported: dict[int, tuple[float, float, float]] = {}
        # Sliding window per UAV: deque[(t, peer_id, residual)]
        self.suspect_events: dict[int, deque] = {i: deque() for i in self.known}
        # Cooldown bookkeeping
        self.last_alert_t: dict[int, float] = {}

        for uid in self.known:
            self.create_subscription(
                NoisyPose, f'/uav{uid}/noisy_pose', self._on_pose, 20
            )
        # Large QoS depth: at N=50 the multi-pair UWB simulator bursts
        # ~300+ msgs per 0.5s tick, and the default depth=100 dropped
        # most of them before our callback could drain.
        self.create_subscription(
            UwbRangeMeasurement, '/uwb/range', self._on_range, 2000
        )
        self.pub_alert = self.create_publisher(SpoofAlert, '/spoof/alert', 50)
        self.create_timer(1.0 / tick_rate, self._tick)

        self.get_logger().info(
            f'spoof_detector_node: n_uavs={len(self.known)} '
            f'T_spoof={self.t_spoof}m M_suspect={self.m_suspect} '
            f'window={self.window_s}s tick={tick_rate}Hz cooldown={self.cooldown}s'
        )

    def _on_pose(self, msg: NoisyPose) -> None:
        self.reported[int(msg.uav_id)] = (
            msg.position.x, msg.position.y, msg.position.z
        )

    def _on_range(self, msg: UwbRangeMeasurement) -> None:
        a, b = int(msg.sender_id), int(msg.receiver_id)
        if a not in self.reported or b not in self.reported:
            return
        pa, pb = self.reported[a], self.reported[b]
        dx, dy, dz = pa[0] - pb[0], pa[1] - pb[1], pa[2] - pb[2]
        predicted = math.sqrt(dx * dx + dy * dy + dz * dz)
        residual = abs(float(msg.range_m) - predicted)
        if residual > self.t_spoof:
            t = time.monotonic()
            # Mark BOTH endpoints suspicious: we can't tell which one
            # is wrong from a single range alone. The accumulator decides
            # who is the consistent offender across many peer pairs.
            for victim, peer in ((a, b), (b, a)):
                if victim in self.suspect_events:
                    self.suspect_events[victim].append((t, peer, residual))

    def _tick(self) -> None:
        now = time.monotonic()
        cutoff = now - self.window_s
        # Trim sliding window per UAV
        for uid in self.known:
            q = self.suspect_events[uid]
            while q and q[0][0] < cutoff:
                q.popleft()

        # Build per-UAV {peer: max_residual_in_window} maps
        pair_events: dict[int, dict[int, float]] = {}
        for uid in self.known:
            d: dict[int, float] = {}
            for _, peer, res in self.suspect_events[uid]:
                if res > d.get(peer, 0.0):
                    d[peer] = res
            pair_events[uid] = d

        # Periodic diagnostic
        if int(now * 2) % 4 == 0:
            sizes = {u: len(d) for u, d in pair_events.items() if d}
            if sizes:
                self.get_logger().info(
                    f'tick: reported={len(self.reported)}/{len(self.known)} '
                    f'unique_peer_conflicts={sizes}'
                )

        # GREEDY PEELING: iteratively pick the UAV with the most unique
        # conflicting peers above m_suspect, flag it, then REMOVE it
        # from every other UAV's peer-conflict set. A truly-spoofed UAV
        # conflicts with all its honest neighbours; those neighbours
        # conflict only with the spoofed UAV(s) they neighbour. Peeling
        # attributes the conflict to the actually-spoofed UAV, which
        # eliminates the false positives produced by the simpler
        # "flag-anyone-with->=M-conflicts" rule.
        peer_sets: dict[int, set[int]] = {
            u: set(d.keys()) for u, d in pair_events.items()
        }
        while peer_sets:
            best_uid, best_peers = max(
                peer_sets.items(), key=lambda x: len(x[1])
            )
            if len(best_peers) < self.m_suspect:
                break
            del peer_sets[best_uid]
            if now - self.last_alert_t.get(best_uid, 0.0) < self.cooldown:
                continue
            self.last_alert_t[best_uid] = now
            max_res = max(pair_events[best_uid].values())
            alert = SpoofAlert()
            alert.timestamp = int(time.time() * 1_000_000)
            alert.suspect_uav_id = best_uid
            alert.n_suspicious_pairs = len(best_peers)
            alert.max_residual_m = float(max_res)
            self.pub_alert.publish(alert)
            self.get_logger().warning(
                f'SPOOF ALERT uav={best_uid}  n_pairs={len(best_peers)}  '
                f'max_residual={max_res:.1f}m'
            )
            # Peel: remove best_uid from peers' conflict sets
            for other in peer_sets:
                peer_sets[other].discard(best_uid)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SpoofDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
