"""Phase 2 SignedObservation producer -- paper Section IV-B.

Per-UAV. Two modes:
  honest    -- top-K SuperPoint descriptors from tile at OWN position
  byzantine -- top-K descriptors from a tile at offset_x away from own
               position; the published OBS.position still claims OWN
               position (this is the "replay from elsewhere" attack
               that paper Section IV-B's unforgeability argument
               addresses)

Verifiers downstream (verifier_node) revisit the claimed position
and recompute SuperPoint on the actual ground; honest descriptors
match (V > T_verify=0.30), byzantine don't (V <<< T_verify, Phase 1
measured V_byz_max = 0.30 on Zurich Z16).

Publishes on /signed_observation (broadcast). Signature mocked
(zero bytes) -- paper trusts Ed25519 crypto; Phase 2 focuses on
the reputation chain, not crypto.

Parameters:
  uav_id              (int)   default 0
  mode                (str)   default 'honest'  -- 'honest' | 'byzantine'
  position_topic      (str)   '/uav<id>/noisy_pose' (subscribes)
  dataset_dir         (str)   '/datasets/zurich-z16'
  publish_period_s    (float) 45.0  -- paper nu_verify^-1
  n_top               (int)   50    -- top-N keypoints
  k_modea             (int)   20    -- Mode A transmitted descriptors
  byzantine_offset_x  (float) 3000.0 -- metres -- pick a tile from "far" away
"""

from __future__ import annotations

import os
import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import NoisyPose, SignedObservation


class SignedObservationPublisherNode(Node):
    def __init__(self) -> None:
        super().__init__('signed_observation_publisher_node')

        self.declare_parameter('uav_id', 0)
        self.declare_parameter('mode', 'honest')
        self.declare_parameter('position_topic', '/uav0/noisy_pose')
        self.declare_parameter('dataset_dir', '/datasets/zurich-z16')
        self.declare_parameter('publish_period_s', 45.0)
        self.declare_parameter('n_top', 50)
        self.declare_parameter('k_modea', 20)
        self.declare_parameter('byzantine_offset_x', 3000.0)

        self.uav_id = int(self.get_parameter('uav_id').value)
        self.mode = str(self.get_parameter('mode').value).lower()
        if self.mode not in ('honest', 'byzantine'):
            raise ValueError(f'mode must be honest|byzantine, got {self.mode!r}')
        self.position_topic = str(self.get_parameter('position_topic').value)
        self.dataset_dir = str(self.get_parameter('dataset_dir').value)
        period = float(self.get_parameter('publish_period_s').value)
        self.n_top = int(self.get_parameter('n_top').value)
        self.k_modea = int(self.get_parameter('k_modea').value)
        self.byz_offset_x = float(self.get_parameter('byzantine_offset_x').value)

        self.my_position_xyz: tuple[float, float, float] = (0.0, 0.0, 50.0)

        # Lazy SuperPoint
        self._model = None
        self._device = None
        self._tile_paths: list = []

        self.create_subscription(NoisyPose, self.position_topic, self._on_pose, 10)
        self.pub = self.create_publisher(SignedObservation, '/signed_observation', 10)

        self.timer = self.create_timer(period, self._publish_observation)

        self.get_logger().info(
            f'signed_observation_publisher: uav_id={self.uav_id} mode={self.mode} '
            f'period={period}s n_top={self.n_top} K={self.k_modea} '
            f'byz_offset_x={self.byz_offset_x}m'
        )

    def _on_pose(self, msg: NoisyPose) -> None:
        self.my_position_xyz = (msg.position.x, msg.position.y, msg.position.z)

    def _publish_observation(self) -> None:
        try:
            descs = self._extract_descriptors()
        except Exception as exc:
            self.get_logger().error(f'descriptor extraction failed: {exc}')
            return

        obs = SignedObservation()
        obs.timestamp = int(time.time() * 1_000_000)
        # CLAIM own position regardless of mode (byzantine forge: claim
        # we observed at our position but use descriptors from elsewhere)
        obs.position.x, obs.position.y, obs.position.z = self.my_position_xyz
        obs.hash_sha256 = [0] * 32  # paper IV-B hash; Phase 2 mocks
        obs.ransac_inlier_ratio = 0.85
        obs.uav_id = self.uav_id
        obs.signature_ed25519 = [0] * 64  # crypto mocked per Phase 2 scope
        obs.descriptors = descs
        self.pub.publish(obs)
        self.get_logger().info(
            f'OBS mode={self.mode} uav={self.uav_id} '
            f'claim_pos=({self.my_position_xyz[0]:.1f},{self.my_position_xyz[1]:.1f},{self.my_position_xyz[2]:.1f}) '
            f'desc_floats={len(descs)}'
        )

    def _extract_descriptors(self) -> list:
        """Top-K=20 descriptors flattened from the relevant tile."""
        self._ensure_model_loaded()
        import cv2  # type: ignore
        import torch  # type: ignore

        if self.mode == 'honest':
            target_xyz = self.my_position_xyz
        else:
            target_xyz = (
                self.my_position_xyz[0] + self.byz_offset_x,
                self.my_position_xyz[1],
                self.my_position_xyz[2],
            )
        idx = int(abs(target_xyz[0])) % len(self._tile_paths)
        img = cv2.imread(self._tile_paths[idx])
        if img is None:
            return []

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype('float32') / 255.0
        t = torch.from_numpy(gray)[None, None, ...].to(self._device)
        with torch.no_grad():
            out = self._model({'image': t})
        scores = out['keypoint_scores'][0]
        desc = out['descriptors'][0]
        if desc.shape[0] == 0:
            return []
        top_idx = torch.argsort(scores, descending=True)[:self.n_top]
        topN = desc[top_idx]
        # Mode A: take top-K of those as the transmitted set
        modeA = topN[:self.k_modea]
        # Flatten to list[float] for ROS serialisation (256-D each)
        return modeA.flatten().cpu().tolist()

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        import torch  # type: ignore
        from lightglue import SuperPoint  # type: ignore
        self._device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self._model = SuperPoint(max_num_keypoints=512).eval().to(self._device)
        self._tile_paths = sorted(
            os.path.join(self.dataset_dir, f)
            for f in os.listdir(self.dataset_dir)
            if f.endswith('.png')
        )
        self.get_logger().info(
            f'SuperPoint loaded on {self._device}; {len(self._tile_paths)} tiles available'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SignedObservationPublisherNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
