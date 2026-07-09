# 后端控车联调说明

这条链路现在分成两层：

1. `ros_bridge` 运行在车上，直接向 ROS2 发布 `/cmd_vel`
2. 主后端 `web_api` 运行在 `8000`，通过 HTTP 转发到 `ros_bridge`

## 1. 在小车上启动底盘和 ROS bridge

先启动底盘驱动：

```bash
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
ros2 launch yahboomcar_bringup yahboomcar_bringup_X3_launch.py
```

新开一个终端，再启动 `ros_bridge`：

```bash
cd /path/to/car10th/backend
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
python -m apps.ros_bridge.main
```

先检查健康状态：

```bash
curl http://127.0.0.1:8001/health
```

如果 `subscriber_count` 为 `0`，说明底盘节点还没有订阅到 `/cmd_vel`，这时小车一定不会动。

## 2. 直接测试 ros_bridge

推荐先在车上本机测试：

```bash
curl -X POST "http://127.0.0.1:8001/api/teleop/cmd-vel" \
  -H "Content-Type: application/json" \
  --data-raw '{"linear_x":0.15,"linear_y":0.0,"angular_z":0.0,"duration":1.5,"rate_hz":10.0}'
```

正常情况下返回里应该看到：

- `status: accepted`
- `topic_name: /cmd_vel`
- `subscriber_count: 1` 或更大

如果返回 `409` 且提示 `No active subscriber on /cmd_vel`，请在车上继续检查：

```bash
ros2 topic info /cmd_vel
ros2 topic echo /cmd_vel
ros2 node list
```

## 3. 通过主后端 8000 控车

主后端新增了同名代理接口：

- `GET /api/teleop/health`
- `POST /api/teleop/cmd-vel`
- `POST /api/teleop/stop`

如果主后端和 `ros_bridge` 不在同一台机器上，设置环境变量：

```bash
export ROS_BRIDGE_HTTP_URL="http://192.168.43.34:8001"
```

然后从 VM 或其他机器调用主后端：

```bash
curl -X POST "http://<backend-host>:8000/api/teleop/cmd-vel" \
  -H "Content-Type: application/json" \
  --data-raw '{"linear_x":0.15,"linear_y":0.0,"angular_z":0.0,"duration":1.5,"rate_hz":10.0}'
```

## 4. 你这个项目里最关键的判定标准

只有下面 3 个条件同时成立，才能说明“后端控车”真正打通：

1. `8001/health` 返回 `status=ok`
2. `subscriber_count >= 1`
3. `ros2 topic info /cmd_vel` 能看到底盘订阅者
