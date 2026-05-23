"""Phase 0/3 utility node: simulate UWB ranging between two UAVs.

Subscribes to two NoisyPose streams, computes the true Euclidean
distance, adds zero-mean Gaussian noise with stddev=sigma_range, and
publishes both:
  - Float32 on /uwb/range_<id_a>_<id_b>   (Phase 0 legacy, kept for smoke)
  - UwbRangeMeasurement on /uwb/range     (Phase 3 typed bus consumed by
                                           factor_graph_node)

Paper Section IV-D specifies sigma_range = 0.1 m for UWB factors in the
factor graph. Phase 0 uses the same default; bias and link-degradation
models live elsewhere.

Parameters:
  uav_id_a     (int)   default 0
  uav_id_b     (int)   default 1
  sigma_range  (float) default 0.1   -- metres (paper IV-D default)
  publish_rate (float) default 10.0  -- Hz
  emit_typed   (bool)  default true  -- publish UwbRangeMeasurement on /uwb/range
"""

import math
import random
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

from uav_swarm_msgs.msg import NoisyPose, UwbRangeMeasurement


class UwbRangingSimulatorNode(Node):
    def __init__(self, node_name: str = 'uwb_ranging_simulator_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('uav_id_a', 0)
        self.declare_parameter('uav_id_b', 1)
        self.declare_parameter('sigma_range', 0.1)
        self.declare_parameter('publish_rate', 10.0)
        self.declare_parameter('emit_typed', True)
        self.declare_parameter('seed', 0)

        self.id_a = int(self.get_parameter('uav_id_a').value)
        self.id_b = int(self.get_parameter('uav_id_b').value)
        self.sigma_range = float(self.get_parameter('sigma_range').value)
        self.rate = float(self.get_parameter('publish_rate').value)
        self.emit_typed = bool(self.get_parameter('emit_typed').value)
        seed = int(self.get_parameter('seed').value)
        # Seed=0 -> non-deterministic. Phase 3 batch sweep sets a per-pair
        # seed so trials are reproducible.
        self.rng = random.Random(seed) if seed else random.Random()

        self.pose_a = None
        self.pose_b = None

        self.sub_a = self.create_subscription(
            NoisyPose, f'/uav{self.id_a}/noisy_pose', self._cb_a, 10
        )
        self.sub_b = self.create_subscription(
            NoisyPose, f'/uav{self.id_b}/noisy_pose', self._cb_b, 10
        )
        legacy_topic = f'/uwb/range_{self.id_a}_{self.id_b}'
        self.pub_legacy = self.create_publisher(Float32, legacy_topic, 10)
        self.pub_typed = None
        if self.emit_typed:
            self.pub_typed = self.create_publisher(
                UwbRangeMeasurement, '/uwb/range', 50
            )

        self.timer = self.create_timer(1.0 / self.rate, self._tick)
        self.get_logger().info(
            f'uwb_ranging_simulator: pair=({self.id_a},{self.id_b}) '
            f'sigma_range={self.sigma_range}m rate={self.rate}Hz '
            f'legacy={legacy_topic} typed={"/uwb/range" if self.emit_typed else "off"}'
        )

    def _cb_a(self, msg: NoisyPose) -> None:
        self.pose_a = msg

    def _cb_b(self, msg: NoisyPose) -> None:
        self.pose_b = msg

    def _tick(self) -> None:
        if self.pose_a is None or self.pose_b is None:
            return
        dx = self.pose_a.position.x - self.pose_b.position.x
        dy = self.pose_a.position.y - self.pose_b.position.y
        dz = self.pose_a.position.z - self.pose_b.position.z
        true_d = math.sqrt(dx * dx + dy * dy + dz * dz)
        noisy = true_d + self.rng.gauss(0.0, self.sigma_range)

        legacy = Float32()
        legacy.data = float(noisy)
        self.pub_legacy.publish(legacy)

        if self.pub_typed is not None:
            typed = UwbRangeMeasurement()
            typed.timestamp = int(time.time() * 1_000_000)
            typed.sender_id = self.id_a
            typed.receiver_id = self.id_b
            typed.range_m = float(noisy)
            typed.sigma_m = float(self.sigma_range)
            self.pub_typed.publish(typed)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UwbRangingSimulatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
