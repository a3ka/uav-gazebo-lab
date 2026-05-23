"""Phase 0 utility node: publish NoisyPose at a configurable rate.

For Phase 0 testing we use a synthetic ground truth (circular motion in
the local frame) and inject Gaussian noise of stddev=sigma_inject on
each axis. Phase 1+ will swap the synthetic source for a real
subscription to PX4 vehicle_local_position once px4_msgs is wired in.

Parameters:
  uav_id        (int)   default 0      -- identifier baked into NoisyPose.uav_id
  publish_rate  (float) default 10.0   -- Hz
  sigma_inject  (float) default 1.0    -- metres, stddev of injected noise
  sigma_report  (float) default 50.0   -- metres, what we put in NoisyPose.sigma
                                          (anchor expectation per paper IV-D,
                                          sigma_base; falls back to a fixed
                                          value for Phase 0 smoke)
  radius        (float) default 10.0   -- metres, circle radius for synthetic gt
                                          (set to 0 for a stationary point)
  altitude      (float) default 50.0   -- metres, fixed Z for synthetic gt
  center        (float[2]) default [0,0]  -- XY origin of the synthetic motion;
                                            with radius=0 this is the static
                                            ground-truth position. Phase 3 batch
                                            sweeps use radius=0 + center=[x,y].
"""

import math
import random
import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import NoisyPose


class PositionBroadcasterNode(Node):
    def __init__(self) -> None:
        super().__init__('position_broadcaster_node')

        self.declare_parameter('uav_id', 0)
        self.declare_parameter('publish_rate', 10.0)
        self.declare_parameter('sigma_inject', 1.0)
        self.declare_parameter('sigma_report', 50.0)
        self.declare_parameter('radius', 10.0)
        self.declare_parameter('altitude', 50.0)
        self.declare_parameter('center', [0.0, 0.0])

        self.uav_id = int(self.get_parameter('uav_id').value)
        self.rate = float(self.get_parameter('publish_rate').value)
        self.sigma_inject = float(self.get_parameter('sigma_inject').value)
        self.sigma_report = float(self.get_parameter('sigma_report').value)
        self.radius = float(self.get_parameter('radius').value)
        self.altitude = float(self.get_parameter('altitude').value)
        c = self.get_parameter('center').value
        self.center = (float(c[0]), float(c[1]))

        topic = f'/uav{self.uav_id}/noisy_pose'
        self.pub = self.create_publisher(NoisyPose, topic, 10)
        self.t0 = time.monotonic()
        self.timer = self.create_timer(1.0 / self.rate, self._tick)

        self.get_logger().info(
            f"position_broadcaster_node: uav_id={self.uav_id} rate={self.rate}Hz "
            f"sigma_inject={self.sigma_inject}m sigma_report={self.sigma_report}m "
            f"topic={topic}"
        )

    def _tick(self) -> None:
        t = time.monotonic() - self.t0
        # Synthetic circular ground truth around `center`; radius=0 -> static.
        x_gt = self.center[0] + self.radius * math.cos(t * 0.3)
        y_gt = self.center[1] + self.radius * math.sin(t * 0.3)
        z_gt = self.altitude

        msg = NoisyPose()
        msg.timestamp = int(time.time() * 1_000_000)
        msg.uav_id = self.uav_id
        msg.position.x = x_gt + random.gauss(0.0, self.sigma_inject)
        msg.position.y = y_gt + random.gauss(0.0, self.sigma_inject)
        msg.position.z = z_gt + random.gauss(0.0, self.sigma_inject)
        msg.sigma = self.sigma_report
        self.pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PositionBroadcasterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
