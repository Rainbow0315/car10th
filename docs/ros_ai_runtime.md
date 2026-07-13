# ROS 图像接 AI 检测联调运行说明

本文档记录当前已验证通过的 Jetson 小车运行方式，以及后续实现“Flutter 手机 App 收到模型检测预警”的阶段拆解。

## 1. 当前已验证环境

- 小车 IP：`192.168.137.239`
- SSH 用户：`jetson`
- ROS 容器名：`ros_x3_fixed`
- ROS_DOMAIN_ID：`30`
- 车端项目路径：`/home/jetson/Project/car10th`
- 容器内项目路径：`/root/car10th`
- 后端目录：`/root/car10th/backend`
- 当前 RGB 图像话题：`/image_raw`
- AI 服务端口：`8002`

当前容器已经修复为可用 GPU 环境：

```bash
docker inspect ros_x3_fixed --format '{{.HostConfig.Runtime}} {{.HostConfig.Privileged}} {{.HostConfig.NetworkMode}}'
```

期望结果：

```text
nvidia true host
```

容器内 CUDA 验证：

```bash
docker exec ros_x3_fixed bash -lc \
  'python3 -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.device_count())"'
```

已验证结果：

```text
2.0.0+nv23.05
True
1
```

## 2. 当前容器与镜像

当前运行容器：

```bash
docker ps --filter name=ros_x3_fixed
```

已保存可用镜像：

```text
car10th_ros_x3_ai:working_latest
car10th_ros_x3_ai:working_20260712_163605
```

旧容器保留：

```text
ros_x3_fixed_old_20260712_161002
```

如果后续需要用已修复环境重建容器，应保留以下关键参数：

```bash
docker run -dit \
  --name ros_x3_fixed \
  --runtime nvidia \
  --privileged \
  --network host \
  -e DISPLAY \
  -e QT_X11_NO_MITSHM=1 \
  -e ROS_DOMAIN_ID=30 \
  -v /dev/bus/usb:/dev/bus/usb \
  -v /home/jetson/code/yahboomcar_ws:/root/yahboomcar_ros2_ws/yahboomcar_ws \
  -v /home/jetson/code/software/library_ws:/root/yahboomcar_ros2_ws/software/library_ws \
  -v /home/jetson/rosboard:/root/rosboard \
  -v /home/jetson/maps:/root/maps \
  -v /home/jetson/Project/car10th:/root/car10th \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  car10th_ros_x3_ai:working_latest \
  /bin/bash
```

## 3. 启动 RGB 图像话题

进入小车后执行：

```bash
ssh jetson@192.168.137.239
docker exec -it ros_x3_fixed bash
```

容器内启动 `usb_cam`：

```bash
export ROS_DOMAIN_ID=30
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ros2 run usb_cam usb_cam_node_exe \
  --ros-args \
  --params-file /opt/ros/foxy/share/usb_cam/config/params.yaml
```

另开终端验证：

```bash
docker exec ros_x3_fixed bash -lc \
  'export ROS_DOMAIN_ID=30; source /opt/ros/foxy/setup.bash; source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash; source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash; ros2 topic list'
```

应看到：

```text
/image_raw
/camera_info
```

## 4. 启动 AI 服务

AI 服务依赖当前依赖容器内的：

- NVIDIA Jetson PyTorch：`torch==2.0.0+nv23.05`
- `torchvision==0.15.1`
- `ultralytics`
- `opencv-python-headless`
- YOLOv7 原仓库代码：`/root/yolov7`
- CUDA/cuDNN 动态库

启动命令：

```bash
docker exec -d ros_x3_fixed bash -lc '
export ROS_DOMAIN_ID=30
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
export PYTHONPATH=/root/yolov7:$PYTHONPATH
cd /root/car10th/backend
python3 -m uvicorn apps.ai_service.main:app --host 0.0.0.0 --port 8002 > /tmp/ai_service.log 2>&1
'
```

健康检查：

```bash
docker exec ros_x3_fixed bash -lc \
  'curl -sS http://127.0.0.1:8002/health'
```

期望结果：

```json
{"status":"ok","service":"ai_service"}
```

查看日志：

```bash
docker exec ros_x3_fixed bash -lc 'tail -120 /tmp/ai_service.log'
```

## 5. 验证 ROS 图像抓帧与模型检测

默认三模型检测：

```bash
docker exec ros_x3_fixed bash -lc '
curl -sS --max-time 300 \
  -X POST http://127.0.0.1:8002/api/inspection/detect-ros-image \
  -H "Content-Type: application/json" \
  -d "{\"topic_name\":\"/image_raw\",\"timeout_sec\":10}"
'
```

已验证成功返回结构：

```json
{
  "device": "cuda",
  "summary": {
    "completed_models": ["crack", "puddle", "fod"],
    "failed_models": []
  }
}
```

如果只验证 YOLOv7 两个模型：

```bash
docker exec ros_x3_fixed bash -lc '
curl -sS --max-time 300 \
  -X POST http://127.0.0.1:8002/api/inspection/detect-ros-image \
  -H "Content-Type: application/json" \
  -d "{\"topic_name\":\"/image_raw\",\"timeout_sec\":10,\"enabled_models\":[\"puddle\",\"fod\"]}"
'
```

## 6. 当前关键修复点

1. `ros_x3_fixed` 必须带 Jetson GPU 设备权限运行，否则 `torch.cuda.is_available()` 为 `False`。
2. 容器必须能找到 CUDA/cuDNN 动态库，尤其是：
   - `libcurand.so.10`
   - `libcublas.so.11`
   - `libcudnn.so.8`
   - `libcudnn_ops_infer.so.8`
3. YOLOv7 权重是按原仓库对象 pickle 的，运行时需要 `/root/yolov7` 在 `PYTHONPATH` 中。
4. `ultralytics` 在 Jetson 环境下不要依赖 PyPI `torchvision.ops.nms`，当前容器内已改为使用 Ultralytics 纯 PyTorch NMS。
5. `astra_camera` 当前仍不是主线；临时稳定 RGB 输入是 `usb_cam` 发布的 `/image_raw`。

## 7. 后续阶段拆解：App 预警闭环

最终目标：手机 App 能实时/准实时收到模型检测出的道路病害或异物预警。

### 阶段一：持续摄像头输入与周期检测

目标：从“一次接口抓一帧”升级为“后台持续订阅图像 topic，按频率自动检测”。

建议实现：

- 新增 AI 后台 worker。
- 持续订阅 `/image_raw`。
- 按固定频率抽帧，例如 `1 FPS` 或 `0.5 FPS`。
- 每帧调用三模型检测。
- 检测结果统一落成结构化事件。

需要确认：

- 检测频率：实时、每秒一次、还是只在巡检任务中启用。
- 是否需要保存每次抓帧原图和标注图。

### 阶段二：模型输出结构标准化

目标：把 `crack/puddle/fod` 的输出统一成后端和 App 都能消费的预警结构。

建议字段：

- `alarm_type`：`crack` / `puddle` / `fod`
- `label`
- `confidence`
- `severity`
- `bbox`
- `image_path`
- `robot_code`
- `camera_code`
- `detected_at`
- `status`：`new` / `acknowledged` / `resolved`

需要确认：

- 裂缝、积水、异物的严重程度分级规则。
- 低置信度结果是否直接丢弃，还是作为低级预警保存。

### 阶段三：数据库结构改动

目标：后端持久化检测事件，App 可以查询历史和当前未处理预警。

建议新增表：

- `inspection_alarm`
- `inspection_alarm_detection`
- `inspection_frame`

核心能力：

- 写入每次风险检测事件。
- 查询未处理预警列表。
- 查询预警详情。
- 标记已读/已处理。

需要确认：

- 是否要保留所有无风险检测记录，还是只保留有风险帧。
- 图片路径是存本地路径、HTTP URL，还是对象存储 URL。

### 阶段四：后端推送到 App

目标：手机 App 不需要轮询也能收到新预警。

可选方案：

1. MQTT：符合当前项目已有 MQTT 方向，适合机器人状态和预警推送。
2. WebSocket：适合 App 前端实时订阅。
3. HTTP 轮询：实现最简单，但实时性和体验较弱。

建议优先方案：

- 后端内部保存数据库记录。
- 同时通过 MQTT topic 推送预警摘要。
- App 进入预警页时再 HTTP 拉取详情。

需要确认：

- App 当前是否已经稳定接入 MQTT。
- 预警是否需要离线补偿，即 App 离线后上线仍能看到未处理告警。

### 阶段五：Flutter App 展示与交互

目标：App 中出现可用的预警列表、详情页和处理动作。

建议页面：

- 预警列表：按时间倒序显示未处理/历史预警。
- 预警详情：展示图片、检测框、模型、置信度、位置/机器人信息。
- 处理动作：确认、忽略、标记已处理。

需要确认：

- 是否必须在图片上绘制检测框。
- 是否需要声音/震动/系统通知。

## 8. 持续检测与 App 预警推送

本阶段新增目标：

- 后端持续从 `/image_raw` 抽帧检测。
- 只在模型发现风险时保存告警记录。
- 告警写入 `alarm_logs`。
- 告警通过 MQTT `alarm/notify` 推送给 App。
- App 离线后仍可通过 HTTP 查询历史告警。

### 8.1 执行数据库迁移

在 `backend` 目录执行：

```bash
python3 scripts/run_migration.py db/migrations/003_extend_alarm_detection_fields.sql
```

新增字段：

- `camera_code`
- `detection_model`
- `detection_label`
- `bbox_json`
- `raw_result`

### 8.2 启动一次持续检测

确保 `usb_cam` 和 `ai_service` 已经运行，然后启动 `web_api`。

启动持续检测 worker：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/start \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "/image_raw",
    "interval_sec": 1.0,
    "timeout_sec": 10,
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["crack", "puddle", "fod"]
  }'
```

查看状态：

```bash
curl http://127.0.0.1:8000/api/inspection/monitor/status
```

停止持续检测：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/stop
```

只跑一轮检测并落库/推送：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/inspect-once \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "/image_raw",
    "interval_sec": 1.0,
    "timeout_sec": 10,
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["crack", "puddle", "fod"]
  }'
```

### 8.3 MQTT 预警 topic

预警 topic：

```text
alarm/notify
```

订阅测试：

```bash
mosquitto_sub -h 127.0.0.1 -p 1883 \
  -u parking_app -P parking_app_dev \
  -t alarm/notify -v
```

推送 payload 关键字段：

```json
{
  "alarm_id": 1,
  "alarm_no": "ALM20260712163511823xxxxxx",
  "robot_code": "robot_001",
  "camera_code": "usb_cam",
  "alarm_type": "crack",
  "risk_level": "medium",
  "confidence": 0.72,
  "detection_model": "crack",
  "detection_label": "crack",
  "bbox": [152.7, 276.6, 639.4, 330.1],
  "image_path": "/root/car10th/backend/runtime/inspection/monitor_frames/xxx.jpg",
  "detected_at": "2026-07-12T16:35:11.823"
}
```

### 8.4 App 补偿查询接口

查询告警列表：

```bash
curl 'http://127.0.0.1:8000/api/inspection/alarms?limit=50'
```

查询单条告警：

```bash
curl http://127.0.0.1:8000/api/inspection/alarms/1
```

标记已处理：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/alarms/1/handle \
  -H "Content-Type: application/json" \
  -d '{"remark":"已现场确认并处理"}'
```

## 9. 后续建议

下一阶段优先做：

1. Flutter 增加真实 HTTP API base URL 和 token 管理。
2. Flutter 告警页从 `/api/inspection/alarms` 拉取真实列表。
3. Flutter 增加 MQTT 客户端，订阅 `alarm/notify`。
4. MQTT 收到预警后刷新列表，并在前台提示。
5. 后续再接系统通知、声音/震动和图片框选显示。

在以下问题确认前，不建议直接写死方案：

- Flutter 真实网络层：HTTP API base URL、鉴权 token、刷新策略。
- Flutter MQTT 客户端：连接生命周期、断线重连、前后台通知。
- 预警严重程度分级规则。
