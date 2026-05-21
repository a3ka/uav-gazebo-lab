# Failover phase F2 -- paper Section IV-F.
#
# Broadcast by an orphaned follower 5 s after losing DistilledState
# from its current anchor. Surviving anchors respond with
# ReassignOffer on /reassign/offer/<anchor_id>.

# When the follower decided its current anchor was dead and started
# the failover sequence (microseconds since epoch)
uint64 timestamp

# Requesting follower's identifier
uint64 follower_id

# Last position known to the follower (dead-reckoned from IMU during
# the F1 5-s detection window)
geometry_msgs/Point last_position

# Follower velocity at the moment of the request (used by offering
# anchors to estimate handover geometry)
geometry_msgs/Vector3 velocity

# Battery percentage [0.0, 1.0]; informs anchor capacity decisions
float32 battery_pct

# Sensor capability bitfield. Bit assignments (subset):
#   bit 0 = camera + TRN
#   bit 1 = UWB
#   bit 2 = GNSS receiver
#   bit 3 = IMU (always set)
# Higher bits reserved for Phase 1+/Phase 6 capability advertisements.
uint32 sensor_caps
