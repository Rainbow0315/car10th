#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-ros_x3_fixed}"
ROS_DOMAIN_ID_VALUE="${ROS_DOMAIN_ID_VALUE:-31}"
ROBOT_CODE="${ROBOT_CODE:-robot_002}"
MQTT_HOST="${MQTT_HOST:-192.168.137.20}"
MQTT_PORT="${MQTT_PORT:-1883}"
START_RTABMAP="${START_RTABMAP:-0}"
START_OCTOMAP="${START_OCTOMAP:-0}"

docker start "$CONTAINER_NAME" >/dev/null

docker exec \
  -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID_VALUE" \
  -e ROBOT_TYPE=x3 \
  -e RPLIDAR_TYPE=a1 \
  -e PYTHONUNBUFFERED=1 \
  "$CONTAINER_NAME" bash -lc "
set -eo pipefail

export ROS_DOMAIN_ID='$ROS_DOMAIN_ID_VALUE'
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
export PYTHONUNBUFFERED=1

source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ln -sf /dev/ttyUSB1 /dev/myserial || true
ln -sf /dev/ttyUSB0 /dev/rplidar || true
chmod 666 /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 2>/dev/null || true

cd /root/car10th/backend

python3 - <<'PY'
from pathlib import Path

env_path = Path('.env')
items = {}
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            items[key.strip()] = value.strip()

items.update({
    'MQTT_BROKER_HOST': '$MQTT_HOST',
    'MQTT_BROKER_PORT': '$MQTT_PORT',
    'MQTT_CLIENT_ID': 'parking_backend_$ROBOT_CODE',
    'MQTT_ROBOT_USERNAME': 'parking_robot',
    'MQTT_ROBOT_PASSWORD': 'parking_robot_dev',
    'ROBOT_CODE': '$ROBOT_CODE',
    'DEFAULT_ROBOT_CODE': '$ROBOT_CODE',
    'INSPECTION_MONITOR_ROBOT_CODE': '$ROBOT_CODE',
    'ROS_BRIDGE_HTTP_URL': 'http://127.0.0.1:8001',
    'AI_SERVICE_HTTP_URL': 'http://127.0.0.1:8002',
})

env_path.write_text(
    ''.join(f'{key}={value}\n' for key, value in items.items()),
    encoding='utf-8',
)
PY

start_if_missing() {
  local pattern=\"\$1\"
  local logfile=\"\$2\"
  shift 2
  if ! pgrep -af \"\$pattern\" | awk -v self=\"\$\$\" '\$1 != self {print}' | grep -q .; then
    nohup \"\$@\" > \"\$logfile\" 2>&1 &
  fi
}

start_if_missing 'ros2 launch yahboomcar_nav laser_bringup_launch.py' \
  /tmp/laser_bringup_domain31.log \
  ros2 launch yahboomcar_nav laser_bringup_launch.py

sleep 5

start_if_missing 'ros2 launch astra_camera astro_pro_plus.launch.xml' \
  /tmp/astra_plus.log \
  ros2 launch astra_camera astro_pro_plus.launch.xml

sleep 8

start_if_missing 'python3 -m apps.ros_bridge.main' \
  /tmp/ros_bridge_robot_002.log \
  python3 -m apps.ros_bridge.main

start_if_missing 'uvicorn apps.web_api.main:app' \
  /tmp/web_api_robot_002.log \
  python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000

start_if_missing 'apps.robot_agent.main --robot-code $ROBOT_CODE' \
  /tmp/robot_agent_robot_002.log \
  python3 -m apps.robot_agent.main --robot-code '$ROBOT_CODE' --dry-run

if [ '$START_RTABMAP' = '1' ]; then
  start_if_missing 'ros2 launch yahboomcar_nav rtabmap_sync_launch.py' \
    /tmp/rtabmap_sync_domain31.log \
    ros2 launch yahboomcar_nav rtabmap_sync_launch.py rviz:=false
fi

if [ '$START_OCTOMAP' = '1' ]; then
  start_if_missing 'octomap_server_node' \
    /tmp/octomap_server_domain31.log \
    ros2 run octomap_server octomap_server_node --ros-args \
      -r /cloud_in:=/camera/depth/points \
      -p resolution:=0.05 \
      -p frame_id:=odom \
      -p colored_map:=false \
      -p sensor_model.max_range:=5.0
fi

echo '--- health'
curl -sS --max-time 4 http://127.0.0.1:8001/health || true
echo
curl -sS --max-time 4 http://127.0.0.1:8000/health || true
echo

echo '--- key topics'
for topic in /odom /scan /camera/depth/image_raw /camera/depth/points /camera/color/image_raw; do
  echo \"### \$topic\"
  ros2 topic info \"\$topic\" 2>/dev/null || true
done

echo '--- robot agent log'
tail -20 /tmp/robot_agent_robot_002.log 2>/dev/null || true
"
