# Factor-graph output -- per-UAV navigation estimate.
#
# Emitted by factor_graph_node after each iSAM2 fixed-lag smoother
# update. Phase 3 scenario_runner subscribes to this AND to ground
# truth (synthetic), computes per-trial CEP_50 / CEP_95 grouped by
# hop_depth + active_anchor_count for the Prop CEP claim.
#
# In Phase 6+ this same message will feed downstream control / Pillar 6
# load-balancing decisions.

# When the estimate was finalised (microseconds since epoch)
uint64 timestamp

# UAV whose pose this is
uint64 uav_id

# MAP-estimated position in the local frame (Phase 3 uses ENU; Phase 6+
# will switch to geodetic when integrating PX4)
geometry_msgs/Point position

# Position covariance as 3x3 symmetric, flattened lower-triangular:
# [cov_xx, cov_xy, cov_xz, cov_yy, cov_yz, cov_zz]
# (matches DistilledState.position_covariance convention so downstream
# nodes can treat both interchangeably)
float32[6] position_covariance

# Hop depth from the nearest TRN-equipped anchor at sample time.
# Anchors report 0; followers report their topological distance. Phase
# 3 analysis groups CEP measurements by this field.
uint32 n_hops_from_anchor

# How many active (non-excluded, R > T_reject) anchors contributed
# absolute-position factors to this graph at sample time. Used for the
# multi-anchor-fusion ablation in Phase 7.
uint32 n_active_anchors
