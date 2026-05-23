"""Phase 2 reputation manager node -- paper Section IV-C.

Per-UAV. Maintains a dict[peer_id, R_value] view of every peer's
reputation; applies asymmetric updates on incoming ReputationUpdate
events and temporal decay on each tick.

Asymmetric update (paper Section IV-C):
  R_target  +=  alpha_pos * R_verifier           (VERIFIED)
  R_target  -=  alpha_neg * R_verifier           (UNVERIFIED)
  R_target  -=  alpha_sig                        (INVALID_SIG)
  R_target  -=  alpha_range                      (UWB_RANGE_FAIL)
then clamp to [0, 1]. R_verifier is THIS node's current view of the
reporter (the voter); first-time peers default to R_init.

Temporal decay (paper Section IV-C end):
  R_target *= exp(-lambda * dt)
applied on each tick to all peers (default 10^-3 s^-1).

Broadcasts:
  - DistilledState (this UAV's own reputation, periodic 5 Hz, paper
    Section IV-D primitive)
  - PeerReputationView per peer (periodic 1 Hz, used by
    quorum_exclusion_node downstream)

Parameters:
  uav_id                 (int)   default 0
  r_init                 (float) 0.5
  alpha_pos              (float) 0.05
  alpha_neg              (float) 0.15
  alpha_sig              (float) 0.30
  alpha_range            (float) 0.10
  lambda_decay           (float) 1e-3   s^-1
  view_broadcast_rate    (float) 1.0    Hz
  state_broadcast_rate   (float) 5.0    Hz
  initial_position       (float[3]) [0,0,50]
"""

from __future__ import annotations

import math
import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import (
    DistilledState,
    PeerReputationView,
    ReputationUpdate,
)


class ReputationManagerNode(Node):
    def __init__(self) -> None:
        super().__init__('reputation_manager_node')

        self.declare_parameter('uav_id', 0)
        self.declare_parameter('r_init', 0.5)
        self.declare_parameter('alpha_pos', 0.05)
        self.declare_parameter('alpha_neg', 0.15)
        self.declare_parameter('alpha_sig', 0.30)
        self.declare_parameter('alpha_range', 0.10)
        self.declare_parameter('lambda_decay', 1e-3)
        self.declare_parameter('view_broadcast_rate', 1.0)
        self.declare_parameter('state_broadcast_rate', 5.0)
        self.declare_parameter('initial_position', [0.0, 0.0, 50.0])

        self.uav_id = int(self.get_parameter('uav_id').value)
        self.r_init = float(self.get_parameter('r_init').value)
        self.alpha_pos = float(self.get_parameter('alpha_pos').value)
        self.alpha_neg = float(self.get_parameter('alpha_neg').value)
        self.alpha_sig = float(self.get_parameter('alpha_sig').value)
        self.alpha_range = float(self.get_parameter('alpha_range').value)
        self.lambda_decay = float(self.get_parameter('lambda_decay').value)
        view_rate = float(self.get_parameter('view_broadcast_rate').value)
        state_rate = float(self.get_parameter('state_broadcast_rate').value)
        ip = self.get_parameter('initial_position').value
        self.pos_x, self.pos_y, self.pos_z = float(ip[0]), float(ip[1]), float(ip[2])

        # Per-peer state: peer_id -> (R, last_update_monotonic)
        # This UAV's own R is also in here so we can broadcast it.
        self.rep: dict[int, tuple[float, float]] = {
            self.uav_id: (1.0, time.monotonic()),  # ourself = full trust
        }

        # Subscribe to ReputationUpdate addressed to ANY of our peers.
        # Per the verifier_node convention, updates land on
        # /reputation/update/u<target_id>. We use a wildcard-style
        # approach: we subscribe to a single broadcast channel as well
        # (Phase 2 scenario_runner sets up wiring), plus we listen on
        # our own channel for self-targeted updates.
        self.create_subscription(
            ReputationUpdate,
            f'/reputation/update/u{self.uav_id}',
            self._on_update,
            10,
        )
        # Broadcast channel that any verifier_node may also publish to
        # for convenience (so we don't need one sub per known peer).
        self.create_subscription(
            ReputationUpdate, '/reputation/update', self._on_update, 10
        )

        # Per-peer view publishers (lazy)
        self._view_pubs: dict[int, rclpy.publisher.Publisher] = {}
        # Own DistilledState publisher
        self.pub_state = self.create_publisher(
            DistilledState, f'/anchor{self.uav_id}/distilled_state', 10
        )

        # Periodic broadcasts
        self.view_timer = self.create_timer(1.0 / view_rate, self._broadcast_views)
        self.state_timer = self.create_timer(1.0 / state_rate, self._broadcast_state)
        # Decay tick at 10 Hz
        self.decay_timer = self.create_timer(0.1, self._apply_decay_tick)

        self.get_logger().info(
            f'reputation_manager_node: uav_id={self.uav_id} '
            f'alpha_pos={self.alpha_pos} alpha_neg={self.alpha_neg} '
            f'lambda={self.lambda_decay}/s view_rate={view_rate}Hz '
            f'state_rate={state_rate}Hz'
        )

    # ─── ROS callbacks ────────────────────────────────────────────────

    def _on_update(self, msg: ReputationUpdate) -> None:
        target = int(msg.target_id)
        reporter = int(msg.reporter_id)
        now = time.monotonic()

        # Look up reporter's R from our view (defaults to r_init for unknown)
        rk, _ = self.rep.get(reporter, (self.r_init, now))

        # Current target R (apply decay first so update is on current value)
        r_old, t_last = self.rep.get(target, (self.r_init, now))
        r_old *= math.exp(-self.lambda_decay * (now - t_last))

        # Apply asymmetric update by reason code
        reason = int(msg.reason)
        if reason == ReputationUpdate.REASON_VERIFIED:
            delta = +self.alpha_pos * rk
        elif reason == ReputationUpdate.REASON_UNVERIFIED:
            delta = -self.alpha_neg * rk
        elif reason == ReputationUpdate.REASON_INVALID_SIG:
            delta = -self.alpha_sig
        elif reason == ReputationUpdate.REASON_UWB_RANGE_FAIL:
            delta = -self.alpha_range
        elif reason == ReputationUpdate.REASON_DECAY:
            delta = 0.0  # decay is handled by _apply_decay_tick, not events
        else:
            self.get_logger().warning(f'unknown reason code {reason}, ignored')
            return

        r_new = max(0.0, min(1.0, r_old + delta))
        self.rep[target] = (r_new, now)
        self.get_logger().info(
            f'rep[{target}]: {r_old:.3f} -> {r_new:.3f} '
            f'(reason={reason}, reporter={reporter}, Rk={rk:.3f})'
        )

    # ─── periodic broadcasts ─────────────────────────────────────────

    def _apply_decay_tick(self) -> None:
        now = time.monotonic()
        for pid, (r, t_last) in list(self.rep.items()):
            if pid == self.uav_id:
                continue  # don't decay own self-reputation
            decayed = r * math.exp(-self.lambda_decay * (now - t_last))
            self.rep[pid] = (decayed, now)

    def _broadcast_state(self) -> None:
        own_r, _ = self.rep.get(self.uav_id, (1.0, time.monotonic()))
        msg = DistilledState()
        msg.timestamp = int(time.time() * 1_000_000)
        msg.position.x = self.pos_x
        msg.position.y = self.pos_y
        msg.position.z = self.pos_z
        msg.position_covariance = [4.0, 0.0, 0.0, 4.0, 0.0, 1.0]
        msg.reputation = float(own_r)
        msg.uav_id = self.uav_id
        # signature_ed25519 left zero (paper assumed; Phase 2 mocks crypto)
        self.pub_state.publish(msg)

    def _broadcast_views(self) -> None:
        now_us = int(time.time() * 1_000_000)
        for pid, (r, _) in self.rep.items():
            if pid == self.uav_id:
                continue  # we don't broadcast our self-view; DistilledState carries it
            pub = self._view_pub_for(pid)
            v = PeerReputationView()
            v.timestamp = now_us
            v.voter_id = self.uav_id
            v.target_id = pid
            v.r_value = float(r)
            pub.publish(v)

    def _view_pub_for(self, target_id: int) -> rclpy.publisher.Publisher:
        if target_id not in self._view_pubs:
            # /reputation/view/u<voter>/u<target> -- both segments
            # 'u'-prefixed per ROS2 topic-name validity gotcha
            self._view_pubs[target_id] = self.create_publisher(
                PeerReputationView,
                f'/reputation/view/u{self.uav_id}/u{target_id}',
                10,
            )
        return self._view_pubs[target_id]


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ReputationManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
