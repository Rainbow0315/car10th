# App camera preview + YOLO concurrent check

## 2026-07-13 update: latest-frame cache

已将 `ai_service` 的 ROS 抓帧方式从“每次请求临时创建订阅、抓一帧、销毁订阅”改为“单个持久订阅 `/image_raw`，维护 latest-frame cache”。

新的链路：

```text
usb_cam
  -> ROS /image_raw
  -> ai_service persistent subscriber + latest-frame cache
  -> snapshot: GET /api/camera/snapshot
  -> YOLO: POST /api/inspection/detect-ros-image
  -> web_api:8000
  -> App
```

这个改动解决的是并发结构问题：App 预览和 YOLO 不再各自临时订阅/抓帧，而是共享 `ai_service` 内的最新帧缓存。它不等于已经证明 Jetson 内存一定够用；模型显存、CPU 编码、网络刷新频率仍需要上车压测。

新增排查接口：

```bash
curl http://127.0.0.1:8002/api/camera/status
curl http://127.0.0.1:8000/api/inspection/camera/status
```

关键字段：
- `running=true`：缓存订阅线程已启动。
- `has_frame=true`：已经从 `/image_raw` 收到至少一帧。
- `frame_age_sec`：最新帧距当前的秒数，持续变大说明 ROS 图像流或缓存线程可能卡住。
- `frame_is_fresh=true`：最新帧仍在可用时间窗内，snapshot/YOLO 可以使用。
- `last_error`：图像编码、ROS spin 等异常信息。

当前工程判断：
- 低频 App preview 继续走 HTTP snapshot，已经是最短可验证闭环。
- 真正同步 YOLO 时，应优先验证 `puddle/fod` 两个模型，暂时不要一次上满所有模型。
- 如果缓存接口稳定、snapshot 稳定、monitor 有 `total_frames` 增长，再看 `tegrastats` 判断 Jetson 是否扛得住。

说明：下文保留的“临时订阅抓帧”描述是 2026-07-13 早些时候并发失败的历史记录；以本节 latest-frame cache 方案为当前实现。车上是否已经部署当前实现，以 `/api/inspection/camera/status` 是否存在、`has_frame=true`、`frame_is_fresh=true` 为准。

## 2026-07-13 robot verification after deployment

已通过 Paramiko 将 latest-frame cache 版本部署到 `192.168.137.239` 的 `/home/jetson/Project/car10th`，并重启 `ai_service` / `web_api`。

视频链路验证结果：

```text
GET /api/inspection/camera/status
running=true
topic_name=/image_raw
has_frame=true
frame_is_fresh=true
last_error=null

GET /api/inspection/camera/snapshot
HTTP=200
snapshot saved, about 75-78 KB
```

单帧检测验证结果：

```text
POST /api/inspection/detect-ros-image
enabled_models=["puddle","fod"]
device=cuda
completed_models=["puddle","fod"]
failed_models=[]
```

短并发验证结果，`puddle/fod` YOLO monitor + 1 Hz snapshot，持续约 `12s`：

```text
snapshot requests: 11/11 HTTP 200
snapshot latency: about 0.02s - 0.06s
monitor total_frames: 12
monitor last_error: null
camera frame_is_fresh: true
```

`tegrastats` 摘要：

```text
RAM: about 3049MB -> 3074MB / 3311MB
SWAP: about 3163MB - 3171MB / 5751MB
CPU: mostly 20% - 30% per core during this short run
GPU/CPU temp: about 59C
```

结论：在当前 `puddle/fod`、1 FPS snapshot、约 12 秒短测条件下，App 预览和 YOLO monitor 可以同步跑通；但 Jetson 内存余量很小，不能据此承诺长时间高帧率直播或三模型全开稳定运行。后续模型微调、提高帧率、加入 `crack` 模型前，需要继续做更长时间的 `tegrastats` 压测。

目标：用最短闭环验证 App 接入小车摄像头实时画面时，YOLO 检测还能不能同步运行。

当前优先方案是 HTTP snapshot，每 1 秒左右抓一帧给 App 显示。它不是最终最高帧率直播方案，但最适合先验证链路和 Jetson 负载。

## 0. 当前实测状态

实测日期：2026-07-13。

已确认视频流链路可用，未启动 YOLO 模型：

```text
Windows/App network
  -> web_api:8000/api/inspection/camera/snapshot
  -> ai_service:8002/api/camera/snapshot
  -> ROS2 /image_raw
  -> JPEG snapshot
```

实测结果：

- `usb_cam` 已发布 `/image_raw`、`/camera_info` 和 `/image_raw/compressed`。
- `ai_service:8002/health` 返回 `{"status":"ok","service":"ai_service"}`。
- `web_api:8000/health` 返回 `{"status":"ok","service":"web_api",...}`。
- Windows 访问 `http://192.168.137.239:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3` 可以保存真实摄像头 JPEG。
- 单帧 JPEG 大约 `150 KB`。
- 容器内连续 3 轮测试 direct/web snapshot 均为 HTTP `200`，耗时约 `0.2s` 到 `2.0s`。
- `probe_camera_yolo_snapshot.ps1` 不带 `-StartYolo` 时通过，且 `monitor/status.running=false`。

本阶段结论：

- App 预览优先使用 HTTP snapshot 是可行的。
- 当前验证的是低频预览，不是高帧率 MJPEG 直播。
- YOLO 并发和内存压力尚未作为通过项，后续单独验证。

单摄像头端口结论：

- 物理摄像头只有一个输入端口，不应让多个进程同时打开 `/dev/video0`。
- 如果 App 直播方案直接打开摄像头设备，同时 YOLO/`usb_cam` 也打开设备，这条路大概率不可行。
- 可行前提是只允许 `usb_cam` 一个进程打开摄像头，再由 ROS `/image_raw` 扇出给预览和检测。
- 当前实现的 HTTP snapshot 和 YOLO 检测都走 ROS topic，不直接打开 `/dev/video0`，方向是对的。
- 但当前实现仍是“每次请求临时订阅抓帧”，并发稳定性不够，不建议承诺高帧率直播 + YOLO 同时跑。
- 若要继续做同步，下一步应改成 `ai_service` 内部单一持久订阅 `/image_raw`，维护最新帧缓存；App snapshot 和 YOLO 都从这个缓存取帧。
- 如果时间不够，建议答辩口径定为：已打通 App 低频摄像头预览；YOLO 检测与高帧率直播同步需要单帧源缓存架构，当前不硬承诺。

2026-07-13 短时并发试验：

- 测试方式：`puddle/fod` YOLO monitor + 每秒一次 snapshot，持续约 `20s`。
- 结果：未进入有效性能测试阶段。
- 现象：snapshot 请求返回 HTTP `400`，YOLO monitor `total_frames=0`，`last_error=500: Internal Server Error`。
- 初始原因之一：车上 `apps/ai_service/pipelines/inspection.py` 版本旧，缺 `inspect_ros_topic()`；已同步修复。
- 后续单帧检测仍出现 `/image_raw` 抓帧超时；重启 `ai_service` 后 snapshot 恢复，direct/web snapshot 均 HTTP `200`。
- 判断：这不是“Jetson 内存一定扛不住”的证据，而是当前临时订阅抓帧方案在并发/失败后状态不稳定。
- 当前不建议继续硬测 YOLO 并发，除非先实现持久订阅 + 最新帧缓存。

恢复视频预览：

Windows 一键恢复：

```powershell
cd D:\code\car\car10th
.\scripts\recover_camera_snapshot.ps1
.\scripts\probe_camera_yolo_snapshot.ps1
```

手动恢复：

```bash
docker exec -d ros_x3_fixed bash -lc '
export ROS_DOMAIN_ID=30
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
export PYTHONPATH=/root/yolov7:$PYTHONPATH
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
cd /root/car10th/backend
python3 -m uvicorn apps.ai_service.main:app --host 0.0.0.0 --port 8002 > /tmp/ai_service.log 2>&1
'
```

## 1. 链路说明

App 控制页摄像头预览：

```text
App ControlPage
  -> GET web_api:8000/api/inspection/camera/snapshot?topic_name=/image_raw
  -> web_api InspectionService
  -> GET ai_service:8002/api/camera/snapshot
  -> ROS2 /image_raw
  -> 返回 JPEG
```

App 控制页 YOLO 按钮：

```text
Start YOLO
  -> POST web_api:8000/api/inspection/monitor/start
  -> web_api 后台 worker
  -> POST ai_service:8002/api/inspection/detect-ros-image
  -> ROS2 /image_raw
  -> crack / puddle / fod 推理
  -> 有风险时写 alarm_logs 并推送 MQTT alarm/notify

Stop YOLO
  -> POST web_api:8000/api/inspection/monitor/stop
```

手动控车仍然走原来的 Yahboom TCP 长连接，不经过这些 HTTP 接口：

```text
App ControlPage
  -> TCP <car-ip>:<tcp-port>
  -> Yahboom 原厂控车服务
  -> 底盘串口/电机
```

## 2. 启动服务

进入小车和 ROS 容器：

```bash
ssh jetson@192.168.137.239
docker start ros_x3_fixed
docker exec -it ros_x3_fixed bash
```

容器内统一环境：

```bash
export ROS_DOMAIN_ID=30
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
```

启动 USB 摄像头：

```bash
ros2 launch usb_cam demo_launch.py
```

另开容器终端，启动后端：

```bash
cd /root/car10th/backend

nohup python3 -m apps.ros_bridge.main > /tmp/ros_bridge.log 2>&1 &
export PYTHONPATH=/root/yolov7:$PYTHONPATH
nohup python3 -m uvicorn apps.ai_service.main:app --host 0.0.0.0 --port 8002 > /tmp/ai_service.log 2>&1 &
nohup python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000 > /tmp/web_api.log 2>&1 &
```

## 3. 先确认 /image_raw

```bash
ros2 topic list | grep image_raw
ros2 topic hz /image_raw
```

预期：

- 能看到 `/image_raw`
- `ros2 topic hz /image_raw` 有稳定输出

如果失败：

- 看 `usb_cam` 启动终端是否退出
- 确认摄像头没有被其他进程独占
- 临时不要依赖 Astra Plus 的 `/camera/color/image_raw`

## 4. 再确认 AI 单帧检测

先测 `ai_service:8002`：

```bash
curl -sS --max-time 300 \
  -X POST http://127.0.0.1:8002/api/inspection/detect-ros-image \
  -H "Content-Type: application/json" \
  -d '{"topic_name":"/image_raw","timeout_sec":10,"camera_code":"usb_cam","enabled_models":["puddle","fod"]}'
```

再测 App 会经过的 `web_api:8000`：

```bash
curl -sS --max-time 300 \
  -X POST http://127.0.0.1:8000/api/inspection/detect-ros-image \
  -H "Content-Type: application/json" \
  -d '{"topic_name":"/image_raw","timeout_sec":10,"camera_code":"usb_cam","enabled_models":["puddle","fod"]}'
```

预期：

- 返回 JSON
- `summary.completed_models` 至少包含请求的模型
- `device` 是 `cuda` 时说明走 GPU

如果失败：

```bash
tail -120 /tmp/ai_service.log
tail -120 /tmp/web_api.log
```

## 5. 验证 HTTP snapshot

容器内：

```bash
curl -sS --max-time 10 \
  "http://127.0.0.1:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3" \
  -o /tmp/app_snapshot.jpg

ls -lh /tmp/app_snapshot.jpg
```

Windows 上：

```powershell
Invoke-WebRequest `
  "http://192.168.137.239:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3" `
  -OutFile "$env:TEMP\app_snapshot.jpg"
```

如果 Windows 能保存图片，App 控制页的 `Start preview` 就应该能显示画面。

也可以直接用 Windows 探测脚本一次性检查 health、snapshot 和监控状态：

```powershell
cd D:\code\car\car10th
.\scripts\probe_camera_yolo_snapshot.ps1
```

如果要同时启动 YOLO 监控并观察 5 秒后的状态：

```powershell
.\scripts\probe_camera_yolo_snapshot.ps1 -StartYolo
```

## 6. App 操作

Android 工程已经配置：

- `android.permission.INTERNET`
- `android:usesCleartextTraffic="true"`

因此可以直接访问 `http://192.168.137.239:8000` 这类明文 HTTP 地址。

当前 Windows Flutter 环境未检测到 Android 手机设备。连接手机并打开 USB 调试后，可用：

```powershell
cd D:\code\car\car10th\mobile_app
flutter devices
flutter run
```

或者先构建 APK：

```powershell
cd D:\code\car\car10th\mobile_app
flutter build apk --debug
```

生成位置通常是：

```text
mobile_app\build\app\outputs\flutter-apk\app-debug.apk
```

2026-07-13 已验证：

- `flutter build apk --debug` 构建成功。
- APK 路径：`mobile_app\build\app\outputs\flutter-apk\app-debug.apk`
- APK 大小约 `151 MB`。
- 当前 Windows Flutter 只检测到 `Windows`、`Chrome`、`Edge`，未检测到 Android 手机，因此尚未执行真机安装。

1. 设置页确认 API 地址是：

```text
http://192.168.137.239:8000
```

2. 控制页点击 `Start preview`。
3. 看到画面后点击 `Start YOLO`。
4. 观察控制页 YOLO 状态里的 `Frames` 和 `Last check` 是否持续变化。
5. 手动方向控制仍然走 TCP，如果方向按钮失败，优先查 TCP host/port，不要先查 HTTP snapshot。

## 7. 并发性能验证

建议开 4 个终端。

如果已经运行过 Windows 同步脚本，也可以先在小车宿主机上一键跑基准测试：

```bash
cd /home/jetson/Project/car10th
bash scripts/robot_camera_yolo_benchmark.sh
```

默认会运行 30 秒，结果写入：

```text
/tmp/car10th_camera_yolo_benchmark/
```

重点看：

- `snapshot_latency.csv`：大多数 `http_code` 应为 `200`，`total_time_sec` 应多数小于 `3`
- `monitor_status.json`：`total_frames` 应增长，`last_error` 应为空
- `tegrastats.log`：观察 CPU/GPU/内存是否持续打满或内存持续上涨

如需延长到 60 秒：

```bash
DURATION_SEC=60 bash scripts/robot_camera_yolo_benchmark.sh
```

手动分终端验证步骤如下。

终端 A：看 Jetson 负载。

```bash
tegrastats
```

终端 B：看图像话题是否稳定。

```bash
ros2 topic hz /image_raw
```

终端 C：模拟 App snapshot 刷新。

```bash
while true; do
  date +"%H:%M:%S"
  curl -sS --max-time 10 \
    "http://127.0.0.1:8000/api/inspection/camera/snapshot?topic_name=/image_raw&timeout_sec=3" \
    -o /tmp/app_snapshot.jpg
  sleep 1
done
```

终端 D：启动 YOLO 监控并看状态。

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

watch -n 1 'curl -s http://127.0.0.1:8000/api/inspection/monitor/status'
```

通过标准：

- snapshot 请求多数能在 3 秒内返回
- `/image_raw` 频率没有明显掉到 0
- `monitor/status.total_frames` 持续增长
- `last_error` 为空或不是连续出现
- `tegrastats` 中内存没有持续上涨到危险区间
- App 手动控车 TCP 仍可响应

停止 YOLO：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/stop
```

## 8. 当前取舍和风险

- HTTP snapshot 会反复创建短生命周期 ROS 订阅，适合 1 FPS 左右验证，不适合高帧率长期直播。
- 如果 App 需要 5 FPS 以上预览，下一步应做 ai_service 内部常驻订阅缓存，再对外提供 MJPEG。
- WebSocket 更适合推送检测结果、告警和状态，不建议第一步就用它传图片。
- 同时跑三模型压力更大；性能验证阶段可以先只开 `puddle`、`fod`，再加 `crack`。
- 手机热点延迟和丢包会影响 App 预览体验，但不一定代表 Jetson 推理扛不住。
- Astra Plus 彩色流当前不稳定，默认仍使用 usb_cam 的 `/image_raw`。
