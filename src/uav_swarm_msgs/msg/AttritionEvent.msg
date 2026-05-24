# Phase 6 attrition event broadcast by attrition_orchestrator_node.
# Lets load_monitor_node timestamp the kill moment and lets
# downstream analyzers (re-balance latency, time-over-capacity) align
# their per-event windows.
#
#   victim_uav_id    the UAV that was just killed
#   victim_role      "anchor" | "follower" (string)
#   trigger          "scheduled" | "stress" | "manual" -- Phase 6 is
#                    always "scheduled"; Phase 7+ may add others
#   surviving_n_anchors    count after this event (informational)
#   surviving_n_followers  count after this event (informational)
uint64 timestamp
uint64 victim_uav_id
string victim_role
string trigger
uint32 surviving_n_anchors
uint32 surviving_n_followers
