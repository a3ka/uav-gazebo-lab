cmake_minimum_required(VERSION 3.14)
project(uav_swarm_msgs)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

set(msg_files
  msg/SignedObservation.msg
  msg/DistilledState.msg
  msg/NoisyPose.msg
  msg/ReputationUpdate.msg
  # Failover protocol (paper Section IV-F, Phase 4 implementation)
  msg/ReassignRequest.msg
  msg/ReassignOffer.msg
  msg/AttachAck.msg
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  DEPENDENCIES geometry_msgs builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)

ament_package()
