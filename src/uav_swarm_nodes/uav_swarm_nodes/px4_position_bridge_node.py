"""Phase 6 Tier A bridge: PX4 vehicle_local_position -> /uav<i>/noisy_pose.

PX4 SITL inside Gazebo publishes `/px4_<i>/fmu/out/vehicle_local_position`
(VehicleLocalPosition msg from px4_msgs). The Phase 4/6 protocol stack
expects `/uav<i>/noisy_pose` (NoisyPose). This bridge converts one to
the other so existing nodes keep working on top of real flight dynamics.

Parameters:
  uav_id           int    default 0      this UAV's id
  px4_id           int    default 0      PX4 instance id (typically == uav_id)
  sigma_report     float  default 50.0   reported uncertainty (paper IV-D)

Topics:
  Subscribes: /px4_<px4_id>/fmu/out/vehicle_local_position
  Publishes:  /uav<uav_id>/noisy_pose
              /uav<uav_id>/ground_truth (clean copy for UWB sim)
"""
from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from px4_msgs.msg import VehicleLocalPosition
from uav_swarm_msgs.msg import NoisyPose


class Px4PositionBridgeNode(Node):
    def __init__(self, node_name: str = 'px4_position_bridge_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)
        self.declare_parameter('uav_id', 0)
        self.declare_parameter('px4_id', 0)
        self.declare_parameter('sigma_report', 50.0)

        self.uav_id = int(self.get_parameter('uav_id').value)
        self.px4_id = int(self.get_parameter('px4_id').value)
        self.sigma_report = float(self.get_parameter('sigma_report').value)

        # PX4 uses BEST_EFFORT QoS by convention -- must match here or
        # subscription discovers no publisher.
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST, depth=10,
        )
        topic = f'/px4_{self.px4_id}/fmu/out/vehicle_local_position'
        self.create_subscription(VehicleLocalPosition, topic, self._on_vlp, qos)

        self.pub_noisy = self.create_publisher(
            NoisyPose, f'/uav{self.uav_id}/noisy_pose', 10
        )
        self.pub_gt = self.create_publisher(
            NoisyPose, f'/uav{self.uav_id}/ground_truth', 10
        )
        self.get_logger().info(
            f'px4_position_bridge: uav_id={self.uav_id} '
            f'px4_id={self.px4_id}  in={topic}'
        )

    def _on_vlp(self, msg: VehicleLocalPosition) -> None:
        n = NoisyPose()
        n.timestamp = int(time.time() * 1_000_000)
        n.uav_id = self.uav_id
        # PX4 publishes NED (North-East-Down) local frame; convert to ENU
        # (East-North-Up) so x/y/z align with the lab's existing
        # right-handed-Z-up convention used by anchor_node positions etc.
        n.position.x = float(msg.y)
        n.position.y = float(msg.x)
        n.position.z = float(-msg.z)
        n.sigma = self.sigma_report
        self.pub_noisy.publish(n)
        # Clean ground-truth copy (no spoof, no extra noise -- PX4 SITL
        # is the source of truth here).
        gt = NoisyPose()
        gt.timestamp = n.timestamp
        gt.uav_id = self.uav_id
        gt.position.x = n.position.x
        gt.position.y = n.position.y
        gt.position.z = n.position.z
        gt.sigma = 0.0
        self.pub_gt.publish(gt)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Px4PositionBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
