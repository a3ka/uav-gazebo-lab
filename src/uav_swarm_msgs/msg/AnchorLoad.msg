# Phase 6 anchor load report. Anchors broadcast their current load
# at the DistilledState rate so the load_monitor can compute
# time-over-capacity and re-balance latency per attrition event.
#
#   target_capacity  the static max followers per the paper's IV-F
#                    setup. Phase 4 already accepts this as a param.
#   n_attached       current follower count actually attached
#   over_capacity    bool flag (n_attached > target_capacity)
uint64 timestamp
uint64 anchor_id
uint32 target_capacity
uint32 n_attached
bool over_capacity
