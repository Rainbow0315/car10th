#!/usr/bin/env bash
set -eo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_BRIDGE_URL="${ROS_BRIDGE_URL:-http://127.0.0.1:8001}"
export WEB_API_URL="${WEB_API_URL:-http://127.0.0.1:8000}"

source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
echo

echo "[1/5] ROS topics"
ros2 topic list | grep -E '^(/map|/odom|/scan|/goal_pose|/cmd_vel)$' || true
echo

echo "[2/5] /map info"
ros2 topic info /map || true
echo

echo "[3/5] /odom info"
ros2 topic info /odom || true
echo

echo "[4/5] ros_bridge map endpoint"
curl -s "$ROS_BRIDGE_URL/api/slam/map" | python3 -m json.tool || true
echo

echo "[5/5] web_api map endpoint"
curl -s "$WEB_API_URL/api/slam/map" | python3 -m json.tool || true
echo

echo "Goal topic check command:"
echo "  ros2 topic echo /goal_pose --once"
echo
echo "Goal API test command:"
echo "  curl -X POST $WEB_API_URL/api/slam/goal -H 'Content-Type: application/json' -d '{\"x\":0.5,\"y\":0.0,\"yaw\":0.0,\"frame_id\":\"map\"}'"
