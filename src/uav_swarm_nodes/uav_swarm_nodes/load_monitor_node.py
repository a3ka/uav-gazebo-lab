"""Phase 6 task 6.3 — per-trial load timeline + attrition log.

Subscribes:
  /anchor/load          (AnchorLoad) -- one anchor per tick at the
                        DistilledState rate
  /attrition/event      (AttritionEvent) -- broadcast by
                        attrition_orchestrator_node

Writes:
  output CSV file with one row per AnchorLoad sample:
    t_rel_s, anchor_id, target_capacity, n_attached, over_capacity
  plus interleaved rows for attrition events:
    t_rel_s, victim_id, victim_role, surviving_n_anchors,
    surviving_n_followers
  (the two row types share a 't_rel_s' column and are distinguished
  by 'kind' column: 'load' | 'attrition')

Designed for batch analysis (phase6-analyze.py): the CSV is the only
persisted artefact. The node is otherwise stateless beyond its
output file handle.

Parameters:
  out_csv         str    path to write CSV. Required (will overwrite).
  flush_every_n   int    fflush every N rows (default 50). Lower
                         values reduce data loss if the trial crashes.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import rclpy
from rclpy.node import Node

from uav_swarm_msgs.msg import AnchorLoad, AttritionEvent


class LoadMonitorNode(Node):
    COLUMNS = [
        'kind', 't_rel_s', 'anchor_id', 'target_capacity', 'n_attached',
        'over_capacity', 'victim_id', 'victim_role',
        'surviving_n_anchors', 'surviving_n_followers',
    ]

    def __init__(self, node_name: str = 'load_monitor_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)
        self.declare_parameter('out_csv', '')
        self.declare_parameter('flush_every_n', 50)

        out = str(self.get_parameter('out_csv').value)
        if not out:
            raise ValueError('out_csv parameter is required')
        self.out_path = Path(out)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.out_path.open('w', newline='')
        self._csv = csv.DictWriter(self._fh, fieldnames=self.COLUMNS)
        self._csv.writeheader()
        self._flush_every = int(self.get_parameter('flush_every_n').value)
        self._rows_since_flush = 0
        self._t0 = time.monotonic()

        self.create_subscription(AnchorLoad, '/anchor/load', self._on_load, 100)
        self.create_subscription(
            AttritionEvent, '/attrition/event', self._on_attrition, 50
        )
        self.get_logger().info(f'load_monitor: writing to {self.out_path}')

    def destroy_node(self) -> bool:
        try:
            self._fh.flush()
            self._fh.close()
        except Exception:
            pass
        return super().destroy_node()

    def _t(self) -> float:
        return time.monotonic() - self._t0

    def _write(self, row: dict) -> None:
        self._csv.writerow(row)
        self._rows_since_flush += 1
        if self._rows_since_flush >= self._flush_every:
            self._fh.flush()
            self._rows_since_flush = 0

    def _on_load(self, msg: AnchorLoad) -> None:
        self._write({
            'kind': 'load', 't_rel_s': round(self._t(), 4),
            'anchor_id': int(msg.anchor_id),
            'target_capacity': int(msg.target_capacity),
            'n_attached': int(msg.n_attached),
            'over_capacity': int(bool(msg.over_capacity)),
            'victim_id': '', 'victim_role': '',
            'surviving_n_anchors': '', 'surviving_n_followers': '',
        })

    def _on_attrition(self, msg: AttritionEvent) -> None:
        self._write({
            'kind': 'attrition', 't_rel_s': round(self._t(), 4),
            'anchor_id': '', 'target_capacity': '', 'n_attached': '',
            'over_capacity': '',
            'victim_id': int(msg.victim_uav_id),
            'victim_role': str(msg.victim_role),
            'surviving_n_anchors': int(msg.surviving_n_anchors),
            'surviving_n_followers': int(msg.surviving_n_followers),
        })
        self._fh.flush()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LoadMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
