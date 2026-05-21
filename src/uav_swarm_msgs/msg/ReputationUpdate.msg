# Reputation change event -- paper Section IV-C.
#
# Emitted by a verifier UAV after evaluating a SignedObservation or
# UWB consistency check from a peer. Subscribers include the per-UAV
# reputation manager + Phase 2 audit logger (exclusion-time analysis).

# When the update was decided (microseconds since epoch)
uint64 timestamp

# Who is making the update (the verifier -- its own reputation R_k is
# used as a multiplier on the per-event delta)
uint64 reporter_id

# Whose reputation is being updated (the target peer)
uint64 target_id

# Reputation before this update
float32 old_value

# Reputation after this update (already clamped to [0,1])
float32 new_value

# Reason codes. Numeric mapping aligns with paper Section IV-C event
# taxonomy. See package documentation for the delta formulas.
#   VERIFIED        ->  + alpha_pos * R_k
#   UNVERIFIED      ->  - alpha_neg * R_k    (alpha_neg = 0.15 default)
#   INVALID_SIG     ->  - alpha_sig          (alpha_sig = 0.30 default)
#   UWB_RANGE_FAIL  ->  - alpha_range        (alpha_range = 0.10)
#   DECAY           ->  * exp(-lambda * dt)  (lambda = 1e-3 s^-1)
uint8 REASON_VERIFIED=1
uint8 REASON_UNVERIFIED=2
uint8 REASON_INVALID_SIG=3
uint8 REASON_UWB_RANGE_FAIL=4
uint8 REASON_DECAY=5
uint8 reason
