# 引导找车最短闭环

## 目标

当前版本先做两件事：

1. 小车导航到固定坐标“车位一”。
2. 到达后抓取 `/image_raw`，调用车牌检测模型，并与用户绑定车牌比对。

## 后端链路

App -> `web_api:8000/api/car-finding/*`

- 导航：`car_finding_service` -> `slam_service.publish_goal()` -> `ros_bridge:8001/api/slam/goal` -> ROS2 `/goal_pose`
- 车牌：`car_finding_service` -> `inspection_service.detect_ros_plate()` -> `ai_service:8002/api/inspection/detect-ros-plate` -> plate model

## 接口

```powershell
$base = "http://192.168.137.239:8000"

Invoke-RestMethod "$base/api/car-finding/parking-spots"

$body = @{ user_id="demo_user"; plate_number="A12345" } | ConvertTo-Json
Invoke-RestMethod "$base/api/car-finding/bind-plate" -Method Post -ContentType "application/json" -Body $body
Invoke-RestMethod "$base/api/car-finding/park-at-spot-one" -Method Post -ContentType "application/json" -Body $body

# 会真实下发导航目标。先确认车位一坐标已经配置正确。
Invoke-RestMethod "$base/api/car-finding/guide-to-spot-one" -Method Post -ContentType "application/json" -Body (@{ user_id="demo_user" } | ConvertTo-Json)

$verify = @{
  user_id="demo_user"
  topic_name="/image_raw"
  timeout_sec=8.0
  robot_code="robot_001"
  camera_code="usb_cam"
} | ConvertTo-Json
Invoke-RestMethod "$base/api/car-finding/verify-at-spot-one" -Method Post -ContentType "application/json" -Body $verify
```

## 车位一坐标

默认是占位值：

```text
PARKING_SPOT_ONE_X=0.0
PARKING_SPOT_ONE_Y=0.0
PARKING_SPOT_ONE_YAW=0.0
PARKING_SPOT_ONE_FRAME_ID=map
```

实测前要把车位一的 map 坐标写入车端 `/root/car10th/backend/.env`，然后重启 `web_api`。

## 当前真车状态

- 车 1 `192.168.137.239`：找车接口已部署；plate 模型调用成功，当前画面无车牌时返回 `matched=false`、`completed_models=["plate"]`。
- 车 2 `192.168.137.95`：找车接口、plate 代码和权重已部署；容器缺少 `torch` / `ultralytics`，所以 plate 推理会返回 `failed_models=["plate"]`。最快修复是复用车 1 的 Docker 镜像或补齐 GPU 推理依赖。
