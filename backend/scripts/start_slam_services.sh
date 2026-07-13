#!/usr/bin/env bash
set -eo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_BRIDGE_PORT="${ROS_BRIDGE_PORT:-8001}"
export WEB_API_PORT="${WEB_API_PORT:-8000}"

source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

cd /root/car10th/backend
mkdir -p /tmp/car10th_services

if ! curl -s "http://127.0.0.1:${ROS_BRIDGE_PORT}/health" >/dev/null 2>&1; then
  nohup python3 -m apps.ros_bridge.main > /tmp/car10th_services/ros_bridge.log 2>&1 &
  echo "$!" > /tmp/car10th_services/ros_bridge.pid
  echo "ros_bridge started pid=$(cat /tmp/car10th_services/ros_bridge.pid)"
else
  echo "ros_bridge already running on ${ROS_BRIDGE_PORT}"
fi

if ! curl -s "http://127.0.0.1:${WEB_API_PORT}/health" >/dev/null 2>&1; then
  nohup uvicorn apps.web_api.main:app --host 0.0.0.0 --port "$WEB_API_PORT" > /tmp/car10th_services/web_api.log 2>&1 &
  echo "$!" > /tmp/car10th_services/web_api.pid
  echo "web_api started pid=$(cat /tmp/car10th_services/web_api.pid)"
else
  echo "web_api already running on ${WEB_API_PORT}"
fi

echo "Check:"
echo "  curl http://127.0.0.1:${ROS_BRIDGE_PORT}/api/slam/map"
echo "  curl http://127.0.0.1:${WEB_API_PORT}/api/slam/map"
