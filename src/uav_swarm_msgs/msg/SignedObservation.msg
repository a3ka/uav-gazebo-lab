# Visual Proof of Observation (PoO) -- paper Section IV-B.
#
# Broadcast by an honest UAV after a TRN fix; verified by a neighbour
# that physically revisits the same location within r_verify = 500 m.
# A receiving UAV updates the sender's reputation per Section IV-C based
# on the verification outcome.
#
# Mode B (hash-only, 180-200 B baseline): leave 'descriptors' empty.
# Mode A (compact descriptor set, 5.30 kB): populate 'descriptors' with
#   K=20 x 256 float32 = 5120 B of SuperPoint descriptors. Phase 1
#   uses Mode A -- see docs/poo-algorithm-spec.md.

# Observation timestamp t1 (microseconds since epoch)
uint64 timestamp

# Position p_i -- geodetic (lat,lon,alt).
geometry_msgs/Point position

# SHA-256 hash H_i = SHA-256(sort_desc(f_i[0:N=50]))
uint8[32] hash_sha256

# RANSAC inlier ratio c_i from the initial TRN fix, range [0.0, 1.0]
float32 ransac_inlier_ratio

# Sender UAV identifier ID_i
uint64 uav_id

# Ed25519 signature sigma_i over (t1 || p_i || H_i || c_i || ID_i)
uint8[64] signature_ed25519

# Mode A only: K=20 SuperPoint descriptors, 256-D L2-normalised.
# Empty array == Mode B.
float32[] descriptors
