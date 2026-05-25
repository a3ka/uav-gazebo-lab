"""Phase 8 minimal Raft baseline node.

Implements just enough Raft to do leader-election and measure
recovery time after the leader is killed. NO log replication, NO
membership changes -- only the failover-time comparable claim
matters for Phase 8.

State machine:
  FOLLOWER  (default)
    on heartbeat_recv: reset election timer, term = max(term, msg.term)
    on election_timer: become CANDIDATE, term += 1, vote for self,
                       broadcast VoteRequest
    on vote_req(term>=mine): grant if not voted-this-term
  CANDIDATE
    on majority grants: become LEADER, start heartbeat
    on higher-term heartbeat: become FOLLOWER (someone else won)
    on election_timer: re-call election (term += 1)
  LEADER
    every heartbeat_period: broadcast Heartbeat(term=mine, leader=self)
    on higher-term heartbeat: become FOLLOWER (we lost)

Parameters:
  node_id           int     this Raft member's id
  n_members         int     total number of members (for quorum calc)
  election_timeout_s float  default 5.0  -- match Phase 4 watchdog
  heartbeat_period_s float  default 1.0
  jitter_max_s       float  default 1.0  -- randomized to break ties
  seed              int     default 0    -- 0 => non-deterministic

Topics:
  /raft/heartbeat   pub by current leader
  /raft/vote/req    pub by candidate
  /raft/vote/grant  pub by voter; (voter, candidate, grant) tuple

Phase 8 timing output: publishes Float64 on /raft/leader_change/n<id>
with the t_become_leader timestamp each time THIS node enters LEADER.
The scenario runner subscribes to all and computes recovery time.
"""
from __future__ import annotations

import random
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Float64

from uav_swarm_msgs.msg import RaftHeartbeat, RaftVoteGrant, RaftVoteRequest


# BEST_EFFORT + depth 1 on the heartbeat channel: when the leader
# dies, no buffered heartbeats should keep arriving at survivors and
# resetting their election timer. RELIABLE-default left up to ~100
# msgs queued, making the cluster appear "still has leader" for tens
# of seconds after the actual leader process exited -- survivors
# never silence-detected.
_HB_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST, depth=1,
)


STATE_FOLLOWER = 'F'
STATE_CANDIDATE = 'C'
STATE_LEADER = 'L'


class RaftNode(Node):
    def __init__(self, node_name: str = 'raft_node', **kwargs) -> None:
        super().__init__(node_name, **kwargs)

        self.declare_parameter('node_id', 0)
        self.declare_parameter('n_members', 5)
        self.declare_parameter('election_timeout_s', 5.0)
        self.declare_parameter('heartbeat_period_s', 1.0)
        self.declare_parameter('jitter_max_s', 1.0)
        self.declare_parameter('seed', 0)
        # Byzantine attack mode (Phase 8 capability-gap comparison).
        # When true, this node CONSTANTLY broadcasts heartbeat with
        # leader_id = self regardless of its actual Raft state, term,
        # or vote history. Mimics a Byzantine "leader-claimer" that
        # tries to monopolise cluster leadership. Raft has no mechanism
        # to challenge heartbeat authenticity; honest survivors see
        # this stream and their election timer never expires.
        self.declare_parameter('byzantine', False)

        self.id = int(self.get_parameter('node_id').value)
        self.n_members = int(self.get_parameter('n_members').value)
        self.election_timeout = float(self.get_parameter('election_timeout_s').value)
        self.heartbeat_period = float(self.get_parameter('heartbeat_period_s').value)
        self.jitter_max = float(self.get_parameter('jitter_max_s').value)
        seed = int(self.get_parameter('seed').value)
        self.rng = random.Random(seed) if seed else random.Random()
        self.byzantine = bool(self.get_parameter('byzantine').value)

        self.state = STATE_FOLLOWER
        self.term = 0
        self.voted_for_term: dict[int, int] = {}   # term -> candidate
        self.votes_received: set[int] = set()
        self.last_heartbeat_t = time.monotonic()
        self.next_election_t = self._compute_next_election_t()

        self.create_subscription(RaftHeartbeat, '/raft/heartbeat',
                                 self._on_heartbeat, _HB_QOS)
        self.create_subscription(RaftVoteRequest, '/raft/vote/req',
                                 self._on_vote_req, 50)
        self.create_subscription(RaftVoteGrant, '/raft/vote/grant',
                                 self._on_vote_grant, 50)

        self.pub_heartbeat = self.create_publisher(
            RaftHeartbeat, '/raft/heartbeat', _HB_QOS
        )
        self.pub_vote_req = self.create_publisher(RaftVoteRequest, '/raft/vote/req', 50)
        self.pub_vote_grant = self.create_publisher(RaftVoteGrant, '/raft/vote/grant', 50)
        # Per-node "I became leader at this monotonic time" channel
        self.pub_leader = self.create_publisher(
            Float64, f'/raft/leader_change/n{self.id}', 10
        )

        self.create_timer(0.05, self._tick)
        self.get_logger().info(
            f'raft_node {self.id}: n={self.n_members} '
            f't_election={self.election_timeout}s hb={self.heartbeat_period}s'
        )

    def _compute_next_election_t(self) -> float:
        return time.monotonic() + self.election_timeout + self.rng.uniform(0, self.jitter_max)

    def _on_heartbeat(self, msg: RaftHeartbeat) -> None:
        if int(msg.leader_id) == self.id:
            return  # ignore own heartbeat
        if int(msg.term) < self.term:
            return  # stale leader
        self.term = int(msg.term)
        self.last_heartbeat_t = time.monotonic()
        self.next_election_t = self._compute_next_election_t()
        if self.state in (STATE_CANDIDATE, STATE_LEADER):
            self.state = STATE_FOLLOWER  # stepped down

    def _on_vote_req(self, msg: RaftVoteRequest) -> None:
        if int(msg.candidate_id) == self.id:
            return
        cand_term = int(msg.term)
        if cand_term < self.term:
            self._send_grant(int(msg.candidate_id), cand_term, False)
            return
        # New-term election overrides any leader / candidate state
        if cand_term > self.term:
            self.term = cand_term
            self.state = STATE_FOLLOWER
        already_voted = self.voted_for_term.get(cand_term)
        if already_voted is None:
            self.voted_for_term[cand_term] = int(msg.candidate_id)
            self._send_grant(int(msg.candidate_id), cand_term, True)
            self.last_heartbeat_t = time.monotonic()
            self.next_election_t = self._compute_next_election_t()
        else:
            self._send_grant(int(msg.candidate_id), cand_term,
                             already_voted == int(msg.candidate_id))

    def _send_grant(self, candidate_id: int, term: int, grant: bool) -> None:
        g = RaftVoteGrant()
        g.timestamp = int(time.time() * 1_000_000)
        g.voter_id = self.id
        g.candidate_id = candidate_id
        g.term = term
        g.grant = grant
        self.pub_vote_grant.publish(g)

    def _on_vote_grant(self, msg: RaftVoteGrant) -> None:
        if self.state != STATE_CANDIDATE:
            return
        if int(msg.candidate_id) != self.id or int(msg.term) != self.term:
            return
        if not msg.grant:
            return
        self.votes_received.add(int(msg.voter_id))
        # Majority quorum incl. self (own vote in candidate transition)
        if len(self.votes_received) >= (self.n_members // 2 + 1):
            self._become_leader()

    def _become_leader(self) -> None:
        self.state = STATE_LEADER
        self.pub_leader.publish(Float64(data=time.monotonic()))
        self.get_logger().info(
            f'raft_node {self.id}: BECAME LEADER (term={self.term}, '
            f'votes={len(self.votes_received)}/{self.n_members})'
        )
        self._broadcast_heartbeat()

    def _broadcast_heartbeat(self) -> None:
        hb = RaftHeartbeat()
        hb.timestamp = int(time.time() * 1_000_000)
        hb.leader_id = self.id
        hb.term = self.term
        self.pub_heartbeat.publish(hb)
        self.last_heartbeat_t = time.monotonic()

    def _start_election(self) -> None:
        self.term += 1
        self.state = STATE_CANDIDATE
        self.votes_received = {self.id}     # vote for self
        self.voted_for_term[self.term] = self.id
        req = RaftVoteRequest()
        req.timestamp = int(time.time() * 1_000_000)
        req.candidate_id = self.id
        req.term = self.term
        self.pub_vote_req.publish(req)
        self.next_election_t = self._compute_next_election_t()
        self.get_logger().info(
            f'raft_node {self.id}: starting election (term={self.term})'
        )

    def _tick(self) -> None:
        now = time.monotonic()
        # Byzantine: lie about being leader regardless of state. Honest
        # subscribers reset their election timer on every fake
        # heartbeat -> cluster cannot elect an honest leader.
        if self.byzantine:
            if now - self.last_heartbeat_t >= self.heartbeat_period:
                # Fake term=1 (or always one above what we last saw, but
                # term=1 is enough to mimic "rightful initial leader").
                hb = RaftHeartbeat()
                hb.timestamp = int(time.time() * 1_000_000)
                hb.leader_id = self.id
                hb.term = max(self.term, 1)
                self.pub_heartbeat.publish(hb)
                self.last_heartbeat_t = now
            return
        if self.state == STATE_LEADER:
            if now - self.last_heartbeat_t >= self.heartbeat_period:
                self._broadcast_heartbeat()
        else:
            if now >= self.next_election_t:
                self._start_election()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RaftNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
