"""Phase 6 task 6.1 — attrition timeline driver.

Reads a YAML/JSON attrition profile and at each scheduled `t_s` (after
the node starts) publishes an `AttritionEvent` on `/attrition/event`.
The scenario runner (Tier A Gazebo or Tier B Python MC) subscribes to
/attrition/event and implements the actual "kill" via the mechanism
appropriate to its tier (SIGKILL for Tier A processes, in-process
node destroy for Tier B).

Decoupling timing from mechanism lets the SAME orchestrator drive
both tiers without conditional code paths.

Profile format (list of dicts):
  [
    {"t_s": 30.0, "victim_uav_id": 0, "victim_role": "anchor"},
    {"t_s": 60.0, "victim_uav_id": 1, "victim_role": "anchor"},
    {"t_s": 90.0, "victim_uav_id": 7, "victim_role": "follower"}
  ]

Parameters:
  profile_json    str    JSON-encoded list as above (default "[]")
  trigger_label   str    populates AttritionEvent.trigger field
                         (default "scheduled")
  n_anchors_init  int    initial anchor count (for surviving counters)
  n_followers_init int   initial follower count
  tick_period_s   float  scheduler granularity (default 0.1)
"""
from __future__ import annotations

import json
import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import AttritionEvent


class AttritionOrchestratorNode(Node):
    def __init__(self, node_name: str = 'attrition_orchestrator_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('profile_json', '[]')
        self.declare_parameter('trigger_label', 'scheduled')
        self.declare_parameter('n_anchors_init', 0)
        self.declare_parameter('n_followers_init', 0)
        self.declare_parameter('tick_period_s', 0.1)

        profile_raw = str(self.get_parameter('profile_json').value)
        self.profile: list[dict] = json.loads(profile_raw)
        # Stable order by t_s so out-of-order entries are still
        # delivered in the right sequence.
        self.profile.sort(key=lambda e: float(e['t_s']))
        self.trigger = str(self.get_parameter('trigger_label').value)
        self.surviving_anchors = int(self.get_parameter('n_anchors_init').value)
        self.surviving_followers = int(self.get_parameter('n_followers_init').value)
        tick = float(self.get_parameter('tick_period_s').value)

        self.pub = self.create_publisher(AttritionEvent, '/attrition/event', 50)
        self.t0 = time.monotonic()
        self.create_timer(tick, self._tick)
        self.get_logger().info(
            f'attrition_orchestrator: {len(self.profile)} scheduled events, '
            f'trigger={self.trigger} init=(A={self.surviving_anchors}, '
            f'F={self.surviving_followers})'
        )

    def _tick(self) -> None:
        now = time.monotonic() - self.t0
        while self.profile and float(self.profile[0]['t_s']) <= now:
            event = self.profile.pop(0)
            role = str(event.get('victim_role', 'unknown'))
            if role == 'anchor' and self.surviving_anchors > 0:
                self.surviving_anchors -= 1
            elif role == 'follower' and self.surviving_followers > 0:
                self.surviving_followers -= 1
            msg = AttritionEvent()
            msg.timestamp = int(time.time() * 1_000_000)
            msg.victim_uav_id = int(event['victim_uav_id'])
            msg.victim_role = role
            msg.trigger = self.trigger
            msg.surviving_n_anchors = int(self.surviving_anchors)
            msg.surviving_n_followers = int(self.surviving_followers)
            self.pub.publish(msg)
            self.get_logger().warning(
                f'ATTRITION t={now:.2f}s  victim={msg.victim_uav_id} '
                f'({role})  surviving A={self.surviving_anchors} '
                f'F={self.surviving_followers}'
            )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AttritionOrchestratorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
