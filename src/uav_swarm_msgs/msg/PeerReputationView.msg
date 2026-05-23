# Inter-UAV reputation broadcast -- paper Section IV-F quorum exclusion.
#
# Each UAV broadcasts its OWN view of every peer's reputation. The
# quorum_exclusion_node aggregates these from M independent voters to
# decide permanent exclusion.
#
# Distinct from DistilledState.reputation, which is a UAV's view of
# ITSELF. PeerReputationView is a UAV's view of OTHERS.

# When this view was computed (microseconds since epoch)
uint64 timestamp

# UAV broadcasting the view (the voter); needed so quorum_exclusion
# can verify voter_self_R > T_quorum
uint64 voter_id

# Subject of the view (the target peer whose R is reported)
uint64 target_id

# Voter's current estimate of target's reputation, in [0, 1]
float32 r_value
