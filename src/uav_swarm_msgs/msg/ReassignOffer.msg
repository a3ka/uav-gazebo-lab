# Failover phase F3 -- paper Section IV-F.
#
# Broadcast by surviving anchors in response to a ReassignRequest.
# Each follower collects offers for T_offer_window = 1 s, then runs
# the selection formula:
#   S_reassign = alpha_prox / d + alpha_rep * R + alpha_cap * (1 - L)
# with defaults (alpha_prox, alpha_rep, alpha_cap) = (0.4, 0.35, 0.25).
# d = Euclidean distance follower -> anchor,
# L = current_followers / target_capacity in [0, 1].

# When the offer was emitted (microseconds since epoch)
uint64 timestamp

# Identifier of the offering anchor
uint64 anchor_id

# Anchor's current position
geometry_msgs/Point position

# Anchor's current reputation, in [0, 1]
float32 reputation

# Followers the anchor can still accept (target_capacity - current).
# Encoded as count; the follower normalises against the swarm-wide
# target_capacity constant to obtain L in the selection formula.
uint32 capacity_free
