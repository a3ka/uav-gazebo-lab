# Phase 8 minimal Raft vote grant. Voter publishes on
# /raft/vote/grant for the candidate it grants its vote to.
# `grant=true` for affirmative, `grant=false` (term reject / already
# voted) for negative.
uint64 timestamp
uint64 voter_id
uint64 candidate_id
uint64 term
bool grant
