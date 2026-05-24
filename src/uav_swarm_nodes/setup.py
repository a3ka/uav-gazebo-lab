from setuptools import find_packages, setup

package_name = 'uav_swarm_nodes'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='uav-gazebo-lab',
    maintainer_email='lab@uav-gazebo-lab.local',
    description='Shared utility ROS2 nodes for the BFT UAV swarm validation testbed.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'position_broadcaster_node = uav_swarm_nodes.position_broadcaster_node:main',
            'uwb_ranging_simulator_node = uav_swarm_nodes.uwb_ranging_simulator_node:main',
            'comm_logger_node = uav_swarm_nodes.comm_logger_node:main',
            # Phase 4 failover protocol
            'anchor_node = uav_swarm_nodes.anchor_node:main',
            'follower_node = uav_swarm_nodes.follower_node:main',
            # Phase 2 reputation -> exclusion loop
            'verifier_node = uav_swarm_nodes.verifier_node:main',
            'reputation_manager_node = uav_swarm_nodes.reputation_manager_node:main',
            'quorum_exclusion_node = uav_swarm_nodes.quorum_exclusion_node:main',
            'signed_observation_publisher_node = uav_swarm_nodes.signed_observation_publisher_node:main',
            # Phase 3 CEP + relay refit
            'factor_graph_node = uav_swarm_nodes.factor_graph_node:main',
            'trn_anchor_node = uav_swarm_nodes.trn_anchor_node:main',
            # Phase 5 GNSS spoofing detection
            'spoof_detector_node = uav_swarm_nodes.spoof_detector_node:main',
            'multi_uwb_simulator_node = uav_swarm_nodes.multi_uwb_simulator_node:main',
            # Phase 6 attrition + load balancing
            'attrition_orchestrator_node = uav_swarm_nodes.attrition_orchestrator_node:main',
            'load_monitor_node = uav_swarm_nodes.load_monitor_node:main',
            # Phase 8 SwarmRaft baseline (Raft leader election)
            'raft_node = uav_swarm_nodes.raft_node:main',
            # Phase 6 Tier A — bridge PX4 vehicle_local_position to NoisyPose
            'px4_position_bridge_node = uav_swarm_nodes.px4_position_bridge_node:main',
        ],
    },
)
