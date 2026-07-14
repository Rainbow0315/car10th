# 小车每日启动清单

适用环境：

- 小车 IP：`192.168.137.239`
- ROS 容器：`ros_x3_fixed`
- ROS_DOMAIN_ID：`30`
- 车型/雷达：`ROBOT_TYPE=x3`，`RPLIDAR_TYPE=a1`
- App API：`http://192.168.137.239:8000`

## 0. Windows 端先确认

如果数据库和 MQTT 在 Windows Docker 里，先启动：

```powershell
docker start parking_mysql parking_mqtt
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

检查 Windows 到小车：

```powershell
Test-NetConnection 192.168.137.239 -Port 22
Test-NetConnection 192.168.137.239 -Port 8000
```

`8000` 不通时，通常不是 App 问题，而是车上的容器或后端没起来。

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

不要同时开 `map_gmapping_launch.py` 和 `navigation_dwa_fast_launch.py`。

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

```bash
nohup ros2 launch yahboomcar_nav navigation_dwa_fast_launch.py \
  > /tmp/navigation_dwa_fast.log 2>&1 &
```

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
```

期望：

- `/map` publisher 是 `map_server`
- `/scan` publisher 是 `sllidar_node`
- `/odom` publisher 是 `ekf_filter_node`
- 日志里有 `Managed nodes are active`

## 4. 摄像头预览和 AI 检测

如果只验证 App 摄像头预览，先启动 RGB 图像和 AI 服务即可，不需要启动 YOLO monitor。

### 4.1 启动 USB 摄像头

```bash
ros2 launch usb_cam demo_launch.py
```

预期有 `/image_raw`。如果 `show_image.py` 报 OpenCV GUI 错误，一般可以先忽略，只要 `usb_cam_node_exe` 还在发布图像。

注意：摄像头物理端口只有一个，不要让多个进程同时打开 `/dev/video0`。推荐只由 `usb_cam` 打开摄像头，App 预览和 AI 检测都从 ROS `/image_raw` 间接取图。

检查：

```bash
ros2 topic list | grep image_raw
ros2 topic hz /image_raw
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
```

Windows 上也可以不启动模型，只验证视频预览链路：

```powershell
cd D:\code\car\car10th
.\scripts\probe_camera_yolo_snapshot.ps1
```

预期：

- `web_api` 和 `ai_service` health 都是 `ok`
- 能保存约 `150 KB` 左右的 JPEG
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
    "enabled_models": ["puddle", "fod"]
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
nohup ros2 launch yahboomcar_nav navigation_dwa_fast_launch.py > /tmp/navigation_dwa_fast.log 2>&1 &

cd /root/car10th/backend
nohup python3 -m apps.ros_bridge.main > /tmp/ros_bridge.log 2>&1 &
nohup python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000 > /tmp/web_api.log 2>&1 &
```

最后验证：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/slam/map
curl "http://127.0.0.1:8000/api/inspection/alarms?limit=3"
```
