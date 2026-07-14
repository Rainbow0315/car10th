# 多车协同前端控制联调

记录时间：2026-07-13

## 已接入的前端入口

Flutter 控制页：`mobile_app/lib/features/control/control_page.dart`

新增能力：

- 单车控制目标选择：`小车1 robot_001` / `小车2 robot_002`
- 单车方向、灯光、摇杆、四轮速度仍走 Yahboom TCP 私有协议
- 多车协同区支持勾选车辆
- `选中车辆前进 5s` 会一次请求后端，由后端并发打到每台车的 `ros_bridge`
- `全部停止` 会一次请求后端，由后端并发停止选中车辆

## 单车控制链路

单车控制目标选择后，会更新 AppSettings 中的 TCP 目标：

```text
robot_001 -> 192.168.137.239:6001
robot_002 -> 192.168.137.89:6001
```

链路：

```text
ControlPage 单车方向按钮
-> Repository TCP 私有协议帧
-> 目标小车 tcp_car_bridge / Yahboom TCP 服务
-> ROS2 /cmd_vel 或原厂底盘控制
-> driver_node / 底盘
```

如果单车按钮失败，优先查：

```powershell
Test-NetConnection 192.168.137.239 -Port 6001
Test-NetConnection 192.168.137.89 -Port 6001
```

以及车端：

```bash
ss -lntup | grep -E '6001|6000'
pgrep -af 'tcp_car_bridge|Rosmaster-App|app.py'
```

## 多车协同链路

前端多车按钮不逐台直连小车，而是打 Windows/后端接口：

```text
ControlPage 多车协同按钮
-> POST /api/fleet/teleop/cmd-vel
-> web_api 并发请求每台车 ros_bridge
-> POST http://<robot_ip>:8001/api/teleop/cmd-vel
-> ROS2 /cmd_vel
-> driver_node / 底盘
```

停止链路：

```text
ControlPage 全部停止
-> POST /api/fleet/teleop/stop
-> web_api 并发请求每台车 ros_bridge
-> POST http://<robot_ip>:8001/api/teleop/stop
```

当前后端兜底 ros_bridge 地址：

```text
robot_001 -> http://192.168.137.239:8001
robot_002 -> http://192.168.137.89:8001
```

如果 fleet 心跳中有 `agent_ip`，后端优先使用心跳里的 IP；没有时才使用上面的兜底地址。

## 接口验证

零速度冒烟，不让车移动：

```powershell
$body = @{
  robot_codes=@('robot_001','robot_002')
  linear_x=0.0
  linear_y=0.0
  angular_z=0.0
  duration=0.0
  rate_hz=10.0
  wait_for_subscriber_timeout=1.0
  require_all_ready=$false
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/api/fleet/teleop/cmd-vel' `
  -ContentType 'application/json' `
  -Body $body
```

真实前进 5 秒：

```powershell
$body = @{
  robot_codes=@('robot_001','robot_002')
  linear_x=0.12
  linear_y=0.0
  angular_z=0.0
  duration=5.0
  rate_hz=10.0
  wait_for_subscriber_timeout=1.0
  require_all_ready=$false
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/api/fleet/teleop/cmd-vel' `
  -ContentType 'application/json' `
  -Body $body
```

停止：

```powershell
$body = @{ robot_codes=@('robot_001','robot_002') } |
  ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/api/fleet/teleop/stop' `
  -ContentType 'application/json' `
  -Body $body
```

## 当前实测结果

2026-07-13，车2零速度接口冒烟通过：

```text
POST /api/fleet/teleop/cmd-vel
robot_002 ok=true status_code=200 ros_bridge_url=http://192.168.137.89:8001
```

双车零速度请求中，车1当前 ros_bridge 超时：

```text
robot_001 ok=false error=timed out ros_bridge_url=http://192.168.137.239:8001
robot_002 ok=true  status_code=200
```

这说明前端和后端接口已经能明确指出是哪台车链路失败。恢复车1后，先查：

```powershell
Invoke-RestMethod http://192.168.137.239:8001/health
```

如果超时，查车1网络、`ros_x3_fixed`、`apps.ros_bridge.main` 进程。恢复后，前端多车按钮就会同时向两台车下发。
