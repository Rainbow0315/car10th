# 路面裂缝/水洼/异物模型微调优化说明

本文档给负责模型优化的同学或 AI 助手使用。目标是把 `crack`、`puddle`、`fod` 三个检测模型微调后，产出能直接替换到本项目 AI 服务里的 `.pt` 权重，并提供可复现实验记录。

## 1. 当前项目接入方式

后端 AI 服务入口：

```text
backend/apps/ai_service/pipelines/inspection.py
```

当前三个模型名：

```text
crack   路面裂缝
puddle  水洼/积水
fod     异物/障碍物
```

默认权重路径在：

```text
backend/apps/ai_service/weights/crack_detect.pt
backend/apps/ai_service/weights/puddle_detect.pt
backend/apps/ai_service/weights/fod_detect.pt
```

配置文件：

```text
backend/common/config/settings.py
```

当前推理阈值：

```text
detection_conf = 0.25
detection_iou = 0.45
inspection_alarm_min_confidence = 0.6
```

注意：`detection_conf` 是模型推理时的初筛阈值，`inspection_alarm_min_confidence` 是最终是否入库/告警的阈值。现在低于 `0.6` 的检测结果不会报到告警中心。

## 2. 微调目标

每个模型优化后至少要满足：

```text
1. 能在车载 USB 相机画面上稳定检测目标。
2. 大平地、普通地面纹理、阴影、反光不能大量误报。
3. 置信度分布合理，真实目标尽量高于 0.6，误检尽量低于 0.6。
4. 输出格式仍然是 YOLO 检测框，能被现有后端读取。
5. 权重文件最终仍以 .pt 形式交付。
```

三个模型的建议关注点：

```text
crack:
  重点降低地砖缝、阴影、划痕、反光线误报。

puddle:
  重点区分真实积水、地面反光、光斑、深色地面。

fod:
  重点区分真实异物、路面纹理、车轮影子、远处小噪点。
```

## 3. 数据集准备

建议每类模型单独维护一个数据集目录：

```text
datasets/
  crack/
    images/
      train/
      val/
      test/
    labels/
      train/
      val/
      test/
    data.yaml
  puddle/
    images/
    labels/
    data.yaml
  fod/
    images/
    labels/
    data.yaml
```

YOLO 标签格式：

```text
class_id x_center y_center width height
```

坐标必须是归一化后的 0 到 1。

`data.yaml` 示例：

```yaml
path: /absolute/path/to/datasets/crack
train: images/train
val: images/val
test: images/test
names:
  0: crack
```

水洼：

```yaml
names:
  0: puddle
```

异物：

```yaml
names:
  0: fod
```

如果一个模型内部要分严重程度，可以保留多类别，例如：

```yaml
names:
  0: crack_low
  1: crack_medium
  2: crack_high
```

但要提前同步给后端同学，因为告警类型映射会读 `label`。

## 4. 标注规范

### 4.1 裂缝 crack

标注规则：

```text
1. 框住可见裂缝主体，尽量贴合裂缝区域。
2. 多条独立裂缝分别标。
3. 地砖缝、正常施工缝、阴影线不要标为裂缝。
4. 过细且肉眼难确认的裂缝，建议先放入 hard_negative，不直接标正样本。
```

必须加入负样本：

```text
1. 普通水泥地/沥青地
2. 地砖缝
3. 阴影
4. 反光线
5. 划痕但不是裂缝
```

### 4.2 水洼 puddle

标注规则：

```text
1. 框住可见积水区域。
2. 如果只有轻微反光但无积水，不标。
3. 透明水洼边缘不清时，按可见边界标。
4. 大面积积水可以一个框覆盖主体。
```

必须加入负样本：

```text
1. 光照反光
2. 深色地面
3. 影子
4. 地面污渍
5. 镜面材质但无积水
```

### 4.3 异物 fod

标注规则：

```text
1. 标注会影响小车通行或巡检安全的物体。
2. 框住物体外接矩形。
3. 很远、很小、无法确认的目标先不标。
4. 固定设施不要标成异物，例如墙角、路牌、固定管线。
```

必须加入负样本：

```text
1. 空地面
2. 车轮影子
3. 路边固定设施
4. 地面纹理
5. 不影响通行的小污点
```

## 5. 数据划分建议

推荐比例：

```text
train: 70%
val:   20%
test:  10%
```

注意：

```text
1. 同一段视频抽出来的连续帧不要同时放进 train 和 val/test。
2. val/test 必须包含真实车载场景，不要只用网上图片。
3. 每类至少准备一批 hard negative，大平地误报就主要靠这些负样本压下去。
```

最低建议数量：

```text
每类正样本: 300 张以上
每类负样本: 300 张以上
更理想: 每类 1000+ 张，并覆盖不同光照/角度/地面材质
```

## 6. 训练环境建议

训练建议在 Windows 工作站或有 GPU 的服务器上完成，不建议直接在 Jetson 上训练。

推荐 Python 环境：

```text
Python 3.8 到 3.10
PyTorch 与 CUDA 匹配
ultralytics
opencv-python
numpy
```

如果用 Ultralytics YOLOv8 训练：

```bash
pip install ultralytics opencv-python numpy
```

如果继续沿用 YOLOv7，需要使用 YOLOv7 官方训练仓库，并保证导出的 `.pt` 能被本项目的 `YoloV7Detector` 加载。

## 7. 推荐训练方式

### 7.1 裂缝模型 crack

当前后端 `CrackDetector` 使用 `ultralytics.YOLO` 加载，因此裂缝模型推荐直接用 YOLOv8/Ultralytics 训练。

命令模板：

```bash
yolo detect train ^
  model=yolov8n.pt ^
  data=datasets/crack/data.yaml ^
  imgsz=640 ^
  epochs=100 ^
  batch=16 ^
  patience=30 ^
  project=runs/road_damage ^
  name=crack_v1
```

如果目标比较细小，可以尝试：

```bash
yolo detect train model=yolov8s.pt data=datasets/crack/data.yaml imgsz=960 epochs=120 batch=8 project=runs/road_damage name=crack_v2_img960
```

### 7.2 水洼模型 puddle

当前后端 `puddle` 使用 `YoloV7Detector`，也就是 YOLOv7 权重加载逻辑。推荐两条路线二选一：

```text
路线 A: 继续训练 YOLOv7，保持后端不改。
路线 B: 改后端让 puddle 也走 Ultralytics YOLO，然后用 YOLOv8 训练。
```

为了减少接入风险，先选路线 A。

YOLOv7 命令模板：

```bash
python train.py ^
  --workers 8 ^
  --device 0 ^
  --batch-size 16 ^
  --data datasets/puddle/data.yaml ^
  --img 640 640 ^
  --cfg cfg/training/yolov7.yaml ^
  --weights yolov7.pt ^
  --name puddle_v1 ^
  --hyp data/hyp.scratch.p5.yaml ^
  --epochs 100
```

### 7.3 异物模型 fod

当前后端 `fod` 也使用 `YoloV7Detector`。同样建议先保持 YOLOv7。

命令模板：

```bash
python train.py ^
  --workers 8 ^
  --device 0 ^
  --batch-size 16 ^
  --data datasets/fod/data.yaml ^
  --img 640 640 ^
  --cfg cfg/training/yolov7.yaml ^
  --weights yolov7.pt ^
  --name fod_v1 ^
  --hyp data/hyp.scratch.p5.yaml ^
  --epochs 100
```

## 8. 重点优化策略

### 8.1 降低大平地误报

必须做 hard negative 训练。把现场误报图片收集起来，放进训练集：

```text
images/train/xxx.jpg
labels/train/xxx.txt
```

负样本的 `.txt` 标签文件应为空文件，表示这张图没有目标。

建议每轮现场测试后：

```text
1. 保存误报帧
2. 判断属于 crack/puddle/fod 哪个模型误报
3. 加入对应模型数据集的负样本
4. 重新训练或继续微调
5. 对比误报是否下降
```

### 8.2 调整置信度分布

训练后看 val/test 结果，不只看 mAP，还要看：

```text
1. 真实目标的 confidence 是否多数高于 0.6
2. 误检的 confidence 是否多数低于 0.6
3. 在车载画面中是否有连续帧误报
```

如果误检普遍高于 0.6：

```text
1. 增加 hard negative
2. 降低过强的数据增强
3. 检查标注是否把非目标误标成目标
4. 增加同场景的正常地面样本
```

### 8.3 类别不要混乱

三个模型最好分开训练、分开评估：

```text
crack_detect.pt
puddle_detect.pt
fod_detect.pt
```

不要把水洼和异物混到一个模型里，除非后端也同步改为多类别统一模型。

## 9. 验收指标

每个模型交付前至少提供：

```text
1. best.pt 权重
2. data.yaml
3. 训练命令
4. 训练结果目录 runs/.../results.png
5. val 指标: precision / recall / mAP50 / mAP50-95
6. 现场测试图片或视频结果
7. 误报样例和漏检样例
```

建议验收门槛：

```text
precision >= 0.80
recall >= 0.70
mAP50 >= 0.80
现场大平地连续测试 2 分钟，不能持续刷告警
```

如果模型召回很高但误报多，优先提升 precision。

## 10. 权重命名规范

训练产物不要直接覆盖旧文件，先按版本命名：

```text
crack_detect_v20260712.pt
puddle_detect_v20260712.pt
fod_detect_v20260712.pt
```

确认可用后再复制为后端默认文件名：

```text
backend/apps/ai_service/weights/crack_detect.pt
backend/apps/ai_service/weights/puddle_detect.pt
backend/apps/ai_service/weights/fod_detect.pt
```

建议同时保存版本说明：

```text
backend/apps/ai_service/weights/README.md
```

内容示例：

```text
crack_detect.pt
- 来源: crack_v3_img960
- 数据: 现场裂缝 860 张，负样本 1200 张
- 指标: precision 0.86, recall 0.74, mAP50 0.88
- 备注: 主要修复地砖缝误报
```

## 11. 本项目替换权重步骤

在车上或本地项目中：

```bash
cd /root/car10th/backend
mkdir -p apps/ai_service/weights
```

复制新权重：

```bash
cp /path/to/crack_detect_v20260712.pt apps/ai_service/weights/crack_detect.pt
cp /path/to/puddle_detect_v20260712.pt apps/ai_service/weights/puddle_detect.pt
cp /path/to/fod_detect_v20260712.pt apps/ai_service/weights/fod_detect.pt
```

重启 AI 服务：

```bash
cd /root/car10th/backend
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
uvicorn apps.ai_service.main:app --host 0.0.0.0 --port 8002
```

如果 AI 服务已经在跑，先停止旧进程再启动。

## 12. 单张图片测试

请求 AI 服务：

```bash
curl -X POST http://127.0.0.1:8002/api/inspection/detect-image \
  -H "Content-Type: application/json" \
  -d '{
    "image_path": "/root/car10th/backend/test_images/test.jpg",
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["crack", "puddle", "fod"]
  }'
```

期望返回：

```json
{
  "summary": {
    "total_detections": 1,
    "has_risk": true,
    "labels": {
      "crack": 1
    }
  },
  "results": {
    "crack": {
      "count": 1,
      "detections": [
        {
          "label": "crack",
          "confidence": 0.83,
          "bbox": [100.0, 120.0, 300.0, 180.0]
        }
      ]
    }
  }
}
```

## 13. ROS 图像话题测试

车上当前可用 RGB 图像话题是：

```text
/image_raw
```

测试请求：

```bash
curl -X POST http://127.0.0.1:8002/api/inspection/detect-ros-image \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "/image_raw",
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["crack", "puddle", "fod"],
    "timeout_sec": 5
  }'
```

如果返回“未从 topic 收到图像帧”，先确认：

```bash
ros2 topic list
ros2 topic hz /image_raw
```

## 14. 连续检测测试

启动连续检测：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/start \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "/image_raw",
    "interval_sec": 1.0,
    "timeout_sec": 5.0,
    "robot_code": "robot_001",
    "camera_code": "usb_cam",
    "enabled_models": ["crack", "puddle", "fod"]
  }'
```

查看状态：

```bash
curl http://127.0.0.1:8000/api/inspection/monitor/status
```

停止连续检测：

```bash
curl -X POST http://127.0.0.1:8000/api/inspection/monitor/stop
```

## 15. 微调迭代流程

建议每次优化按下面闭环执行：

```text
1. 采集现场图像或视频
2. 挑出误报、漏检、真实目标样本
3. 更新标签
4. 重新训练
5. 本地 val/test 验证
6. 替换到 AI service
7. 用 /image_raw 连续检测验证
8. 记录误报率和漏检样例
9. 再进入下一轮数据补充
```

## 16. 交付给后端同学的清单

每次交付请给以下内容：

```text
weights/
  crack_detect_vYYYYMMDD.pt
  puddle_detect_vYYYYMMDD.pt
  fod_detect_vYYYYMMDD.pt

report/
  crack_report.md
  puddle_report.md
  fod_report.md
  confusion_samples/
    false_positive/
    false_negative/
```

每个 report 至少写：

```text
1. 使用的数据量
2. 训练命令
3. 训练轮数
4. 最好权重路径
5. precision / recall / mAP50
6. 推荐推理 conf
7. 典型误报
8. 典型漏检
9. 是否建议上线
```

## 17. AI 助手执行提示词

如果让 AI 助手继续微调，可以直接把下面这段发给它：

```text
你要负责优化 car10th 项目的路面检测模型。项目后端在 backend/apps/ai_service，当前模型包括 crack、puddle、fod。请按 docs/road_damage_model_finetune.md 的规范处理数据集、训练模型、评估指标，并输出可替换到 backend/apps/ai_service/weights/ 的 .pt 权重。重点目标是降低大平地、地面纹理、阴影、反光导致的误报，让真实目标置信度尽量高于 0.6，误检低于 0.6。每次训练必须保存训练命令、data.yaml、指标和误报/漏检样例。
```

