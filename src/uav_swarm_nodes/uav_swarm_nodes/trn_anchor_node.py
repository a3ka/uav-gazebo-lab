"""Phase 3 TRN anchor node -- paper Section IV-D anchor absolute fix.

Anchor-only. Every t_trn seconds (paper default 10 s = 0.1 Hz)
publishes a TrnAbsoluteFix declaring "I observed my own position via
TRN at <pos> +/- <sigma>". The factor_graph_node consumes this as a
tight PriorFactorPoint3 on the anchor's key.

PoO pipeline shortcut for Phase 3 MVP: instead of running camera +
SuperPoint match on every TRN tick (which would burn GPU for every
anchor every 10 s), this node adds Gaussian noise to the ground-truth
position and emits the noisy fix. Phase 1 (AUC=0.9996, FRR=4.6%)
already validated the underlying PoO inference; Phase 3 is measuring
how the FACTOR GRAPH integrates TRN fixes, not re-validating PoO.
Phase 6+ swaps the noise model for real Gazebo camera + Phase 1
pipeline call.

Parameters:
  uav_id              (int)    default 0
  initial_position    (float[3]) [0,0,50]    -- ground truth used when no NoisyPose received
  position_topic      (str)    /uav<id>/noisy_pose   -- live ground truth
  trn_period_s        (float)  10.0  -- paper Section IV-D
  sigma_trn_m         (float)  5.0   -- 1-sigma noise of TRN fix
  seed                (int)    42    -- RNG for reproducibility
"""

from __future__ import annotations

import random
import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import NoisyPose, TrnAbsoluteFix


class TrnAnchorNode(Node):
    def __init__(self, node_name: str = 'trn_anchor_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('uav_id', 0)
        self.declare_parameter('initial_position', [0.0, 0.0, 50.0])
        self.declare_parameter('position_topic', '/uav0/noisy_pose')
        self.declare_parameter('trn_period_s', 10.0)
        self.declare_parameter('sigma_trn_m', 5.0)
        self.declare_parameter('seed', 42)

        self.uav_id = int(self.get_parameter('uav_id').value)
        ip = self.get_parameter('initial_position').value
        self.gt_position: tuple[float, float, float] = (
            float(ip[0]), float(ip[1]), float(ip[2])
        )
        self.position_topic = str(self.get_parameter('position_topic').value)
        period = float(self.get_parameter('trn_period_s').value)
        self.sigma_trn = float(self.get_parameter('sigma_trn_m').value)
        self.rng = random.Random(int(self.get_parameter('seed').value))

        self.create_subscription(
            NoisyPose, self.position_topic, self._on_pose, 10
        )
        self.pub = self.create_publisher(TrnAbsoluteFix, '/trn/fix', 10)
        self.timer = self.create_timer(period, self._publish_fix)

        self.get_logger().info(
            f'trn_anchor_node: uav_id={self.uav_id} period={period}s '
            f'sigma_trn={self.sigma_trn}m gt={self.gt_position}'
        )

    def _on_pose(self, msg: NoisyPose) -> None:
        # Live ground truth (e.g. from Gazebo) overrides initial_position.
        if int(msg.uav_id) != self.uav_id:
            return
        self.gt_position = (msg.position.x, msg.position.y, msg.position.z)

    def _publish_fix(self) -> None:
        fix = TrnAbsoluteFix()
        fix.timestamp = int(time.time() * 1_000_000)
        fix.uav_id = self.uav_id
        gx, gy, gz = self.gt_position
        # Add Gaussian noise -- mocks Phase 1 PoO inference uncertainty
        # (paper-stated TRN CEP ~5 m at flight altitude)
        fix.position.x = gx + self.rng.gauss(0.0, self.sigma_trn)
        fix.position.y = gy + self.rng.gauss(0.0, self.sigma_trn)
        # Altitude TRN is tighter (paper IV-D anisotropy 0.5)
        fix.position.z = gz + self.rng.gauss(0.0, self.sigma_trn * 0.5)
        fix.sigma_m = float(self.sigma_trn)
        self.pub.publish(fix)
        self.get_logger().info(
            f'TRN fix uav={self.uav_id}: '
            f'({fix.position.x:.2f},{fix.position.y:.2f},{fix.position.z:.2f}) '
            f'sigma={fix.sigma_m:.2f}'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TrnAnchorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
