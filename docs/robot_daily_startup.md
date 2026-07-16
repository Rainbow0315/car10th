# 小车每日启动清单

适用环境：

- 小车 IP：`192.168.137.239`
- 小车2 IP：`192.168.137.95`
- ROS 容器：`ros_x3_fixed`
- ROS_DOMAIN_ID：车1 `30`，车2 `31`
- 车型/雷达：`ROBOT_TYPE=x3`，`RPLIDAR_TYPE=a1`
- App API：`http://192.168.137.239:8000`

> 2026-07-14 真车验证：车1是 `192.168.137.239`，车2是 `192.168.137.95`。App 设置页和小车选择器里的 API/TCP 地址要跟当前车辆一致。
> 2026-07-14 真车验证：Windows Docker MySQL/MQTT 主机是 `192.168.137.20`，MySQL 密码是 `jyt20050315`。两台车 `/root/car10th/backend/.env` 的 `MYSQL_HOST` / `MQTT_BROKER_HOST` 都应指向 `192.168.137.20`。

## 0. Windows 端先确认

如果数据库和 MQTT 在 Windows Docker 里，先启动：

```powershell
docker start parking_mysql parking_mqtt
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

Patrol task saving writes to MySQL. The robot-side `/root/car10th/backend/.env` must use the Windows WLAN IP for `MYSQL_HOST`, currently `192.168.137.20`; do not use the VMnet8 IP `192.168.137.1`. If this is wrong, map APIs can still work, but saving patrol tasks fails with: `Host 'jetson-desktop.mshome.net' is not allowed to connect to this MySQL server`.

Quick fix on the robot:

```bash
cd /root/car10th/backend
sed -i 's/^MYSQL_HOST=.*/MYSQL_HOST=192.168.137.20/' .env
sed -i 's/^MQTT_BROKER_HOST=.*/MQTT_BROKER_HOST=192.168.137.20/' .env
pkill -f "uvicorn apps.web_api.main:app" || true
nohup python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000 > /tmp/web_api.log 2>&1 &
```

如果要在告警中心显示 YOLO 风险截图，或要让车牌识别读取具体号码，还要在 Windows 上启动图片/OCR 云服务。车端会把风险帧上传到 `192.168.137.20:8010`，截图保存到 `D:\code\car\car10th\backend\runtime\inspection\cloud_frames`；车1本地没有 PaddleOCR 时，会把车牌裁剪图发到 `http://192.168.137.20:8010/api/ocr/plate` 做 OCR：

第一次使用车牌 OCR 前确认 Windows Python 里有 RapidOCR：

```powershell
python -m pip install rapidocr_onnxruntime -i https://pypi.org/simple
```

```powershell
cd D:\code\car\car10th\backend
python scripts\cloud_file_server.py
```

另开终端验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
```

预期返回 `{"status":"ok","service":"cloud_file_server"}`。如果这个服务没起，新告警仍能入库，但 `image_url` 为空，App 只能尝试从产图小车读取旧路径；车牌找车也只能返回车牌框，不能读出具体号码。

检查 Windows 到小车：

```powershell
Test-NetConnection 192.168.137.239 -Port 22
Test-NetConnection 192.168.137.239 -Port 8000
```

`8000` 不通时，通常不是 App 问题，而是车上的容器或后端没起来。

## 0.1 先查是不是原厂 App 占了摄像头

摄像头物理端口只有一个。若 App 直播报 503、`/image_raw` 有 topic 但没有新帧，先在小车宿主机查 `/dev/video0` 是否被原厂程序占用：

```bash
fuser -v /dev/video0 /dev/video1 2>&1 || true
ps -ef | grep -Ei 'Rosmaster-App|usb_cam|camera|video' | grep -v grep || true
```

如果看到：

```text
python3 /home/jetson/Rosmaster-App/rosmaster/app.py
```

说明原厂 App 正在独占摄像头，`usb_cam` 无法正常出帧。先停掉它，再启动 ROS 图像链路：

```bash
pkill -f '^python3 /home/jetson/Rosmaster-App/rosmaster/app.py' || true
fuser -v /dev/video0 /dev/video1 2>&1 || true
```

注意：不要让原厂 App、OpenCV 测试脚本、`usb_cam` 同时打开 `/dev/video0`。App 直播和 YOLO 都应该复用 ROS `/image_raw`。

## 1. 启动 ROS 容器

在小车宿主机执行：

```bash
docker start ros_x3_fixed
docker exec -it ros_x3_fixed bash
```

进入容器后统一先执行：

```bash
export ROS_DOMAIN_ID=30
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1

source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ln -sf /dev/ttyUSB1 /dev/myserial
ln -sf /dev/ttyUSB0 /dev/rplidar
chmod 666 /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 2>/dev/null || true
```

## 2. App 要能读数据，至少启动这些

### 2.1 底盘和雷达

```bash
nohup ros2 launch yahboomcar_nav laser_bringup_launch.py \
  > /tmp/laser_bringup_nav.log 2>&1 &
```

### 2.2 ROS 桥接和主后端

```bash
cd /root/car10th/backend

nohup python3 -m apps.ros_bridge.main \
  > /tmp/ros_bridge.log 2>&1 &

export TCP_CAR_TRACK_START_COMMAND="bash -lc 'source /opt/ros/foxy/setup.bash; source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash; source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash; exec ros2 run yahboomcar_laser laser_Tracker_a1_X3 > /tmp/laser_tracker_app.log 2>&1'"
export TCP_CAR_TRACK_STOP_COMMAND="bash -lc 'pkill -f \"[l]aser_Tracker_a1_X3\" || true'"
nohup python3 -m apps.tcp_car_bridge.main \
  > /tmp/tcp_car_bridge.log 2>&1 &

nohup python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000 \
  > /tmp/web_api.log 2>&1 &
```

如果是巡航/定时巡航测试，`web_api` 启动时会同时启动巡航定时调度器，读取数据库里 `schedule_cron` 非空的 `/api/patrol/tasks`。定时表达式是 5 段 cron，例如 `0 22 * * *`。

验证：

```bash
curl http://127.0.0.1:8001/health
ss -lntp | grep ':6001'
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/slam/map
curl "http://127.0.0.1:8000/api/inspection/alarms?limit=3"
```

需要在车端单独验证灯光秀时运行：

```bash
cd /root/car10th/backend
python3 scripts/light_show.py
```

Windows 上也可以验证：

```powershell
Invoke-RestMethod http://192.168.137.239:8000/health
Invoke-RestMethod http://192.168.137.239:8000/api/slam/map
Invoke-RestMethod "http://192.168.137.239:8000/api/inspection/alarms?limit=3"
```

## 3. 建图模式和导航模式二选一

不要同时开 `map_gmapping_launch.py` 和导航 launch。

- 建图模式：`/map` 由 `slam_gmapping` 发布，是实时动态地图。
- 导航模式：`/map` 由 `map_server` 发布，是保存好的静态地图。

### 3.1 建图模式

用于重新录 SLAM 地图：

```bash
ros2 launch yahboomcar_nav map_gmapping_launch.py
```

保存地图后，把地图放到导航读取路径：

```bash
cp /root/yahboomcar_ros2_ws/yahboomcar_ws/src/yahboomcar_nav/maps/yahboomcar.* \
  /root/yahboomcar_ros2_ws/yahboomcar_ws/install/yahboomcar_nav/share/yahboomcar_nav/maps/
```

### 3.2 导航模式

用于 App 显示静态地图、后续发导航目标：

车1当前使用优化版导航：

```bash
nohup ros2 launch yahboomcar_nav navigation_dwa_fast_launch.py \
  > /tmp/navigation_dwa_fast.log 2>&1 &
```

车2当前稳定启动项仍是原版导航：

```bash
nohup ros2 launch yahboomcar_nav navigation_dwa_launch.py \
  > /tmp/navigation_dwa.log 2>&1 &
```

说明：2026-07-14 已把车1的 `navigation_dwa_fast_launch.py`、`navigation_dwa_candidate_launch.py`、`dwa_nav_params_fast.yaml`、`dwa_nav_params_candidate.yaml` 同步到车2的 Yahboom ROS 工作空间，但车2用 fast 入口启动时仍出现 `base_footprint -> odom` TF 等待，巡航前先用原版 `navigation_dwa_launch.py` 保证 `/map`、`/amcl_pose` 和 App 地图可用。

启动后给 AMCL 一个初始位姿：

```bash
ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
"{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}}, covariance: [0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0685]}}"
```

验证导航栈：

```bash
ros2 topic info /map
ros2 topic info /scan
ros2 topic info /odom
tail -40 /tmp/navigation_dwa_fast.log
tail -40 /tmp/navigation_dwa.log
```

期望：

- `/map` publisher 是 `map_server`
- `/scan` publisher 是 `sllidar_node`
- `/odom` publisher 是 `ekf_filter_node`
- 日志里有 `Managed nodes are active`

如果日志持续提示 `Please set the initial pose`，说明 AMCL 还没有初始位姿。可以先用上面的 `/initialpose` 命令给一个默认位姿，再在 App 地图页校准。

## 4. 摄像头预览和 AI 检测

如果只验证 App 摄像头预览，先启动 RGB 图像和 AI 服务即可，不需要启动 YOLO monitor。

### 4.1 启动 USB 摄像头

```bash
nohup ros2 run usb_cam usb_cam_node_exe \
  --ros-args --params-file /opt/ros/foxy/share/usb_cam/config/params.yaml \
  > /tmp/usb_cam.log 2>&1 &
```

预期有 `/image_raw`。不推荐日常用 `ros2 launch usb_cam demo_launch.py`，因为它会额外启动 `show_image.py`，在无 GUI 或 NoMachine 环境下容易产生干扰。只启动 `usb_cam_node_exe` 更稳。

注意：摄像头物理端口只有一个，不要让多个进程同时打开 `/dev/video0`。推荐只由 `usb_cam` 打开摄像头，App 预览和 AI 检测都从 ROS `/image_raw` 间接取图。

检查：

```bash
ros2 topic list | grep image_raw
ros2 topic hz /image_raw
tail -40 /tmp/usb_cam.log
```

### 4.2 启动 AI 服务和主后端

`ai_service` 负责从 ROS `/image_raw` 抓帧并返回 JPEG；`web_api` 负责给 App 暴露 `8000` 网关。

```bash
cd /root/car10th/backend

export PYTHONPATH=/root/yolov7:$PYTHONPATH

nohup python3 -m uvicorn apps.ai_service.main:app --host 0.0.0.0 --port 8002 \
  > /tmp/ai_service.log 2>&1 &

nohup python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000 \
  > /tmp/web_api.log 2>&1 &
```

检查：

```bash
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3" \
  -o /tmp/app_snapshot.jpg
ls -lh /tmp/app_snapshot.jpg
curl "http://127.0.0.1:8000/api/inspection/camera/mjpeg?topic_name=/image_raw&fps=3&timeout_sec=5" \
  --max-time 4 -o /tmp/app_mjpeg_probe.bin || true
ls -lh /tmp/app_mjpeg_probe.bin
```

Windows 上也可以不启动模型，只验证视频预览链路：

```powershell
cd D:\code\car\car10th
.\scripts\probe_camera_yolo_snapshot.ps1
```

预期：

- `web_api` 和 `ai_service` health 都是 `ok`
- 能保存约 `150 KB` 左右的 JPEG
- MJPEG 探测文件在 4 秒内能拿到持续增长的数据
- `monitor/status.running=false` 表示还没启动 YOLO monitor

### 4.3 启动 YOLO 检测

确认视频预览可用后，再启动 YOLO monitor。建议先只开 `puddle`、`fod`，后续模型微调和压力验证再逐步加 `crack`。

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/start \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "/image_raw",
    "interval_sec": 1.0,
    "timeout_sec": 10,
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["unified"]
  }'

curl http://127.0.0.1:8000/api/inspection/monitor/status
```

停止：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/stop
```

## 5. 常见故障速查

### App 完全没数据

先看车端服务，不要先怀疑前端：

```bash
docker ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
```

如果 `docker ps` 里没有 `ros_x3_fixed`，说明容器停了，重新从第 1 节开始。

如果 `8000/8001` 能通，但视频 503、控制无响应、地图无数据，按链路分别查：

```bash
ss -lntp | grep -E ':8000|:8001|:8002|:6001' || true
ros2 topic info /image_raw
ros2 topic info /map
ros2 topic info /scan
ros2 topic info /odom
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8000/api/inspection/camera/status
```

- 视频：`8002` 必须健康，`/image_raw` 必须有 publisher 且能出新帧。
- 控车：宿主机必须监听 `6001`，App 走 TCP 到 `小车IP:6001`。
- 地图：`/map`、`/scan`、`/odom` 必须都有 publisher。

### App 显示圆形雷达图，不是保存的地图

说明还在建图模式，`/map` 大概率由 `slam_gmapping` 发布。

```bash
ros2 topic info /map -v
```

切到导航模式后，`/map` 应该由 `map_server` 发布。

### 地图 API 还是旧尺寸

检查 `ros_bridge` 是否已重启，并确认 `/map` 订阅 QoS 是 `TRANSIENT_LOCAL`：

```bash
curl http://127.0.0.1:8001/api/slam/map
curl http://127.0.0.1:8000/api/slam/map
```

当前保存地图的正常尺寸应接近：

```text
width=640
height=608
data_len=389120
```

### 数据库告警读不到

Windows 先确认 MySQL：

```powershell
docker start parking_mysql
docker exec parking_mysql mysql -uroot -pjyt20050315 -e "USE parking_inspection_robot; SELECT COUNT(*) FROM alarm_logs;"
```

车上确认 `web_api` 的 `.env` 指向 Windows 主机 IP，而不是容器内默认 `mysql`。

### MQTT 报连接失败

`web_api /health` 里 `mqtt_connected=false` 不一定影响地图和数据库读取；如果要用 MQTT 控车/推送，再启动 Windows 的 `parking_mqtt` 并确认车端 `.env` 指向正确 broker。

## 6. 最短启动顺序

只想让 App 读地图、告警、基础状态：

```bash
docker start ros_x3_fixed
docker exec -it ros_x3_fixed bash

export ROS_DOMAIN_ID=30
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ln -sf /dev/ttyUSB1 /dev/myserial
ln -sf /dev/ttyUSB0 /dev/rplidar
chmod 666 /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 2>/dev/null || true

nohup ros2 launch yahboomcar_nav laser_bringup_launch.py > /tmp/laser_bringup_nav.log 2>&1 &
# 车1：
nohup ros2 launch yahboomcar_nav navigation_dwa_fast_launch.py > /tmp/navigation_dwa_fast.log 2>&1 &
# 车2当前稳定项：
# nohup ros2 launch yahboomcar_nav navigation_dwa_launch.py > /tmp/navigation_dwa.log 2>&1 &

cd /root/car10th/backend
nohup python3 -m apps.ros_bridge.main > /tmp/ros_bridge.log 2>&1 &
nohup python3 -m apps.tcp_car_bridge.main > /tmp/tcp_car_bridge.log 2>&1 &
nohup ros2 run usb_cam usb_cam_node_exe --ros-args --params-file /opt/ros/foxy/share/usb_cam/config/params.yaml > /tmp/usb_cam.log 2>&1 &
export PYTHONPATH=/root/yolov7:$PYTHONPATH
nohup python3 -m uvicorn apps.ai_service.main:app --host 0.0.0.0 --port 8002 > /tmp/ai_service.log 2>&1 &
nohup python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000 > /tmp/web_api.log 2>&1 &
```

最后验证：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/slam/map
curl "http://127.0.0.1:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3" -o /tmp/app_snapshot.jpg
curl "http://127.0.0.1:8000/api/inspection/alarms?limit=3"
```

最后从 Windows 验证：

```powershell
Test-NetConnection 192.168.137.239 -Port 6001
Invoke-RestMethod http://192.168.137.239:8000/health
Invoke-RestMethod http://192.168.137.239:8001/health
Invoke-RestMethod http://192.168.137.239:8002/health
Invoke-WebRequest "http://192.168.137.239:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3" -OutFile "$env:TEMP\car10th_snapshot.jpg"
```
