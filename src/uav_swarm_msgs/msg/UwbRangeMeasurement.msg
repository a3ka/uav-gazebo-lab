# UWB inter-UAV range measurement -- paper Section IV-D ranging factor.
#
# Replaces the Phase 0 Float32 prototype with a typed message so the
# Phase 3 factor_graph_node can consume the (sender, receiver, range,
# sigma) tuple as a single payload + create the proper BetweenFactor
# in the local factor graph.
#
# Paper default sigma_range = 0.1 m (Section IV-D); we expose it per
# message to allow per-link degradation models (e.g. LoS vs NLoS,
# longer-range UWB drift) in future scenarios.

# Sample timestamp (microseconds since epoch)
uint64 timestamp

# UAV that emitted the range query (the "anchor" end of the measurement)
uint64 sender_id

# UAV that returned the range (the "responder" end)
uint64 receiver_id

# Measured range in metres
float32 range_m

# 1-sigma noise of this measurement (paper default 0.1 m)
float32 sigma_m
