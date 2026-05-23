# Phase 5 GNSS spoofing alert published by spoof_detector_node.
# Paper Pillar 5: spoofing detection via UWB cross-verification.
#
#   suspect_uav_id   the UAV whose reported (GNSS) position disagrees
#                    with UWB ranges to its peers
#   n_suspicious_pairs   how many peer pairs (i, neighbour) had
#                    |range - predicted| > T_spoof in the current window
#   max_residual_m   largest |range - predicted| observed for the suspect
uint64 timestamp
uint64 suspect_uav_id
uint32 n_suspicious_pairs
float32 max_residual_m
