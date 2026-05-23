"""Phase 3 factor graph node -- paper Section IV-D.

Per-UAV iSAM2 fixed-lag smoother estimating each peer's current Point3
position (3-DOF only -- Phase 3 measures CEP, rotation is out of scope
for this measurement campaign). Symbols are integer-keyed by uav_id;
each UAV gets one current-position estimate maintained across ticks.

Factor types (paper IV-D mapping):
  PriorFactorPoint3 anchor TRN
      Anchors with known initial_position get a tight self-prior at
      startup. Phase 3 mocks the TRN factor as initial-position-=-truth;
      task 3.4 (trn_anchor_node) will replace this with periodic
      camera-driven TRN fixes.

  PriorFactorPoint3 reputation-weighted peer prior
      Every DistilledState received -> prior on peer's Point3 with
      noise sigma = sigma_base / (R_peer + eps), per paper formula 9.
      sigma_base=50, eps=0.01 (paper defaults).
      Covariance anisotropy: (sigma, sigma, sigma/2) lat/lon/alt per
      paper's halved-altitude assumption (anchors with barometric
      altimeters have tighter altitude bound).

  RangeFactor3D UWB
      Each UwbRangeMeasurement -> range constraint between sender +
      receiver Point3 keys. sigma_range = msg.sigma_m (default 0.1 m
      paper Section IV-D).

ISAM2 update rate: configurable, default 20 Hz (paper says <50 ms
optimisation latency budget; gtsam Python easily fits that on CPU).
On each tick, accumulated factors are committed in a single
isam.update(); EstimatedPose is published with this UAV's MAP estimate.

Parameters:
  uav_id              (int)    default 0
  is_anchor           (bool)   default false  -- anchors get self-prior
  initial_position    (float[3]) [0,0,50]
  update_rate_hz      (float)  20.0
  sigma_base          (float)  50.0  -- paper Section IV-D
  reputation_eps      (float)  0.01
  anchor_self_sigma   (float)  1.0   -- tightness of anchor's self-anchor
                                       prior (will be replaced with real
                                       TRN-fix uncertainty in task 3.4)
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import (
    DistilledState,
    EstimatedPose,
    TrnAbsoluteFix,
    UwbRangeMeasurement,
)


class FactorGraphNode(Node):
    def __init__(self, node_name: str = 'factor_graph_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('uav_id', 0)
        self.declare_parameter('is_anchor', False)
        self.declare_parameter('initial_position', [0.0, 0.0, 50.0])
        self.declare_parameter('update_rate_hz', 20.0)
        self.declare_parameter('sigma_base', 50.0)
        self.declare_parameter('reputation_eps', 0.01)
        self.declare_parameter('anchor_self_sigma', 1.0)
        self.declare_parameter('follower_self_sigma', 50.0)

        self.uav_id = int(self.get_parameter('uav_id').value)
        self.is_anchor = bool(self.get_parameter('is_anchor').value)
        ip = self.get_parameter('initial_position').value
        self.initial_position = (float(ip[0]), float(ip[1]), float(ip[2]))
        rate = float(self.get_parameter('update_rate_hz').value)
        self.sigma_base = float(self.get_parameter('sigma_base').value)
        self.eps = float(self.get_parameter('reputation_eps').value)
        self.anchor_self_sigma = float(self.get_parameter('anchor_self_sigma').value)
        self.follower_self_sigma = float(self.get_parameter('follower_self_sigma').value)

        # Lazy GTSAM (so unit tests can spawn the node without gtsam)
        self._gtsam = None
        self._isam = None
        self.pending_factors = None
        self.pending_init = None
        self.known_keys: set[int] = set()

        # Subscriptions
        self.create_subscription(DistilledState, '/distilled_state', self._on_state, 20)
        self.create_subscription(UwbRangeMeasurement, '/uwb/range', self._on_range, 50)
        self.create_subscription(TrnAbsoluteFix, '/trn/fix', self._on_trn, 20)

        self.pub_est = self.create_publisher(
            EstimatedPose, f'/estimate/u{self.uav_id}/pose', 10
        )

        # 20 Hz update tick
        self.timer = self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info(
            f'factor_graph_node: uav_id={self.uav_id} is_anchor={self.is_anchor} '
            f'init_pos={self.initial_position} rate={rate}Hz '
            f'sigma_base={self.sigma_base} eps={self.eps}'
        )

    # ─── lazy gtsam init ────────────────────────────────────────────

    def _ensure_gtsam(self) -> None:
        if self._gtsam is not None:
            return
        import gtsam  # type: ignore
        self._gtsam = gtsam
        self._isam = gtsam.ISAM2()
        self.pending_factors = gtsam.NonlinearFactorGraph()
        self.pending_init = gtsam.Values()
        # Seed graph with self entry
        self._seed_self()

    def _seed_self(self) -> None:
        g = self._gtsam
        init_pt = g.Point3(*self.initial_position)
        self.pending_init.insert(self.uav_id, init_pt)
        self.known_keys.add(self.uav_id)
        # Anchors get a tight TRN-mocked self-prior (paper IV-D: TRN-equipped
        # anchors contribute absolute position constraints; task 3.4 replaces
        # this with periodic camera-driven TRN fixes).
        # Followers get a WIDE self-prior (default 50 m) so iSAM2 has
        # something to pull against -- a single range from a single anchor
        # leaves the follower on a sphere and is mathematically
        # underdetermined. Real follower deployments have IMU pre-integration
        # + previous-step belief; the wide self-prior approximates that
        # before task 3.5 wires real IMU factors.
        s = self.anchor_self_sigma if self.is_anchor else self.follower_self_sigma
        noise = g.noiseModel.Diagonal.Sigmas([s, s, s * 0.5])
        self.pending_factors.add(g.PriorFactorPoint3(self.uav_id, init_pt, noise))

    # ─── callbacks ──────────────────────────────────────────────────

    def _on_state(self, msg: DistilledState) -> None:
        self._ensure_gtsam()
        peer = int(msg.uav_id)
        if peer == self.uav_id:
            return
        g = self._gtsam
        pt = g.Point3(msg.position.x, msg.position.y, msg.position.z)
        # Reputation-weighted noise per paper formula 9.
        sigma = self.sigma_base / (max(msg.reputation, 0.0) + self.eps)
        noise = g.noiseModel.Diagonal.Sigmas([sigma, sigma, sigma * 0.5])
        if peer not in self.known_keys:
            self.pending_init.insert(peer, pt)
            self.known_keys.add(peer)
        self.pending_factors.add(g.PriorFactorPoint3(peer, pt, noise))

    def _on_range(self, msg: UwbRangeMeasurement) -> None:
        self._ensure_gtsam()
        sender = int(msg.sender_id)
        receiver = int(msg.receiver_id)
        # Only add the factor when BOTH peers are already initialised
        # (otherwise iSAM2 update would fail on missing initial guesses).
        if sender not in self.known_keys or receiver not in self.known_keys:
            return
        g = self._gtsam
        sigma = max(float(msg.sigma_m), 0.01)
        noise = g.noiseModel.Isotropic.Sigma(1, sigma)
        # RangeFactor3 takes Point3 keys (Range[Factor3D] is for Pose3 SE(3));
        # the bare number suffix in gtsam Python means N-dim Euclidean point.
        self.pending_factors.add(
            g.RangeFactor3(sender, receiver, float(msg.range_m), noise)
        )

    def _on_trn(self, msg: TrnAbsoluteFix) -> None:
        """Anchor TRN fix -- adds a tight prior on the anchor's key."""
        self._ensure_gtsam()
        anchor = int(msg.uav_id)
        g = self._gtsam
        pt = g.Point3(msg.position.x, msg.position.y, msg.position.z)
        sigma = max(float(msg.sigma_m), 0.01)
        noise = g.noiseModel.Diagonal.Sigmas([sigma, sigma, sigma * 0.5])
        if anchor not in self.known_keys:
            self.pending_init.insert(anchor, pt)
            self.known_keys.add(anchor)
        self.pending_factors.add(g.PriorFactorPoint3(anchor, pt, noise))

    # ─── periodic iSAM2 update ──────────────────────────────────────

    def _tick(self) -> None:
        self._ensure_gtsam()
        # Integrate any newly-accumulated factors
        if self.pending_factors.size() > 0 or self.pending_init.size() > 0:
            try:
                self._isam.update(self.pending_factors, self.pending_init)
            except Exception as exc:
                self.get_logger().warning(f'iSAM2 update failed: {exc}')
            finally:
                self.pending_factors.resize(0)
                self.pending_init.clear()
        # ALWAYS publish current estimate so downstream subscribers
        # (CEP measurement, scenario runner) see a steady stream and
        # don't miss the only-ever message because they were late to
        # subscribe.
        try:
            result = self._isam.calculateEstimate()
        except Exception:
            return
        if not result.exists(self.uav_id):
            return
        my_pt = result.atPoint3(self.uav_id)
        est = EstimatedPose()
        est.timestamp = int(time.time() * 1_000_000)
        est.uav_id = self.uav_id
        est.position.x = float(my_pt[0])
        est.position.y = float(my_pt[1])
        est.position.z = float(my_pt[2])
        # Phase 3 MVP: marginal covariance compute deferred to task 3.9
        # analysis (gtsam.Marginals on accumulated graph). Leave 0s.
        est.position_covariance = [0.0] * 6
        est.n_hops_from_anchor = 0   # filled by topology generator (task 3.6)
        est.n_active_anchors = sum(
            1 for k in self.known_keys if k != self.uav_id
        )
        self.pub_est.publish(est)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FactorGraphNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
