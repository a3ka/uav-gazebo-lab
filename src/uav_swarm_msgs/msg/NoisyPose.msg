# Pose with a single noise scalar -- paper Section IV-D / IV-E.
#
# Used by the position relay path (multi-hop sigma cascade) and as the
# light-weight intra-test broadcast pose for utility nodes
# (position_broadcaster_node, uwb_ranging_simulator_node) in Phase 0
# item 7.
#
# For factor-graph priors prefer DistilledState (which carries full
# covariance). NoisyPose is for relay / observation-style uses where
# only the isotropic 1-D sigma is meaningful.

# Sample timestamp (microseconds since epoch)
uint64 timestamp

# Source UAV identifier
uint64 uav_id

# Position (geodetic or local frame -- chosen per scenario)
geometry_msgs/Point position

# Scalar noise estimate sigma (metres). For anchors:
# sigma ~ sigma_base/(R+eps); for relay hop k:
# sigma_k = sigma_anchor * (1+delta)^k under the paper-stated GDOP
# bound (refit empirically in Phase 3).
float32 sigma
