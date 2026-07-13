#!/usr/bin/env bash
set -eo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROBOT_TYPE="${ROBOT_TYPE:-x3}"
export RPLIDAR_TYPE="${RPLIDAR_TYPE:-a1}"

source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

# The original Yahboom launch files expect these device aliases.
ln -sf /dev/ttyUSB1 /dev/myserial
ln -sf /dev/ttyUSB0 /dev/rplidar
chmod 666 /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 2>/dev/null || true

echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
echo "ROBOT_TYPE=$ROBOT_TYPE"
echo "RPLIDAR_TYPE=$RPLIDAR_TYPE"
ls -l /dev/myserial /dev/rplidar /dev/ttyUSB* 2>/dev/null || true

exec ros2 launch yahboomcar_nav map_gmapping_launch.py
