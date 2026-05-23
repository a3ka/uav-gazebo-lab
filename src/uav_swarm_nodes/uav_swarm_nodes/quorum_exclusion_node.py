"""Phase 2 quorum exclusion node -- paper Section IV-F end.

Per-UAV. Subscribes to:
  - /distilled_state (broadcast) -- tracks each peer's OWN R, needed to
    qualify voters (only voters with R > T_quorum count)
  - /reputation/view (broadcast) -- aggregates per-voter views of every
    target peer's reputation

Exclusion rule: when M >= M_quorum (default 3) distinct voters, each
with own R > T_quorum (0.60), report a target's R < T_reject (0.20),
emit an ExclusionEvent on /phase2/exclusions/u<my_id>.

Each target only excluded once per node lifetime (idempotent). The
emitted timestamp is the moment the M-th qualifying vote landed,
which is what Phase 2 analysis uses to compute exclusion time per
Prop 3.

Parameters:
  uav_id      (int)   default 0
  m_quorum    (int)   default 3   -- M voters required
  t_reject    (float) default 0.20
  t_quorum    (float) default 0.60
  tick_rate   (float) default 5.0 Hz -- periodic recompute (also fires
                                       on new view, but tick catches
                                       cases where voter's own R rises
                                       above T_quorum after the view
                                       was received)
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import (
    DistilledState,
    ExclusionEvent,
    PeerReputationView,
)


class QuorumExclusionNode(Node):
    def __init__(self) -> None:
        super().__init__('quorum_exclusion_node')

        self.declare_parameter('uav_id', 0)
        self.declare_parameter('m_quorum', 3)
        self.declare_parameter('t_reject', 0.20)
        self.declare_parameter('t_quorum', 0.60)
        self.declare_parameter('tick_rate', 5.0)

        self.uav_id = int(self.get_parameter('uav_id').value)
        self.m_quorum = int(self.get_parameter('m_quorum').value)
        self.t_reject = float(self.get_parameter('t_reject').value)
        self.t_quorum = float(self.get_parameter('t_quorum').value)
        rate = float(self.get_parameter('tick_rate').value)

        # voter_own_R[voter_id] -> last seen own R (from DistilledState)
        self.voter_own_r: dict[int, float] = {}
        # views[target_id][voter_id] -> last reported r_value
        self.views: dict[int, dict[int, float]] = {}
        # Targets already excluded by THIS node (avoid duplicate events)
        self.excluded: set[int] = set()

        self.create_subscription(DistilledState, '/distilled_state', self._on_state, 20)
        self.create_subscription(PeerReputationView, '/reputation/view', self._on_view, 50)

        self.pub_exclusion = self.create_publisher(
            ExclusionEvent, f'/phase2/exclusions/u{self.uav_id}', 10
        )

        self.tick_timer = self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info(
            f'quorum_exclusion_node: uav_id={self.uav_id} '
            f'M={self.m_quorum} T_reject={self.t_reject} '
            f'T_quorum={self.t_quorum} tick={rate}Hz'
        )

    # ─── callbacks ────────────────────────────────────────────────────

    def _on_state(self, msg: DistilledState) -> None:
        self.voter_own_r[int(msg.uav_id)] = float(msg.reputation)

    def _on_view(self, msg: PeerReputationView) -> None:
        voter = int(msg.voter_id)
        target = int(msg.target_id)
        if voter == self.uav_id:
            return  # don't count our own broadcasts
        self.views.setdefault(target, {})[voter] = float(msg.r_value)

    # ─── exclusion check ─────────────────────────────────────────────

    def _tick(self) -> None:
        for target, per_voter in list(self.views.items()):
            if target in self.excluded:
                continue
            qualified: list[tuple[int, float]] = []
            voter_self_min = 1.0
            for voter, r_view in per_voter.items():
                own_r = self.voter_own_r.get(voter, 0.0)
                if own_r > self.t_quorum and r_view < self.t_reject:
                    qualified.append((voter, own_r))
                    if own_r < voter_self_min:
                        voter_self_min = own_r
            if len(qualified) >= self.m_quorum:
                self._emit(target, qualified, voter_self_min)

    def _emit(self, target: int, qualified: list[tuple[int, float]], voter_self_min: float) -> None:
        ev = ExclusionEvent()
        ev.timestamp = int(time.time() * 1_000_000)
        ev.target_id = target
        ev.voter_ids = [v for v, _ in qualified]
        ev.voter_min_r = float(voter_self_min)
        self.pub_exclusion.publish(ev)
        self.excluded.add(target)
        self.get_logger().warning(
            f'EXCLUSION target={target} via voters={ev.voter_ids} '
            f'min_voter_R={voter_self_min:.3f}'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = QuorumExclusionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
