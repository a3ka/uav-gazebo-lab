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
        ],
    },
)
