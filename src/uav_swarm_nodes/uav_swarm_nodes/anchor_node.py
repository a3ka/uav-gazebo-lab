"""Phase 4 anchor node -- paper Section IV-F.

Behaviours:
  * Publishes DistilledState every 100 ms on /anchor<id>/distilled_state
  * Listens for ReassignRequest on /reassign/request; responds with
    ReassignOffer on /reassign/offer/<my_id>
  * Listens for ATTACH on /attach/request/<my_id> (reusing
    ReassignRequest payload per spec), increments follower count,
    responds with AttachAck on /attach/ack/<follower_id>

Scenario hooks (for failover_scenario_runner):
  * publish_rate param can be changed at runtime via parameter event
    callback to simulate slow degradation (scenario S2).
  * reputation param can be forced to a low value to simulate
    rejection-driven failover (scenario S5).

Parameters:
  anchor_id          (int)   default 0
  initial_position   (float[3]) default [0,0,50]
  target_capacity    (int)   default 5
  reputation         (float) default 0.8
  publish_rate       (float) default 10.0  (Hz)
"""

import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import (
    AnchorLoad,
    AttachAck,
    DistilledState,
    ReassignOffer,
    ReassignRequest,
)


class AnchorNode(Node):
    def __init__(self, node_name: str = 'anchor_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('anchor_id', 0)
        self.declare_parameter('initial_position', [0.0, 0.0, 50.0])
        self.declare_parameter('target_capacity', 5)
        self.declare_parameter('reputation', 0.8)
        self.declare_parameter('publish_rate', 10.0)

        self.anchor_id = int(self.get_parameter('anchor_id').value)
        ip = self.get_parameter('initial_position').value
        self.pos_x, self.pos_y, self.pos_z = float(ip[0]), float(ip[1]), float(ip[2])
        self.target_capacity = int(self.get_parameter('target_capacity').value)
        self.reputation = float(self.get_parameter('reputation').value)
        rate = float(self.get_parameter('publish_rate').value)

        self.followers_attached: set[int] = set()
        # Cache per-follower ATTACH_ACK publishers. Without this, each
        # ATTACH_REQUEST callback created a fresh local publisher that
        # could be GC'd before DDS delivered the msg -- and the per-
        # follower discovery storm at N>=100 brought mission-survival
        # to ~1-5% (Phase 6 N=200 sweep result).
        self._ack_pubs: dict[int, 'rclpy.publisher.Publisher'] = {}

        # Publishers
        # Note: ROS2 topic-segment validator rejects segments that start with
        # a digit, so we prefix the anchor id with 'a' and the follower id
        # with 'f' everywhere they appear in topic names.
        self.pub_distilled = self.create_publisher(
            DistilledState, f'/anchor{self.anchor_id}/distilled_state', 10
        )
        self.pub_offer = self.create_publisher(
            ReassignOffer, f'/reassign/offer/a{self.anchor_id}', 10
        )
        # Phase 6 load broadcast -- piggybacked on the DistilledState
        # timer so load_monitor_node gets a sample at the same rate.
        self.pub_load = self.create_publisher(
            AnchorLoad, '/anchor/load', 50
        )

        # Subscribers
        self.create_subscription(
            ReassignRequest, '/reassign/request', self._on_reassign_request, 10
        )
        self.create_subscription(
            ReassignRequest,
            f'/attach/request/a{self.anchor_id}',
            self._on_attach_request,
            10,
        )

        # Periodic DistilledState
        self.distilled_timer = self.create_timer(1.0 / rate, self._publish_distilled)

        # Reputation can change at runtime (scenario S5)
        self.add_on_set_parameters_callback(self._param_cb)

        self.get_logger().info(
            f'anchor_node: id={self.anchor_id} pos=({self.pos_x},{self.pos_y},{self.pos_z}) '
            f'target_capacity={self.target_capacity} reputation={self.reputation} rate={rate}Hz'
        )

    def _publish_distilled(self) -> None:
        msg = DistilledState()
        msg.timestamp = int(time.time() * 1_000_000)
        msg.position.x = self.pos_x
        msg.position.y = self.pos_y
        msg.position.z = self.pos_z
        # Velocity stays zero -- nominal static anchor for Phase 4 scope
        msg.position_covariance = [4.0, 0.0, 0.0, 4.0, 0.0, 1.0]
        msg.reputation = self.reputation
        msg.uav_id = self.anchor_id
        # signature_ed25519 left zero -- crypto wiring lives in Phase 2
        self.pub_distilled.publish(msg)
        # Phase 6 load broadcast (one per tick)
        load = AnchorLoad()
        load.timestamp = msg.timestamp
        load.anchor_id = self.anchor_id
        load.target_capacity = self.target_capacity
        load.n_attached = len(self.followers_attached)
        load.over_capacity = (load.n_attached > load.target_capacity)
        self.pub_load.publish(load)

    def _on_reassign_request(self, msg: ReassignRequest) -> None:
        capacity_free = max(0, self.target_capacity - len(self.followers_attached))
        if capacity_free == 0:
            return  # Politely silent when full
        offer = ReassignOffer()
        offer.timestamp = int(time.time() * 1_000_000)
        offer.anchor_id = self.anchor_id
        offer.position.x = self.pos_x
        offer.position.y = self.pos_y
        offer.position.z = self.pos_z
        offer.reputation = self.reputation
        offer.capacity_free = capacity_free
        self.pub_offer.publish(offer)
        self.get_logger().info(
            f'anchor {self.anchor_id}: offered to follower {msg.follower_id} '
            f'(capacity_free={capacity_free}, R={self.reputation:.2f})'
        )

    def _on_attach_request(self, msg: ReassignRequest) -> None:
        fid = int(msg.follower_id)
        # Admission control (Phase 6 thundering-herd fix): refuse the
        # attach if accepting would push n_attached above target_capacity.
        # Idempotent re-attach of an already-attached follower is OK and
        # ALWAYS accepted (capacity invariant unchanged). Refused
        # followers will retry via their ATTACH-timeout path and pick the
        # next-best offer.
        if (fid not in self.followers_attached
                and len(self.followers_attached) >= self.target_capacity):
            self.get_logger().info(
                f'anchor {self.anchor_id}: REFUSED attach from follower {fid} '
                f'(full at {len(self.followers_attached)}/{self.target_capacity})'
            )
            return
        self.followers_attached.add(fid)
        ack = AttachAck()
        ack.timestamp = int(time.time() * 1_000_000)
        ack.anchor_id = self.anchor_id
        ack.follower_id = fid
        ack.confirmed_position.x = msg.last_position.x
        ack.confirmed_position.y = msg.last_position.y
        ack.confirmed_position.z = msg.last_position.z
        ack.confirmed_covariance = [4.0, 0.0, 0.0, 4.0, 0.0, 1.0]
        # Per-follower ack channel ('f' prefix for ROS2 topic name validity).
        # Publisher is CACHED -- creating one per request triggered a
        # DDS discovery storm + local-publisher GC race at N>=100.
        if fid not in self._ack_pubs:
            self._ack_pubs[fid] = self.create_publisher(
                AttachAck, f'/attach/ack/f{fid}', 10
            )
        self._ack_pubs[fid].publish(ack)
        self.get_logger().info(
            f'anchor {self.anchor_id}: ATTACH_ACK -> follower {fid} '
            f'(attached={len(self.followers_attached)}/{self.target_capacity})'
        )

    def _param_cb(self, params):
        from rcl_interfaces.msg import SetParametersResult
        for p in params:
            if p.name == 'reputation':
                self.reputation = float(p.value)
                self.get_logger().info(f'reputation set -> {self.reputation:.2f}')
            elif p.name == 'publish_rate':
                rate = float(p.value)
                # ALWAYS tear down the old timer first. The previous
                # `if rate > 0` guard left the prior timer running when
                # rate=0 was set (scenarios S2/S3), so the anchor kept
                # publishing and the follower's silence watchdog never
                # fired.
                if self.distilled_timer is not None:
                    self.distilled_timer.destroy()
                    self.distilled_timer = None
                if rate > 0:
                    self.distilled_timer = self.create_timer(
                        1.0 / rate, self._publish_distilled
                    )
                    self.get_logger().info(f'publish_rate set -> {rate}Hz')
                else:
                    self.get_logger().info('publish_rate set -> 0 (silenced)')
        return SetParametersResult(successful=True)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AnchorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
