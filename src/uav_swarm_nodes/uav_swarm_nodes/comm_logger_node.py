"""Phase 0 utility node: log subscribed-topic byte sizes and send rates.

Used for Phase 0 item 10 -- empirical comm-complexity check against the
paper's claimed ~185 B per message and ~13.3 kbit/s aggregate per UAV.

Parameters:
  topic         (string)  required        -- ROS2 topic to subscribe to
  msg_type      (string)  required        -- 'pkg/msg/MsgName'
  report_period (float)   default 5.0     -- seconds between stat dumps

Counters: messages received, bytes accumulated (over the wire after
DDS-level CDR serialise; computed via rclpy.serialization).
"""

import time

import rclpy
from rclpy.node import Node
from rclpy.serialization import serialize_message
from rosidl_runtime_py.utilities import get_message


class CommLoggerNode(Node):
    def __init__(self) -> None:
        super().__init__('comm_logger_node')

        self.declare_parameter('topic', '')
        self.declare_parameter('msg_type', '')
        self.declare_parameter('report_period', 5.0)

        topic = str(self.get_parameter('topic').value).strip()
        msg_type_str = str(self.get_parameter('msg_type').value).strip()
        self.report_period = float(self.get_parameter('report_period').value)

        if not topic or not msg_type_str:
            raise RuntimeError(
                'comm_logger_node requires both `topic` and `msg_type` params, '
                "e.g. msg_type='uav_swarm_msgs/msg/NoisyPose'"
            )

        try:
            msg_cls = get_message(msg_type_str)
        except (LookupError, ValueError) as exc:
            raise RuntimeError(f'Cannot resolve msg type {msg_type_str!r}: {exc}') from exc

        self.count = 0
        self.bytes_total = 0
        self.window_start = time.monotonic()
        self.sub = self.create_subscription(msg_cls, topic, self._cb, 10)
        self.timer = self.create_timer(self.report_period, self._report)

        self.get_logger().info(
            f"comm_logger_node: topic={topic} msg_type={msg_type_str} "
            f"report_period={self.report_period}s"
        )

    def _cb(self, msg) -> None:
        self.count += 1
        self.bytes_total += len(serialize_message(msg))

    def _report(self) -> None:
        now = time.monotonic()
        dt = max(now - self.window_start, 1e-6)
        rate_msg_s = self.count / dt
        avg_bytes = (self.bytes_total / self.count) if self.count else 0.0
        bits_per_s = (self.bytes_total * 8) / dt
        self.get_logger().info(
            f"window={dt:.2f}s  msgs={self.count}  rate={rate_msg_s:.2f}/s  "
            f"avg_msg={avg_bytes:.1f}B  throughput={bits_per_s:.1f}bit/s "
            f"({bits_per_s / 1024.0:.2f} kbit/s)"
        )
        self.count = 0
        self.bytes_total = 0
        self.window_start = now


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CommLoggerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
