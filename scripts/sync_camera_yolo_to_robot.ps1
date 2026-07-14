param(
    [string]$RobotHost = "192.168.137.239",
    [string]$RobotUser = "jetson",
    [string]$RobotProjectDir = "/home/jetson/Project/car10th",
    [string]$ContainerName = "ros_x3_fixed"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$bundleName = "car10th_camera_yolo_snapshot_patch.tar.gz"
$bundlePath = Join-Path $env:TEMP $bundleName

$files = @(
    "backend/apps/ai_service/main.py",
    "backend/apps/ai_service/detectors/crack_detector.py",
    "backend/apps/ai_service/detectors/yolov7_detector.py",
    "backend/apps/ai_service/pipelines/inspection.py",
    "backend/apps/ai_service/ros_image_capture.py",
    "backend/apps/web_api/routers/inspection.py",
    "backend/apps/web_api/services/inspection_alarm_service.py",
    "backend/apps/web_api/services/inspection_service.py",
    "backend/apps/web_api/services/inspection_monitor_service.py",
    "backend/common/config/settings.py",
    "backend/common/schemas/inspection.py",
    "docs/app_camera_yolo_live_check.md",
    "docs/yolo_input_pipeline.md",
    "scripts/robot_camera_yolo_benchmark.sh"
)

Push-Location $repoRoot
try {
    if (Test-Path $bundlePath) {
        Remove-Item -LiteralPath $bundlePath -Force
    }

    tar -czf $bundlePath @files

    $remote = "${RobotUser}@${RobotHost}"
    $remoteBundle = "/tmp/$bundleName"

    Write-Host "Uploading patch bundle to ${remote}:$remoteBundle"
    scp $bundlePath "${remote}:${remoteBundle}"

    $remoteScript = @"
set -e
cd '$RobotProjectDir'
tar -xzf '$remoteBundle' -C '$RobotProjectDir'
docker exec '$ContainerName' bash -lc '
set -e
export ROS_DOMAIN_ID=30
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
export PYTHONPATH=/root/yolov7:$PYTHONPATH
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
cd /root/car10th/backend
python3 - <<'PY'
import os
import signal
import subprocess

prefixes = (
    "python3 -m uvicorn apps.ai_service.main:app",
    "python3 -m uvicorn apps.web_api.main:app",
    "/usr/bin/python3 /usr/local/bin/uvicorn apps.ai_service.main:app",
    "/usr/bin/python3 /usr/local/bin/uvicorn apps.web_api.main:app",
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
sleep 1
nohup python3 -m uvicorn apps.ai_service.main:app --host 0.0.0.0 --port 8002 > /tmp/ai_service.log 2>&1 &
nohup python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000 > /tmp/web_api.log 2>&1 &
'
sleep 6
docker exec '$ContainerName' bash -lc '
curl -sS http://127.0.0.1:8002/health && echo
curl -sS http://127.0.0.1:8000/health && echo
curl -sS "http://127.0.0.1:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3" -o /tmp/car10th_cache_warmup.jpg || true
ls -lh /tmp/car10th_cache_warmup.jpg 2>/dev/null || true
curl -sS http://127.0.0.1:8000/api/inspection/camera/status || true
'
"@

    Write-Host "Applying patch and restarting ai_service/web_api on robot"
    $remoteScript | ssh $remote "bash -s"

    Write-Host ""
    Write-Host "Done. Next probe from Windows:"
    Write-Host ".\scripts\probe_camera_yolo_snapshot.ps1 -RobotHost $RobotHost"
    Write-Host "Invoke-WebRequest `"http://${RobotHost}:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3`" -OutFile `"`$env:TEMP\car10th_snapshot.jpg`""
    Write-Host ""
    Write-Host "Note: this script deploys robot/backend files only. Rebuild or reinstall the mobile app to see the new ControlPage camera UI."
}
finally {
    Pop-Location
}
