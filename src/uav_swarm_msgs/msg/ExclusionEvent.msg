# Permanent peer exclusion event -- paper Section IV-F quorum exclusion.
#
# Emitted by quorum_exclusion_node once M >= 3 independent voters,
# each with own R > T_quorum=0.6, agree that a target's R has
# dropped below T_reject=0.2. The target is then permanently
# excluded from this UAV's factor-graph reasoning.
#
# Subscribed by Phase 2 scenario runner and analysis script to
# compute median + 95th percentile exclusion times per (M, f) cell
# (Prop 3) and Prop 1 false-exclusion incidents on honest peers.

# When the exclusion was declared (microseconds since epoch).
# Phase 2 analysis subtracts this from the byzantine-start timestamp
# to obtain T_exclusion for Prop 3 distribution.
uint64 timestamp

# The peer being excluded
uint64 target_id

# The voters that produced the quorum (>= M entries, M=3 default)
uint64[] voter_ids

# Lowest voter self-R among the quorum; must be > T_quorum=0.6 for
# the exclusion to be valid (sanity check for analysis layer)
float32 voter_min_r
