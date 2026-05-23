"""Phase 2 verifier node -- paper Section IV-B end + Section IV-C.

Wraps the Phase 1-validated PoO pipeline (SuperPoint v1, top-N=50,
Mode A K=20, Lowe ratio tau=0.7, T_verify=0.30) as a ROS2 callback
on /uav<i>/signed_observation. Buffers each observation until the
verifier's OWN current position falls within r_verify = 500 m of the
observation's claimed position; at that point captures the verifier's
camera frame (we use the staged Zurich Z16 tile based on the
synthetic position for headless dev), runs SuperPoint + Lowe-ratio
match, and publishes a ReputationUpdate on
/reputation/update/u<target> with reason VERIFIED or UNVERIFIED.

Phase 2 mocks Ed25519 signature verification (paper trusts crypto;
this phase focuses on reputation chain mechanics). INVALID_SIG and
UWB_RANGE_FAIL reasons are emitted by other nodes.

Parameters:
  verifier_id          (int)   default 0
  position_topic       (str)   '/uav<id>/noisy_pose' (uses NoisyPose)
  dataset_dir          (str)   '/datasets/zurich-z16' for tile lookup
  r_verify             (float) 500.0 m -- paper Section IV-B
  t_verify             (float) 0.30  -- VERIFIED threshold (Phase 1 validated)
  k_modea              (int)   20    -- transmitted descriptors per spec
  n_top                (int)   50    -- top-N keypoints for hash basis
  lowe_tau             (float) 0.7   -- Lowe ratio matcher
  max_pending_age_s    (float) 3600.0 -- T_max_verify per paper Section IV-C end
"""

from __future__ import annotations

import math
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import (
    NoisyPose,
    ReputationUpdate,
    SignedObservation,
)


@dataclass
class PendingObs:
    target_id: int
    position_xyz: tuple[float, float, float]
    timestamp_us: int  # observation t_1
    descriptors: list  # Mode A descriptors (K = len)


class VerifierNode(Node):
    def __init__(self) -> None:
        super().__init__('verifier_node')

        self.declare_parameter('verifier_id', 0)
        self.declare_parameter('position_topic', '/uav0/noisy_pose')
        self.declare_parameter('dataset_dir', '/datasets/zurich-z16')
        self.declare_parameter('r_verify', 500.0)
        self.declare_parameter('t_verify', 0.30)
        self.declare_parameter('k_modea', 20)
        self.declare_parameter('n_top', 50)
        self.declare_parameter('lowe_tau', 0.7)
        self.declare_parameter('max_pending_age_s', 3600.0)

        self.verifier_id = int(self.get_parameter('verifier_id').value)
        self.position_topic = str(self.get_parameter('position_topic').value)
        self.dataset_dir = str(self.get_parameter('dataset_dir').value)
        self.r_verify = float(self.get_parameter('r_verify').value)
        self.t_verify = float(self.get_parameter('t_verify').value)
        self.k_modea = int(self.get_parameter('k_modea').value)
        self.n_top = int(self.get_parameter('n_top').value)
        self.lowe_tau = float(self.get_parameter('lowe_tau').value)
        self.max_pending_age_s = float(self.get_parameter('max_pending_age_s').value)

        # Lazy: SuperPoint + cv2 + torch loaded on first verify
        self._model = None
        self._device = None
        self._tile_paths: list = []

        self.my_position_xyz: Optional[tuple[float, float, float]] = None
        self.pending: deque[PendingObs] = deque(maxlen=200)

        # Subscriptions
        self.create_subscription(
            SignedObservation,
            '/signed_observation',  # broadcast channel; any UAV can publish
            self._on_observation,
            10,
        )
        self.create_subscription(
            NoisyPose, self.position_topic, self._on_my_position, 10
        )

        # ReputationUpdate publisher (created lazily per target id since
        # ROS2 topics need to start with non-digit segment, see Phase 4
        # gotcha doc)
        self._rep_pubs: dict[int, rclpy.publisher.Publisher] = {}

        # Verification-attempt tick
        self.tick_timer = self.create_timer(0.5, self._tick)

        self.get_logger().info(
            f'verifier_node: id={self.verifier_id} '
            f'r_verify={self.r_verify}m T_verify={self.t_verify} '
            f'K={self.k_modea} N={self.n_top} tau={self.lowe_tau} '
            f'dataset_dir={self.dataset_dir}'
        )

    # ─── ROS callbacks ────────────────────────────────────────────────

    def _on_my_position(self, msg: NoisyPose) -> None:
        self.my_position_xyz = (msg.position.x, msg.position.y, msg.position.z)

    def _on_observation(self, msg: SignedObservation) -> None:
        # Ignore my own observations
        if int(msg.uav_id) == self.verifier_id:
            return
        # Mode A only for Phase 2; Mode B (hash-only) is a future item
        if len(msg.descriptors) == 0:
            return
        # Stash for later verification on revisit
        self.pending.append(PendingObs(
            target_id=int(msg.uav_id),
            position_xyz=(msg.position.x, msg.position.y, msg.position.z),
            timestamp_us=int(msg.timestamp),
            descriptors=list(msg.descriptors),
        ))

    def _tick(self) -> None:
        if self.my_position_xyz is None or not self.pending:
            return
        # Walk pending; verify any we are now within r_verify of, drop stale
        now_us = int(time.time() * 1_000_000)
        max_age_us = int(self.max_pending_age_s * 1_000_000)
        to_drop: list[int] = []
        for i, obs in enumerate(self.pending):
            if (now_us - obs.timestamp_us) > max_age_us:
                to_drop.append(i)
                continue
            d = self._dist(self.my_position_xyz, obs.position_xyz)
            if d <= self.r_verify:
                self._verify_and_emit(obs)
                to_drop.append(i)
        # Drop processed/stale entries (descending indices to preserve order)
        for i in sorted(to_drop, reverse=True):
            del self.pending[i]

    # ─── PoO pipeline ────────────────────────────────────────────────

    def _verify_and_emit(self, obs: PendingObs) -> None:
        try:
            verdict = self._run_poo(obs)
        except Exception as exc:
            self.get_logger().error(f'PoO pipeline error for target={obs.target_id}: {exc}')
            return
        reason = ReputationUpdate.REASON_VERIFIED if verdict else ReputationUpdate.REASON_UNVERIFIED
        upd = ReputationUpdate()
        upd.timestamp = int(time.time() * 1_000_000)
        upd.reporter_id = self.verifier_id
        upd.target_id = obs.target_id
        upd.old_value = 0.0  # filled by reputation_manager
        upd.new_value = 0.0  # filled by reputation_manager
        upd.reason = reason
        self._pub_for(obs.target_id).publish(upd)
        self.get_logger().info(
            f'verifier {self.verifier_id} -> target {obs.target_id}: '
            f'{"VERIFIED" if verdict else "UNVERIFIED"}'
        )

    def _pub_for(self, target_id: int) -> rclpy.publisher.Publisher:
        if target_id not in self._rep_pubs:
            # Topic-name segment must start with a non-digit (see Phase 4
            # gotcha). Prefix 'u' for UAV id.
            self._rep_pubs[target_id] = self.create_publisher(
                ReputationUpdate, f'/reputation/update/u{target_id}', 10
            )
        return self._rep_pubs[target_id]

    def _run_poo(self, obs: PendingObs) -> bool:
        """Returns True if VERIFIED (V > T_verify), False UNVERIFIED."""
        self._ensure_model_loaded()
        import cv2  # type: ignore
        import torch  # type: ignore

        # Verifier captures own frame == lookup tile at obs.position
        tile_img = self._lookup_tile_for_position(obs.position_xyz)
        if tile_img is None:
            # No tile coverage -- treat as UNVERIFIED conservatively
            return False

        gray = cv2.cvtColor(tile_img, cv2.COLOR_BGR2GRAY).astype('float32') / 255.0
        t = torch.from_numpy(gray)[None, None, ...].to(self._device)
        with torch.no_grad():
            out = self._model({'image': t})
        scores = out['keypoint_scores'][0]
        desc = out['descriptors'][0]
        if desc.shape[0] == 0:
            return False
        idx = torch.argsort(scores, descending=True)[:self.n_top]
        revisit_descN = desc[idx]

        # Mode A: obs.descriptors is the K=20 transmitted set. Each
        # descriptor is 256 floats; obs.descriptors flattens it.
        n_obs = len(obs.descriptors) // 256
        if n_obs == 0:
            return False
        obs_desc = torch.tensor(obs.descriptors, dtype=torch.float32,
                                device=self._device).view(n_obs, 256)

        # Lowe ratio match
        if obs_desc.shape[0] == 0 or revisit_descN.shape[0] < 2:
            return False
        d = torch.cdist(obs_desc, revisit_descN)
        top2 = torch.topk(d, k=2, largest=False, dim=1).values
        accepted = (top2[:, 0] < self.lowe_tau * top2[:, 1]).sum().item()
        v_score = accepted / max(self.k_modea, 1)
        return v_score > self.t_verify

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

    def _lookup_tile_for_position(self, xyz: tuple[float, float, float]):
        """Deterministic tile selection from synthetic xyz position.

        Phase 2 uses synthetic UAV positions; we map xyz -> a tile by
        modulo of the integer x-coordinate to deterministically pick
        from staged Zurich tiles. Phase 6+ (real flight in Gazebo) will
        replace this with actual camera capture.
        """
        if not self._tile_paths:
            return None
        idx = int(abs(xyz[0])) % len(self._tile_paths)
        import cv2  # type: ignore
        return cv2.imread(self._tile_paths[idx])

    # ─── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return math.sqrt(
            (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VerifierNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
