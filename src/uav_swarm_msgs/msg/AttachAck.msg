# Failover phase F5 -- paper Section IV-F.
#
# After Selection (F4) the follower sends an ATTACH (we re-use
# ReassignRequest payload on /attach/request/<anchor_id> for that step;
# no separate message). The anchor confirms with AttachAck on
# /attach/ack/<follower_id>. Switching time = (AttachAck arrival) -
# (anchor death moment). Must be < 10 s for Pillar 4 to hold.

# When the ack was emitted (microseconds since epoch)
uint64 timestamp

# Identifier of the accepting anchor
uint64 anchor_id

# Identifier of the follower being attached
uint64 follower_id

# Confirmed position the anchor places the follower at -- this becomes
# the seed pose for the follower's continued navigation
geometry_msgs/Point confirmed_position

# Confirmed position covariance, lower-triangular 3x3:
# [cov_xx, cov_xy, cov_xz, cov_yy, cov_yz, cov_zz]
float32[6] confirmed_covariance
