"""Combined multi-pair UWB ranging simulator.

Phase 5 needed a single rclpy node that handles N(N-1)/2 UWB pairs
internally with ONE /uwb/range publisher, instead of 346 separate
UwbRangingSimulatorNode instances each with their own publisher. With
346 publishers on a single topic the DDS layer ran into discovery /
heartbeat overhead and >95% of messages were lost at the central
spoof_detector_node side. One publisher resolves that.

Parameters:
  pair_list           int[]   default []        flattened [a0,b0,a1,b1,...]
                                                pair ids (must be even length)
  sigma_range         float   default 0.1       per-pair UWB noise (m)
  publish_rate        float   default 2.0       per-pair publish rate (Hz)
  seed                int     default 0         0 -> nondeterministic
  ground_truth_topic_prefix  str  default `/uav`
                                                resolves to
                                                `<prefix><id>/ground_truth`

The node subscribes to each unique UAV's /uav<i>/ground_truth, caches
the latest pose, and at each tick emits one UwbRangeMeasurement per
pair on /uwb/range.
"""
from __future__ import annotations

import math
import random
import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import NoisyPose, UwbRangeMeasurement


class MultiUwbSimulatorNode(Node):
    def __init__(self, node_name: str = 'multi_uwb_simulator_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('pair_list', [0, 1])
        self.declare_parameter('sigma_range', 0.1)
        self.declare_parameter('publish_rate', 2.0)
        self.declare_parameter('seed', 0)
        self.declare_parameter('ground_truth_topic_prefix', '/uav')

        flat = [int(x) for x in self.get_parameter('pair_list').value]
        if len(flat) % 2 != 0:
            raise ValueError('pair_list must have even length (a0,b0,a1,b1,...)')
        self.pairs: list[tuple[int, int]] = [
            (flat[i], flat[i + 1]) for i in range(0, len(flat), 2)
        ]
        self.sigma_range = float(self.get_parameter('sigma_range').value)
        self.rate = float(self.get_parameter('publish_rate').value)
        seed = int(self.get_parameter('seed').value)
        self.rng = random.Random(seed) if seed else random.Random()
        self.prefix = str(self.get_parameter('ground_truth_topic_prefix').value)

        uav_ids = sorted({u for pair in self.pairs for u in pair})
        self.poses: dict[int, tuple[float, float, float]] = {}
        for uid in uav_ids:
            self.create_subscription(
                NoisyPose, f'{self.prefix}{uid}/ground_truth',
                self._make_cb(uid), 10
            )
        # Large publisher queue depth to absorb the per-tick burst
        # (one publish per pair, 300+ pairs at N=50).
        self.pub = self.create_publisher(UwbRangeMeasurement, '/uwb/range', 2000)
        self.timer = self.create_timer(1.0 / self.rate, self._tick)
        self.get_logger().info(
            f'multi_uwb_simulator: n_pairs={len(self.pairs)} '
            f'n_uavs={len(uav_ids)} sigma={self.sigma_range} rate={self.rate}Hz'
        )

    def _make_cb(self, uid: int):
        def _cb(msg: NoisyPose) -> None:
            self.poses[uid] = (msg.position.x, msg.position.y, msg.position.z)
        return _cb

    def _tick(self) -> None:
        ts = int(time.time() * 1_000_000)
        for a, b in self.pairs:
            if a not in self.poses or b not in self.poses:
                continue
            pa = self.poses[a]; pb = self.poses[b]
            dx, dy, dz = pa[0] - pb[0], pa[1] - pb[1], pa[2] - pb[2]
            true_d = math.sqrt(dx * dx + dy * dy + dz * dz)
            noisy = true_d + self.rng.gauss(0.0, self.sigma_range)
            msg = UwbRangeMeasurement()
            msg.timestamp = ts
            msg.sender_id = int(a)
            msg.receiver_id = int(b)
            msg.range_m = float(noisy)
            msg.sigma_m = float(self.sigma_range)
            self.pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MultiUwbSimulatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
