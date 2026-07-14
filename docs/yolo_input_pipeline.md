# 巡航 YOLO 输入链路与新模型接入说明

这份文档给模型侧同学看。当前只接“巡航过程中的路面巡检模型”，也就是路面缺陷、积水/水洼、危险异物检测。车牌识别是后续找车业务的单独逻辑，先不要接入巡航 monitor，避免 Jetson 内存压力叠加。

## 1. 当前巡航输入链路

```text
usb_cam 独占打开摄像头 /dev/video0
  -> ROS2 topic: /image_raw
  -> ai_service 内部持久订阅 /image_raw，维护 latest-frame cache
  -> detect-ros-image 从 cache 取最新帧并保存成 jpg
  -> inspection_pipeline 把 jpg 文件路径传给 unified detector
  -> detector.detect(image_path) 执行 YOLO 推理
  -> web_api monitor 将检测结果转成告警
```

模型侧只需要保证模型能接收 `image_path: str`，返回检测框列表。不要直接打开 `/dev/video0`，不要从 App MJPEG 流里截帧。

## 2. 业务拆分原则

巡航检测：

```text
enabled_models = ["unified"]
权重: backend/apps/ai_service/weights/road_inspection_6class.pt
目标: 路面缺陷 / 水洼积水 / 危险异物
```

车牌检测：

```text
enabled_models = ["plate"]
目标: 后续找车、车牌 OCR
状态: 先不接巡航流程
```

原因：巡航时还要跑直播、导航、雷达和后端服务。车牌模型如果和路面巡检模型一起常驻，Jetson Orin Nano 内存压力会明显变大。

## 3. 兼容旧请求

以前接口里可能传：

```json
["crack", "puddle", "fod"]
```

现在后端会把这些旧值折叠成一次：

```json
["unified"]
```

也就是说旧 App 或脚本即使还传 `crack/puddle/fod`，也不会加载三个模型、跑三遍推理。

## 4. 模型文件放置

默认权重文件：

```text
backend/apps/ai_service/weights/road_inspection_6class.pt
```

车上容器路径：

```text
/root/car10th/backend/apps/ai_service/weights/road_inspection_6class.pt
```

权重不要提交 Git。部署时手动放到车上对应目录，或通过同步脚本拷贝到车上。

## 5. 后端接入位置

核心文件：

```text
backend/apps/ai_service/pipelines/inspection.py
backend/apps/ai_service/detectors/crack_detector.py
backend/common/config/settings.py
backend/common/schemas/inspection.py
backend/apps/web_api/services/inspection_alarm_service.py
```

当前实现复用 `CrackDetector` 的 Ultralytics YOLO 加载逻辑，通过 `model_tag="unified"` 加载：

```python
settings.model_unified
```

模型推理入口仍然是：

```python
detect(image_path: str) -> list[dict]
```

返回格式：

```python
[
    {
        "label": "puddle",
        "confidence": 0.87,
        "bbox": [120.0, 80.0, 300.0, 220.0],
        "extra": {
            "class_id": 0,
            "model": "unified"
        }
    }
]
```

字段要求：

| 字段 | 类型 | 说明 |
|---|---|---|
| `label` | string | 类别名。建议用 `crack`、`puddle`、`fod`，中文也兼容“裂缝/破损/积水/水洼/异物/障碍/垃圾” |
| `confidence` | float | 0 到 1 |
| `bbox` | list[float] | 原图像素坐标 `[x1, y1, x2, y2]` |
| `extra.class_id` | int | 模型类别 id |
| `extra.model` | string | 当前为 `unified` |

## 6. 告警类型映射

`web_api` 会按 `model + label` 判断告警类型：

```text
crack / 裂缝 / 破损      -> crack
puddle / water / 积水 / 水洼 -> water
fod / foreign / debris / 异物 / 障碍 / 垃圾 -> foreign_object
pothole / 坑             -> pothole
```

所以模型类别名最好保持清晰，不要只输出 `class_0` 这种无法映射业务含义的 label。

## 7. 单帧联调命令

进入车上 ROS 容器：

```bash
docker exec -it ros_x3_fixed bash
```

加载环境：

```bash
export ROS_DOMAIN_ID=30
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1

source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
cd /root/car10th/backend
```

确认摄像头有帧：

```bash
ros2 topic list | grep image_raw
ros2 topic hz /image_raw
curl http://127.0.0.1:8002/api/camera/status
```

直接打 `ai_service` 单帧检测：

```bash
curl -X POST http://127.0.0.1:8002/api/inspection/detect-ros-image \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "/image_raw",
    "timeout_sec": 5,
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["unified"]
  }'
```

通过 App 同款网关测试：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/detect-ros-image \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "/image_raw",
    "timeout_sec": 5,
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["unified"]
  }'
```

## 8. 巡航连续检测 monitor

注意：路线巡航逻辑不读模型。`patrol_service` 只负责前端画出的路线、航点任务、定时/手动启动和导航目标下发：

```text
App 巡航任务 start
  -> web_api /api/patrol/tasks/{task_code}/start
  -> patrol_service 发布航点导航目标
  -> ros_bridge / ROS2 导航
```

如果业务上需要“边按路线巡航，边做路面 YOLO 检测”，由 App 或任务调度层同时启动两条独立链路：

```text
链路 A: /api/patrol/tasks/{task_code}/start      负责路线导航
链路 B: /api/inspection/monitor/start           负责 /image_raw -> unified YOLO -> 告警
```

这样巡航路线和模型推理互不绑定，后续也方便单独暂停检测、调整检测间隔或只跑导航演示。

手动启动：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/start \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "/image_raw",
    "interval_sec": 1.0,
    "timeout_sec": 5,
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["unified"]
  }'
```

看状态：

```bash
curl http://127.0.0.1:8000/api/inspection/monitor/status
```

停止：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/stop
```

## 9. 常见失败点

1. `/image_raw` 没有新帧：先查 `ros2 topic hz /image_raw` 和 `GET /api/camera/status`。
2. 权重不存在：确认 `road_inspection_6class.pt` 是否在 `backend/apps/ai_service/weights/`。
3. 类别名无法映射：检测结果有框但告警类型是 `other`，通常是 label 不包含 crack/puddle/fod 或中文业务词。
4. 内存压力大：先只跑 `enabled_models=["unified"]`，不要把 `plate` 放进巡航 monitor。

## 10. 模型侧最小交付

模型侧至少交付：

1. `road_inspection_6class.pt`
2. 类别 id 到 label 的映射
3. 输入尺寸要求
4. 推荐 `conf` / `iou`
5. 一张 `/image_raw` 抓图上的单帧检测 JSON

一句话：巡航模型只需要接 `image_path -> detections`，业务侧会负责从 `/image_raw` 抓帧、定时调用、落告警和给 App 展示。
