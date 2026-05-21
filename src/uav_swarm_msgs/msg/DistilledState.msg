# Distilled State -- paper Section IV-D (central inter-UAV broadcast).
#
# Every UAV publishes this at the broadcast cadence. Consumed by:
#   1. reputation-prior factor in each neighbour's local factor graph
#      (with sigma_j = sigma_base / (R_j + eps), sigma_base = 50 m,
#      eps = 0.01)
#   2. failover watchdog (Section IV-F, phase F1)
#   3. load-balancing broadcast (Section IV-G)

# Broadcast timestamp (microseconds since epoch)
uint64 timestamp

# Position p_j -- geodetic (lat,lon,alt)
geometry_msgs/Point position

# Velocity v_j -- body or local frame; project-wide convention TBD in
# Phase 0 item 7 (utility nodes spec)
geometry_msgs/Vector3 velocity

# Position covariance summary -- 3x3 symmetric matrix as
# [cov_xx, cov_xy, cov_xz, cov_yy, cov_yz, cov_zz]
float32[6] position_covariance

# Reputation R_j in [0, 1]
float32 reputation

# Sender UAV identifier ID_j
uint64 uav_id

# Ed25519 signature sigma_j over (timestamp || position || velocity ||
# covariance || reputation || uav_id)
uint8[64] signature_ed25519
