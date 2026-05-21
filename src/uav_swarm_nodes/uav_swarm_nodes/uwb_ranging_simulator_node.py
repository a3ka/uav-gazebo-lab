"""Phase 0 utility node: simulate UWB ranging between two UAVs.

Subscribes to two NoisyPose streams, computes the true Euclidean
distance between the two reported positions, adds zero-mean Gaussian
noise with stddev=sigma_range, and publishes the noisy range as a
Float32 on /uwb/range_<id_a>_<id_b>.

Paper Section IV-D specifies sigma_range = 0.1 m for UWB factors in the
factor graph. Phase 0 uses the same default; bias and link-degradation
models live elsewhere.

Parameters:
  uav_id_a    (int)   default 0
  uav_id_b    (int)   default 1
  sigma_range (float) default 0.1     -- metres (paper IV-D default)
  publish_rate (float) default 10.0   -- Hz
"""

import math
import random
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

from uav_swarm_msgs.msg import NoisyPose


class UwbRangingSimulatorNode(Node):
    def __init__(self) -> None:
        super().__init__('uwb_ranging_simulator_node')

        self.declare_parameter('uav_id_a', 0)
        self.declare_parameter('uav_id_b', 1)
        self.declare_parameter('sigma_range', 0.1)
        self.declare_parameter('publish_rate', 10.0)

        self.id_a = int(self.get_parameter('uav_id_a').value)
        self.id_b = int(self.get_parameter('uav_id_b').value)
        self.sigma_range = float(self.get_parameter('sigma_range').value)
        self.rate = float(self.get_parameter('publish_rate').value)

        self.pose_a = None
        self.pose_b = None

        self.sub_a = self.create_subscription(
            NoisyPose, f'/uav{self.id_a}/noisy_pose', self._cb_a, 10
        )
        self.sub_b = self.create_subscription(
            NoisyPose, f'/uav{self.id_b}/noisy_pose', self._cb_b, 10
        )
        topic = f'/uwb/range_{self.id_a}_{self.id_b}'
        self.pub = self.create_publisher(Float32, topic, 10)

        self.timer = self.create_timer(1.0 / self.rate, self._tick)
        self.get_logger().info(
            f'uwb_ranging_simulator: pair=({self.id_a},{self.id_b}) '
            f'sigma_range={self.sigma_range}m rate={self.rate}Hz topic={topic}'
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
        noisy = true_d + random.gauss(0.0, self.sigma_range)
        msg = Float32()
        msg.data = float(noisy)
        self.pub.publish(msg)


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
