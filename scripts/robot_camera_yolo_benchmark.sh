#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-ros_x3_fixed}"
TOPIC_NAME="${TOPIC_NAME:-/image_raw}"
DURATION_SEC="${DURATION_SEC:-30}"
SNAPSHOT_INTERVAL_SEC="${SNAPSHOT_INTERVAL_SEC:-1}"
WEB_API_URL="${WEB_API_URL:-http://127.0.0.1:8000}"
AI_SERVICE_URL="${AI_SERVICE_URL:-http://127.0.0.1:8002}"
RESULT_DIR="${RESULT_DIR:-/tmp/car10th_camera_yolo_benchmark}"
ENCODED_TOPIC="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$TOPIC_NAME")"

mkdir -p "$RESULT_DIR"

echo "== Camera + YOLO benchmark =="
echo "container=$CONTAINER_NAME"
echo "topic=$TOPIC_NAME"
echo "duration=${DURATION_SEC}s"
echo "web_api=$WEB_API_URL"
echo "ai_service=$AI_SERVICE_URL"
echo "result_dir=$RESULT_DIR"
echo

docker exec "$CONTAINER_NAME" bash -lc "
set -e
export ROS_DOMAIN_ID=30
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
echo '== ROS topics matching image_raw =='
ros2 topic list | grep image_raw || true
echo
echo '== /image_raw frequency sample =='
timeout 8 ros2 topic hz '$TOPIC_NAME' || true
" | tee "$RESULT_DIR/ros_topic_check.log"

echo
echo "== HTTP health =="
curl -sS "$WEB_API_URL/health" | tee "$RESULT_DIR/web_api_health.json"
echo
curl -sS "$AI_SERVICE_URL/health" | tee "$RESULT_DIR/ai_service_health.json"
echo
curl -sS "$WEB_API_URL/api/inspection/camera/status" | tee "$RESULT_DIR/camera_status_before.json" || true
echo

TEGRAPID=""
if command -v tegrastats >/dev/null 2>&1; then
  tegrastats --interval 1000 > "$RESULT_DIR/tegrastats.log" 2>&1 &
  TEGRAPID="$!"
  echo "tegrastats pid=$TEGRAPID"
else
  echo "tegrastats not found on PATH" | tee "$RESULT_DIR/tegrastats.log"
fi

cleanup() {
  if [[ -n "$TEGRAPID" ]] && kill -0 "$TEGRAPID" >/dev/null 2>&1; then
    kill "$TEGRAPID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo
echo "== Start YOLO monitor =="
curl -sS -X POST "$WEB_API_URL/api/inspection/monitor/start" \
  -H "Content-Type: application/json" \
  -d "{
    \"topic_name\": \"$TOPIC_NAME\",
    \"interval_sec\": 1.0,
    \"timeout_sec\": 10,
    \"robot_code\": \"robot_001\",
    \"camera_code\": \"usb_cam\",
    \"enabled_models\": [\"puddle\", \"fod\"]
  }" | tee "$RESULT_DIR/monitor_start.json"
echo

echo
echo "== Snapshot loop while YOLO monitor runs =="
CSV="$RESULT_DIR/snapshot_latency.csv"
echo "index,epoch_ms,http_code,total_time_sec,size_bytes" > "$CSV"

END_AT=$((SECONDS + DURATION_SEC))
INDEX=0
while [[ "$SECONDS" -lt "$END_AT" ]]; do
  INDEX=$((INDEX + 1))
  OUT="$RESULT_DIR/snapshot_${INDEX}.jpg"
  META="$(curl -sS \
    -o "$OUT" \
    -w "%{http_code},%{time_total},%{size_download}" \
    "$WEB_API_URL/api/inspection/camera/snapshot?topic_name=$ENCODED_TOPIC&timeout_sec=3" || true)"
  EPOCH_MS="$(date +%s%3N)"
  echo "$INDEX,$EPOCH_MS,$META" | tee -a "$CSV"
  curl -sS "$WEB_API_URL/api/inspection/camera/status" > "$RESULT_DIR/camera_status_${INDEX}.json" || true
  sleep "$SNAPSHOT_INTERVAL_SEC"
done

echo
echo "== Camera cache status =="
curl -sS "$WEB_API_URL/api/inspection/camera/status" | tee "$RESULT_DIR/camera_status_after.json" || true
echo

echo
echo "== YOLO monitor status =="
curl -sS "$WEB_API_URL/api/inspection/monitor/status" | tee "$RESULT_DIR/monitor_status.json"
echo

echo
echo "== Stop YOLO monitor =="
curl -sS -X POST "$WEB_API_URL/api/inspection/monitor/stop" | tee "$RESULT_DIR/monitor_stop.json"
echo

cleanup
trap - EXIT

echo
echo "== Summary hints =="
echo "Snapshot latency CSV: $CSV"
echo "Tegrastats log: $RESULT_DIR/tegrastats.log"
echo "Pass baseline: most http_code values are 200, total_time_sec mostly under 3, monitor_status total_frames grows, last_error is empty."
