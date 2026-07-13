param(
    [string]$RobotHost = "192.168.137.239",
    [string]$RobotUser = "jetson",
    [string]$ContainerName = "ros_x3_fixed",
    [string]$TopicName = "/image_raw"
)

$ErrorActionPreference = "Stop"

$remote = "${RobotUser}@${RobotHost}"
$encodedTopic = [uri]::EscapeDataString($TopicName)

$remoteScript = @"
set -e
docker exec '$ContainerName' bash -lc '
cd /root/car10th/backend
python3 - <<'"'"'PY'"'"'
import os
import signal
import subprocess

prefixes = (
    "python3 -m uvicorn apps.ai_service.main:app",
    "/usr/bin/python3 /usr/local/bin/uvicorn apps.ai_service.main:app",
)

out = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
for line in out.splitlines():
    raw = line.strip()
    if not raw:
        continue
    pid_s, _, args = raw.partition(" ")
    if any(args.startswith(prefix) for prefix in prefixes):
        print(f"stopping {pid_s} {args}")
        try:
            os.kill(int(pid_s), signal.SIGTERM)
        except ProcessLookupError:
            pass
PY
'
sleep 1
docker exec -d '$ContainerName' bash -lc '
export ROS_DOMAIN_ID=30
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
export PYTHONPATH=/root/yolov7:`$PYTHONPATH
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
cd /root/car10th/backend
python3 -m uvicorn apps.ai_service.main:app --host 0.0.0.0 --port 8002 > /tmp/ai_service.log 2>&1
'
sleep 6
docker exec '$ContainerName' bash -lc '
echo AI_HEALTH
curl -sS --max-time 5 http://127.0.0.1:8002/health
echo
echo SNAPSHOT
curl -sS -w "\nHTTP=%{http_code} TIME=%{time_total} SIZE=%{size_download}\n" --max-time 10 "http://127.0.0.1:8002/api/camera/snapshot?topic_name=$encodedTopic&timeout_sec=3" -o /tmp/recovered_snapshot.jpg
ls -lh /tmp/recovered_snapshot.jpg
echo
echo CAMERA_STATUS
curl -sS --max-time 5 http://127.0.0.1:8002/api/camera/status || true
echo
'
"@

Write-Host "Restarting ai_service on $remote and probing topic $TopicName"
$remoteScript | ssh $remote "bash -s"

Write-Host ""
Write-Host "Now verify from Windows:"
Write-Host ".\scripts\probe_camera_yolo_snapshot.ps1 -RobotHost $RobotHost"
