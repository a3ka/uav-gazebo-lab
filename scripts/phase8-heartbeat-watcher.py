#!/usr/bin/env python3
"""Phase 8 helper: subscribe to /raft/heartbeat and print each msg as
a line to stdout with controlled flush. Used by phase8-raft-trial.sh
instead of `ros2 topic echo`, which had buffering + livelinness
artefacts under leader-kill + reelection cycles.

Output format (one line per heartbeat):
    HB <unix_ts_us> leader=<id> term=<n>

Exits cleanly on SIGTERM/SIGINT or after `--max-seconds`.
"""
from __future__ import annotations

import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

from uav_swarm_msgs.msg import RaftHeartbeat


# Match raft_node._HB_QOS exactly so subscriber doesn't fall back to
# default RELIABLE and queue stale heartbeats.
_HB_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST, depth=1,
)


class HeartbeatWatcher(Node):
    def __init__(self) -> None:
        super().__init__('phase8_heartbeat_watcher')
        self.create_subscription(
            RaftHeartbeat, '/raft/heartbeat', self._cb, _HB_QOS
        )

    def _cb(self, msg: RaftHeartbeat) -> None:
        print(
            f'HB {int(time.time() * 1_000_000)} '
            f'leader={int(msg.leader_id)} term={int(msg.term)}',
            flush=True,
        )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--max-seconds', type=float, default=60.0)
    args = p.parse_args()

    rclpy.init()
    node = HeartbeatWatcher()
    deadline = time.monotonic() + args.max_seconds
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
