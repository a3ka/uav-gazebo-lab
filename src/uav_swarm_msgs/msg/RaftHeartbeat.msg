# Phase 8 minimal Raft baseline heartbeat (paper Pillar 4 vs SwarmRaft
# comparison). Sent by the current leader at fixed interval; on
# silence > election_timeout, followers become candidates and call a
# vote.
uint64 timestamp
uint64 leader_id
uint64 term
