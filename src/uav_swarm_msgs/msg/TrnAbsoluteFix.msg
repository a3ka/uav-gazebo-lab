# Terrain-Referenced Navigation absolute position fix -- paper Section IV-D.
#
# Emitted by trn_anchor_node every t_trn seconds (paper default 0.1 Hz)
# after matching the anchor's camera against a staged satellite tile
# via the Phase 1-validated PoO pipeline. The factor_graph_node
# consumes this as a tight PriorFactorPoint3 on the anchor's key,
# overwriting the wide self-prior used between TRN fixes.
#
# Phase 3 MVP: trn_anchor_node bypasses the camera+SuperPoint pipeline
# and just adds Gaussian noise to ground-truth position (sigma_trn ~ 5 m).
# Phase 1 already validated PoO inference quality (AUC=0.9996,
# FRR=4.6%); Phase 6+ will swap in real Gazebo camera capture.

# Sample timestamp (microseconds since epoch)
uint64 timestamp

# UAV reporting the fix (must be an anchor)
uint64 uav_id

# TRN-estimated absolute position
geometry_msgs/Point position

# 1-sigma noise of the fix (metres). Paper Section IV-D doesn't pin
# this explicitly; typical TRN with sub-pixel SuperPoint matching ~5 m
# CEP at flight altitudes 100-300 m AGL.
float32 sigma_m
