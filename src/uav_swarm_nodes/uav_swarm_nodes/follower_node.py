"""Phase 4 follower node -- paper Section IV-F.

State machine:
  ATTACHED (current_anchor!=None) -> watchdog ticks; restart on each
    DistilledState received.
  DETECTING (watchdog fired) -> send ReassignRequest; collect offers
    for T_offer_window; select best per S_reassign; send ATTACH.
  ATTACHING (sent ATTACH, awaiting AttachAck) -> on ack: switch to
    new anchor, log switching time, back to ATTACHED.

Switching time = AttachAck arrival - last DistilledState received from
the previous anchor (= effective anchor-death moment from this
follower's vantage point). Published as std_msgs/Float64 on
/phase4/timing/<follower_id>.

Parameters:
  follower_id          (int)   default 0
  initial_anchor_id    (int)   default 0
  known_anchor_ids     (int[]) default [0, 1]  -- pool to subscribe to
                                                 offers from
  t_timeout            (float) default 5.0   (s)
  t_offer_window       (float) default 1.0   (s)
  alpha_prox           (float) default 0.4
  alpha_rep            (float) default 0.35
  alpha_cap            (float) default 0.25
  target_capacity_norm (float) default 10.0  -- normaliser for offer
                                                capacity in selection
"""

import math
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64

from uav_swarm_msgs.msg import (
    AttachAck,
    DistilledState,
    ReassignOffer,
    ReassignRequest,
)

STATE_ATTACHED = 'ATTACHED'
STATE_DETECTING = 'DETECTING'
STATE_ATTACHING = 'ATTACHING'


class FollowerNode(Node):
    def __init__(self) -> None:
        super().__init__('follower_node')

        self.declare_parameter('follower_id', 0)
        self.declare_parameter('initial_anchor_id', 0)
        self.declare_parameter('known_anchor_ids', [0, 1])
        self.declare_parameter('t_timeout', 5.0)
        self.declare_parameter('t_offer_window', 1.0)
        self.declare_parameter('alpha_prox', 0.4)
        self.declare_parameter('alpha_rep', 0.35)
        self.declare_parameter('alpha_cap', 0.25)
        self.declare_parameter('target_capacity_norm', 10.0)

        self.follower_id = int(self.get_parameter('follower_id').value)
        self.current_anchor = int(self.get_parameter('initial_anchor_id').value)
        self.known_anchors = [int(x) for x in self.get_parameter('known_anchor_ids').value]
        self.t_timeout = float(self.get_parameter('t_timeout').value)
        self.t_offer_window = float(self.get_parameter('t_offer_window').value)
        self.alpha_prox = float(self.get_parameter('alpha_prox').value)
        self.alpha_rep = float(self.get_parameter('alpha_rep').value)
        self.alpha_cap = float(self.get_parameter('alpha_cap').value)
        self.capacity_norm = float(self.get_parameter('target_capacity_norm').value)

        # State
        self.state = STATE_ATTACHED
        self.last_distilled_t = time.monotonic()
        self.last_known_position = (0.0, 0.0, 50.0)
        self.last_known_velocity = (0.0, 0.0, 0.0)
        self.offers_received: list[ReassignOffer] = []
        self.t_anchor_death: float = 0.0  # set when watchdog fires
        self.attach_target: int | None = None

        # Publishers
        # ROS2 topic-segment validator rejects segments that start with a digit,
        # so anchor ids are prefixed 'a' and follower ids 'f' everywhere they
        # appear in topic names. (See anchor_node for the matching convention.)
        self.pub_request = self.create_publisher(ReassignRequest, '/reassign/request', 10)
        # ATTACH publishers per-anchor created lazily in _send_attach
        self.pub_timing = self.create_publisher(
            Float64, f'/phase4/timing/f{self.follower_id}', 10
        )

        # Initial subscription to current anchor's DistilledState
        self.sub_distilled = self.create_subscription(
            DistilledState,
            f'/anchor{self.current_anchor}/distilled_state',
            self._on_distilled,
            10,
        )

        # Subscribe to all known anchors' offer channels
        self.offer_subs = []
        for aid in self.known_anchors:
            sub = self.create_subscription(
                ReassignOffer,
                f'/reassign/offer/a{aid}',
                self._on_offer,
                10,
            )
            self.offer_subs.append(sub)

        # AttachAck subscription -- this follower's per-id ack channel
        self.create_subscription(
            AttachAck, f'/attach/ack/f{self.follower_id}', self._on_ack, 10
        )

        # Watchdog tick at 10 Hz
        self.watchdog_timer = self.create_timer(0.1, self._watchdog_tick)

        self.get_logger().info(
            f'follower_node: id={self.follower_id} init_anchor={self.current_anchor} '
            f'known_anchors={self.known_anchors} t_timeout={self.t_timeout}s'
        )

    def _on_distilled(self, msg: DistilledState) -> None:
        if int(msg.uav_id) != self.current_anchor:
            return  # ignore stray messages on a wrong topic mapping
        if self.state != STATE_ATTACHED:
            return  # discard messages from dying anchor during failover
        self.last_distilled_t = time.monotonic()
        self.last_known_position = (msg.position.x, msg.position.y, msg.position.z)

    def _watchdog_tick(self) -> None:
        if self.state != STATE_ATTACHED:
            return
        elapsed = time.monotonic() - self.last_distilled_t
        if elapsed >= self.t_timeout:
            # Anchor death moment, by paper convention, is the start of
            # this 5-s silence window (last DistilledState time).
            self.t_anchor_death = self.last_distilled_t
            self.state = STATE_DETECTING
            self.offers_received = []
            self._send_reassign_request()
            # Schedule offer-collection close
            self.create_timer(self.t_offer_window, self._close_offer_window)
            self.get_logger().warning(
                f'follower {self.follower_id}: anchor {self.current_anchor} '
                f'silent {elapsed:.2f}s -- entering DETECTING'
            )

    def _send_reassign_request(self) -> None:
        msg = ReassignRequest()
        msg.timestamp = int(time.time() * 1_000_000)
        msg.follower_id = self.follower_id
        msg.last_position.x = self.last_known_position[0]
        msg.last_position.y = self.last_known_position[1]
        msg.last_position.z = self.last_known_position[2]
        msg.velocity.x = self.last_known_velocity[0]
        msg.velocity.y = self.last_known_velocity[1]
        msg.velocity.z = self.last_known_velocity[2]
        msg.battery_pct = 1.0  # not modeled in Phase 4 scope
        msg.sensor_caps = 0xF  # camera+TRN, UWB, GNSS, IMU
        self.pub_request.publish(msg)

    def _on_offer(self, msg: ReassignOffer) -> None:
        if self.state != STATE_DETECTING:
            return
        self.offers_received.append(msg)

    def _close_offer_window(self) -> None:
        if self.state != STATE_DETECTING:
            return
        if not self.offers_received:
            self.get_logger().error(
                f'follower {self.follower_id}: no offers in window, retrying'
            )
            # Retry: bump state back to ATTACHED so next tick re-fires
            self.last_distilled_t = time.monotonic() - self.t_timeout - 0.1
            self.state = STATE_ATTACHED
            return

        # F4 Selection: S_reassign = a_p/d + a_r * R + a_c * (1 - L)
        best_offer = max(self.offers_received, key=self._score)
        self.attach_target = int(best_offer.anchor_id)
        self.state = STATE_ATTACHING
        self.get_logger().info(
            f'follower {self.follower_id}: selected anchor {self.attach_target} '
            f'(score={self._score(best_offer):.3f}, considered {len(self.offers_received)})'
        )
        self._send_attach(best_offer)

    def _score(self, offer: ReassignOffer) -> float:
        dx = offer.position.x - self.last_known_position[0]
        dy = offer.position.y - self.last_known_position[1]
        dz = offer.position.z - self.last_known_position[2]
        d = max(math.sqrt(dx * dx + dy * dy + dz * dz), 0.1)
        load = 1.0 - min(offer.capacity_free / self.capacity_norm, 1.0)
        return self.alpha_prox / d + self.alpha_rep * offer.reputation + self.alpha_cap * (1.0 - load)

    def _send_attach(self, offer: ReassignOffer) -> None:
        # Reuses ReassignRequest payload per spec
        attach = ReassignRequest()
        attach.timestamp = int(time.time() * 1_000_000)
        attach.follower_id = self.follower_id
        attach.last_position.x = self.last_known_position[0]
        attach.last_position.y = self.last_known_position[1]
        attach.last_position.z = self.last_known_position[2]
        attach.velocity.x = 0.0
        attach.velocity.y = 0.0
        attach.velocity.z = 0.0
        attach.battery_pct = 1.0
        attach.sensor_caps = 0xF
        pub_attach = self.create_publisher(
            ReassignRequest, f'/attach/request/a{self.attach_target}', 10
        )
        pub_attach.publish(attach)

    def _on_ack(self, msg: AttachAck) -> None:
        if self.state != STATE_ATTACHING:
            return
        if int(msg.anchor_id) != self.attach_target:
            return
        switching_time = time.monotonic() - self.t_anchor_death
        # Publish timing for the failover_scenario_runner to log
        self.pub_timing.publish(Float64(data=float(switching_time)))
        self.get_logger().info(
            f'follower {self.follower_id}: ATTACHED to anchor {msg.anchor_id} '
            f'(switching_time={switching_time:.3f}s)'
        )
        # Switch subscription to new anchor
        self.destroy_subscription(self.sub_distilled)
        self.current_anchor = int(msg.anchor_id)
        self.sub_distilled = self.create_subscription(
            DistilledState,
            f'/anchor{self.current_anchor}/distilled_state',
            self._on_distilled,
            10,
        )
        self.last_distilled_t = time.monotonic()
        self.state = STATE_ATTACHED
        self.offers_received = []
        self.attach_target = None


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FollowerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
