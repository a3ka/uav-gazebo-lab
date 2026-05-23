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
  spoof_offset  (float[3]) default [0,0,0] -- ADDED to the published noisy_pose
                                            after noise injection. Used by
                                            Phase 5 to inject GNSS spoofing
                                            without touching ground truth.
                                            Set at runtime via `ros2 param set`.
"""

import math
import random
import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import NoisyPose


class PositionBroadcasterNode(Node):
    def __init__(self, node_name: str = 'position_broadcaster_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('uav_id', 0)
        self.declare_parameter('publish_rate', 10.0)
        self.declare_parameter('sigma_inject', 1.0)
        self.declare_parameter('sigma_report', 50.0)
        self.declare_parameter('radius', 10.0)
        self.declare_parameter('altitude', 50.0)
        self.declare_parameter('center', [0.0, 0.0])
        self.declare_parameter('spoof_offset', [0.0, 0.0, 0.0])

        self.uav_id = int(self.get_parameter('uav_id').value)
        self.rate = float(self.get_parameter('publish_rate').value)
        self.sigma_inject = float(self.get_parameter('sigma_inject').value)
        self.sigma_report = float(self.get_parameter('sigma_report').value)
        self.radius = float(self.get_parameter('radius').value)
        self.altitude = float(self.get_parameter('altitude').value)
        c = self.get_parameter('center').value
        self.center = (float(c[0]), float(c[1]))
        so = self.get_parameter('spoof_offset').value
        self.spoof_offset = [float(so[0]), float(so[1]), float(so[2])]
        # Runtime param update for spoof injection (`ros2 param set`)
        self.add_on_set_parameters_callback(self._on_param)

        topic = f'/uav{self.uav_id}/noisy_pose'
        self.pub = self.create_publisher(NoisyPose, topic, 10)
        # Separate clean ground-truth channel. UWB simulators must use
        # THIS topic for distance computation -- using noisy_pose would
        # let a GNSS spoof (spoof_offset) feed through to "measured"
        # UWB range, masking the spoof from any cross-verification
        # detector (Phase 5 Pillar 5).
        self.pub_gt = self.create_publisher(
            NoisyPose, f'/uav{self.uav_id}/ground_truth', 10
        )
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
        msg.position.x = x_gt + random.gauss(0.0, self.sigma_inject) + self.spoof_offset[0]
        msg.position.y = y_gt + random.gauss(0.0, self.sigma_inject) + self.spoof_offset[1]
        msg.position.z = z_gt + random.gauss(0.0, self.sigma_inject) + self.spoof_offset[2]
        msg.sigma = self.sigma_report
        self.pub.publish(msg)

        # Clean ground truth (no noise, no spoof) -- for UWB sim
        gt_msg = NoisyPose()
        gt_msg.timestamp = msg.timestamp
        gt_msg.uav_id = self.uav_id
        gt_msg.position.x = x_gt
        gt_msg.position.y = y_gt
        gt_msg.position.z = z_gt
        gt_msg.sigma = 0.0
        self.pub_gt.publish(gt_msg)

    def _on_param(self, params):
        from rcl_interfaces.msg import SetParametersResult
        for p in params:
            if p.name == 'spoof_offset':
                v = list(p.value)
                if len(v) != 3:
                    return SetParametersResult(
                        successful=False, reason='spoof_offset must be float[3]')
                self.spoof_offset = [float(v[0]), float(v[1]), float(v[2])]
                self.get_logger().info(
                    f'spoof_offset set -> [{v[0]:.1f}, {v[1]:.1f}, {v[2]:.1f}]'
                )
        return SetParametersResult(successful=True)


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
