# 小车2环境配置与多车联调记录

记录时间：2026-07-13

## 当前结论

- 小车2 IP：`192.168.137.89`
- SSH：`jetson@yahboom`
- 容器名：`ros_x3_fixed`
- 镜像：`yahboomtechnology/ros-foxy:5.0.1`
- 小车2 ROS 域：`ROS_DOMAIN_ID=31`
- 小车1 ROS 域保持：`ROS_DOMAIN_ID=30`
- 小车2车队编号：`robot_002`
- 小车2 web_api MQTT client id：`parking_backend_robot_002`
- Windows 当前 WLAN IP：`192.168.137.20`

不要让小车1和小车2共用同一个 `ROS_DOMAIN_ID`。实测如果都用 `30`，DDS 会互相看到同名 `/cmd_vel`、`/goal_pose`、`/odom` 等 topic 和节点，存在串车风险。

也不要让多个后端共用同一个 `MQTT_CLIENT_ID`。实测车2 `web_api` 和 Windows 后端都使用 `parking_backend` 时，Mosquitto 会持续出现 `session taken over`，导致其中一个后端的 MQTT 连接被踢下线。

## 已验证闭环

### 1. 车2 ROS 基础链路

车2容器内已验证：

- `/odom` 有 1 个 publisher，能收到真实消息
- `/scan` 有 1 个 publisher，能收到真实消息
- `/camera/depth/image_raw` 有真实消息
- `/camera/depth/points` 有真实点云
- `/camera/color/image_raw` 有 publisher，但实测没有稳定真实帧

因此车2第一阶段不要默认依赖 Astra Plus 的 color 流。需要 RGB 时仍优先用 `usb_cam` 的 `/image_raw`。

### 2. App/API 链路

Windows 可访问：

```powershell
Invoke-RestMethod http://192.168.137.89:8000/health
Invoke-RestMethod http://192.168.137.89:8001/health
Invoke-RestMethod http://192.168.137.89:8000/api/slam/map
```

当前结果：

- `web_api:8000` 可用
- `ros_bridge:8001` 可用
- `/api/slam/map` 可返回结构化响应；没有 `/map` 时 `available=false`

### 3. 多车 MQTT/Fleet 闭环

Windows 本地已启动：

```powershell
docker compose up -d mysql mosquitto
```

本地后端用 Windows Python/venv 启动，健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

返回：

```json
{"status":"ok","service":"web_api","mqtt_connected":true}
```

已验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/fleet/robots
```

能看到：

- `robot_001` online，IP `192.168.137.239`
- `robot_002` online，IP `192.168.137.89`

单车命令闭环：

```powershell
$body = @{ command='set_mode'; payload=@{ mode='patrol' } } | ConvertTo-Json -Compress -Depth 5
$cmd = Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/api/fleet/robots/robot_002/commands' `
  -ContentType 'application/json' `
  -Body $body

Invoke-RestMethod "http://127.0.0.1:8000/api/fleet/commands/$($cmd.command_id)"
```

期望 `status=acked`。

双车批量命令闭环：

```powershell
$body = @{
  robot_codes=@('robot_001','robot_002')
  command='set_mode'
  payload=@{ mode='idle' }
  require_all_ready=$true
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/api/fleet/commands/batch' `
  -ContentType 'application/json' `
  -Body $body
```

实测两台车都能 ACK。

## 车2容器创建命令

车2已经创建好 `ros_x3_fixed`。如果需要重建，先确认旧容器是否要保留，再执行：

```bash
docker rm -f ros_x3_fixed

docker run -dit \
  --name ros_x3_fixed \
  --network host \
  --ipc host \
  --privileged \
  -e DISPLAY=${DISPLAY:-:0} \
  -e QT_X11_NO_MITSHM=1 \
  -e ROS_DOMAIN_ID=31 \
  -e ROBOT_TYPE=x3 \
  -e RPLIDAR_TYPE=a1 \
  -v /dev/bus/usb:/dev/bus/usb \
  -v /home/jetson/code/yahboomcar_ws:/root/yahboomcar_ros2_ws/yahboomcar_ws \
  -v /home/jetson/code/software/library_ws:/root/yahboomcar_ros2_ws/software/library_ws \
  -v /home/jetson/rosboard:/root/rosboard \
  -v /home/jetson/maps:/root/maps \
  -v /home/jetson/Project/car10th:/root/car10th \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  yahboomtechnology/ros-foxy:5.0.1 /bin/bash
```

## 车2推荐启动顺序

进入容器：

```bash
docker start ros_x3_fixed
docker exec -it ros_x3_fixed bash
```

容器内统一环境：

```bash
export ROS_DOMAIN_ID=31
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
export PYTHONUNBUFFERED=1

source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash

ln -sf /dev/ttyUSB1 /dev/myserial
ln -sf /dev/ttyUSB0 /dev/rplidar
chmod 666 /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 2>/dev/null || true
```

启动底盘和雷达：

```bash
nohup ros2 launch yahboomcar_nav laser_bringup_launch.py \
  > /tmp/laser_bringup_domain31.log 2>&1 &
```

启动 Astra Plus 深度相机：

```bash
nohup ros2 launch astra_camera astro_pro_plus.launch.xml \
  > /tmp/astra_plus.log 2>&1 &
```

启动车2 ROS 桥接和 API：

```bash
cd /root/car10th/backend

export MQTT_CLIENT_ID=parking_backend_robot_002

nohup python3 -m apps.ros_bridge.main \
  > /tmp/ros_bridge_robot_002.log 2>&1 &

nohup python3 -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000 \
  > /tmp/web_api_robot_002.log 2>&1 &
```

启动车2多车 agent：

```bash
cd /root/car10th/backend

PYTHONUNBUFFERED=1 nohup python3 -m apps.robot_agent.main \
  --robot-code robot_002 \
  --dry-run \
  > /tmp/robot_agent_robot_002.log 2>&1 &
```

`--dry-run` 表示只验证多车通信和 ACK，不直接驱动车轮。后续接真实运动控制时再去掉或扩展命令处理。

## RTAB-Map 和 Octomap 注意事项

`rtabmap_sync_launch.py` 已能启动，但依赖 `/camera/color/image_raw`、`/camera/depth/image_raw`、`/camera/color/camera_info` 同步。车2当前 Astra Plus color 流没有稳定真实帧，所以 RTAB-Map 会持续提示没有收到 RGBD 数据。

不要把 RTAB-Map 进程启动成功误判成建图成功。需要看日志里是否不再出现：

```text
Did not receive data since 5 seconds
```

`camera_octomap_launch.py` 原始版本不建议直接用。实测它引用了不存在的：

```text
yahboomcar_bringup_x1_launch.py
```

2026-07-13 已在车2的 Yahboom 工作空间中把 source 和 install 两处 launch 文件修成：

```text
yahboomcar_bringup_X3_launch.py
```

并已验证：

```bash
ros2 launch yahboomcar_slam camera_octomap_launch.py --show-args
```

可以正常加载 launch 描述。

注意：这个 launch 只包含 X3 bringup 和 `octomap_server`，不负责启动 Astra Plus。要让 Octomap 有点云输入，仍需先启动：

```bash
ros2 launch astra_camera astro_pro_plus.launch.xml
```

也可以先直接启动 Octomap：

```bash
ros2 run octomap_server octomap_server_node --ros-args \
  -r /cloud_in:=/camera/depth/points \
  -p resolution:=0.05 \
  -p frame_id:=odom \
  -p colored_map:=false \
  -p sensor_model.max_range:=5.0
```

## 快速排查

查看车2关键 topic：

```bash
ros2 topic info /odom
ros2 topic info /scan
ros2 topic info /camera/depth/image_raw
ros2 topic info /camera/depth/points
ros2 topic info /camera/color/image_raw
```

确认真实数据：

```bash
PYTHONUNBUFFERED=1 timeout 4 ros2 topic echo /scan | head
PYTHONUNBUFFERED=1 timeout 4 ros2 topic echo /camera/depth/image_raw | head
```

查看服务健康：

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8000/health
tail -80 /tmp/robot_agent_robot_002.log
```

Windows 侧确认 MQTT 和 fleet：

```powershell
Test-NetConnection 192.168.137.20 -Port 1883
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/fleet/robots
```

## 阶段 1：在线与心跳验证

每次做多车协同演示前，先在 Windows 项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage1_online.ps1
```

脚本会检查：

- `web_api /health` 为 `ok`
- Windows 后端 `mqtt_connected=true`
- `robot_001`、`robot_002` 都在 `/api/fleet/robots`
- 两台车状态都是 `online`
- 等待数秒后二次采样，确认 `last_seen_at` 持续刷新
- 心跳年龄没有超过阈值

2026-07-13 实测通过：

```text
robot_001 online idle 192.168.137.239 last_seen_age_sec=0.6
robot_002 online idle 192.168.137.89  last_seen_age_sec=1.5
PASS: all expected robots are online and heartbeats are refreshing.
```

如果脚本失败，优先按顺序排查：

1. `docker ps` 是否有 `parking_mqtt`。
2. `Invoke-RestMethod http://127.0.0.1:8000/health` 是否 `mqtt_connected=true`。
3. 车2 `/tmp/robot_agent_robot_002.log` 是否持续打印 `published robot/robot_002/heartbeat`。
4. 两台车是否使用不同 `robot_code`，后端是否使用不同 `MQTT_CLIENT_ID`。

## 阶段 2：单车独立命令验证

阶段 2 目标是证明后端能按 `robot_code` 定向下发命令，目标车 ACK，非目标车状态不被误改。此阶段仍只用 `set_mode`，不让车轮运动。

默认验证小车2：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage2_single_command.ps1 `
  -TargetRobot robot_002 `
  -OtherRobot robot_001
```

反向验证小车1：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage2_single_command.ps1 `
  -TargetRobot robot_001 `
  -OtherRobot robot_002
```

脚本会检查：

- Windows 后端 `/health` 为 `ok` 且 `mqtt_connected=true`
- 目标车和非目标车都 `online`
- POST 到 `/api/fleet/robots/{robot_code}/commands`
- MQTT topic 是 `fleet/command/{robot_code}`
- 命令最终 `status=acked`
- ACK 内的 `robot_code` 等于目标车
- 目标车 mode 变为测试值 `patrol`
- 非目标车 mode 保持不变
- 最后把目标车恢复为 `idle`

2026-07-13 实测通过：

```text
robot_002:
  command_id=87c436e650f64f0896c1727d008f37dc
  detail=mode set to patrol
  After: robot_002 mode=patrol, robot_001 mode=idle
  Restored: robot_002 mode=idle

robot_001:
  command_id=93b703f00026459da33361caa768bbf0
  detail=mode set to patrol
  After: robot_001 mode=patrol, robot_002 mode=idle
  Restored: robot_001 mode=idle
```

最终确认：

```text
total_robots=2
online_robots=2
acked_commands=7
robot_001 mode=idle
robot_002 mode=idle
```

## 阶段 3：双车批量命令验证

阶段 3 目标是证明一次后端 batch 请求可以同时分发到两台车，并且每台车拥有独立 `command_id`、独立 ACK。此阶段仍只用 `set_mode`，不让车轮运动。

运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage3_batch_command.ps1
```

脚本会检查：

- Windows 后端 `/health` 为 `ok` 且 `mqtt_connected=true`
- `robot_001`、`robot_002` 都 `online`
- POST 到 `/api/fleet/commands/batch`
- 返回 2 条 command，分别对应 `robot_001` 和 `robot_002`
- 两条 `command_id` 不相同
- 两条 topic 分别是：
  - `fleet/command/robot_001`
  - `fleet/command/robot_002`
- 两条命令最终都 `status=acked`
- 每条 ACK 内的 `robot_code` 和目标车一致
- 两台车 mode 都变为 `patrol`
- 最后通过 batch 命令把两台车都恢复为 `idle`

2026-07-13 实测通过：

```text
Before:
robot_001 online idle 192.168.137.239
robot_002 online idle 192.168.137.89

Batch patrol:
robot_001 command_id=4955076940c34d14af3b673d24f86923 acked detail="mode set to patrol"
robot_002 command_id=ec984b149f4d40929ad291c0bf5b2474 acked detail="mode set to patrol"

After patrol:
robot_001 online patrol 192.168.137.239
robot_002 online patrol 192.168.137.89

Restored idle:
robot_001 online idle 192.168.137.239
robot_002 online idle 192.168.137.89
```

最终确认：

```text
total_robots=2
online_robots=2
acked_commands=13
failed_commands=0
timeout_commands=0
robot_001 mode=idle
robot_002 mode=idle
```

## 阶段 4：编队状态协同验证

阶段 4 目标是证明后端可以创建一次编队任务，把两台车分配到同一个 `formation_id` 下，并且分别下发独立的 `set_formation` 命令。此阶段仍然只验证多车协同状态链路和 ACK，不直接驱动车轮运动。

运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage4_formation.ps1
```

如果希望测试结束后把两台车的 `mode` 恢复为 `idle`，可以加：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage4_formation.ps1 -RestoreIdle
```

脚本会检查：

- Windows 后端 `/health` 为 `ok` 且 `mqtt_connected=true`
- `robot_001`、`robot_002` 都 `online`
- POST 到 `/api/fleet/formations`
- 返回非空 `formation_id`
- 返回 2 条 `set_formation` command，分别对应 `robot_001` 和 `robot_002`
- 两条 `command_id` 不相同
- 两条 topic 分别是：
  - `fleet/command/robot_001`
  - `fleet/command/robot_002`
- `robot_001` payload 中为 `role=leader`、`slot_index=0`
- `robot_002` payload 中为 `role=follower`、`slot_index=1`
- 两条命令最终都 `status=acked`
- `/api/fleet/formations/{formation_id}` 中 `ready=true`
- 两台车的 `formation_id`、`formation_role`、`formation_slot` 和编队成员表一致

2026-07-13 实测通过：

```text
Formation created: 8bd38efdd05346009850740a5e7562da

robot_code role     slot mode   command_id                       command_status ready
---------- ----     ---- ----   ----------                       -------------- -----
robot_001  leader      0 patrol 4d42a403bca44a1b8745ff42a9dfb7b5 acked           True
robot_002  follower    1 patrol de82a14f6ce44cfd8aee18dee2e1d056 acked           True

PASS: formation is ready and all robots reported expected roles.
```

最终确认：

```text
total_robots=2
online_robots=2
total_formations=3
ready_formations=1
robot_001 formation_role=leader formation_slot=0
robot_002 formation_role=follower formation_slot=1
```

注意：阶段 4 当前的 `set_formation` 只让 `robot_agent` 更新编队状态并 ACK，适合演示“多车任务编排已打通”。如果下一阶段要进入真实跟随或队形运动，需要在 `robot_agent` 内把 formation payload 转成 ROS 控制或导航目标，并增加急停、速度上限、间距保护和人工接管。

## 阶段 5：受控真实运动验证

阶段 5 目标是把多车协同从“只更新状态并 ACK”推进到“车端真实发布 `/cmd_vel`”。最短安全闭环是：先确认 MQTT 和 agent 在线，再确认目标车 `ros_bridge` 可用且 `/cmd_vel` 有底盘订阅者，然后下发一次 safety stop，最后在人工确认场地安全后执行一次短时低速 `corridor_crawl`。

如果 Docker Desktop / Mosquitto 没起来，可以先用临时 Python broker 顶上：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_dev_mqtt_broker_windows.ps1
```

然后用跳过 Docker 的方式启动 Windows fleet 后端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_fleet_backend_windows.ps1 `
  -SkipDocker `
  -MqttHost 127.0.0.1 `
  -MqttClientId parking_backend_windows_stage5 `
  -RosBridgeHttpUrl http://192.168.137.89:8001
```

运动前预检，不会前进，只会下发 stop：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage5_controlled_motion.ps1
```

脚本会检查：

- Windows 后端 `/health` 为 `ok` 且 `mqtt_connected=true`
- 目标车 `robot_001` 为 `online`
- 目标车 `ros_bridge` 为 `ok`
- `ros_bridge` 的 `cmd_vel_topic=/cmd_vel`
- `/cmd_vel` 的 `subscriber_count >= 1`
- 后端向 `/api/fleet/safety/stop` 下发 stop
- 车端 agent ACK，且 `dry_run=false`

2026-07-13 预检实测通过：

```text
TargetRobot: robot_001
TargetRosBridgeUrl: http://192.168.137.239:8001
Motion: linear_x=0.12 m/s, duration=1.5 s, armed=False
Preflight OK: ros_bridge subscriber_count=1
Safety stop ACKed: command_id=207fc6441e38485786a894ded506092e, dry_run=False, detail=stop command sent to ROS bridge
PASS: preflight and safety stop succeeded. Add -ArmMotion to execute the short low-speed movement.
```

确认小车在地面空旷区域或架空测试台后，再执行真实短时低速运动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage5_controlled_motion.ps1 -ArmMotion
```

注意：`corridor_crawl` 的 ACK 只表示 `robot_agent -> ros_bridge` 已接受命令。`ros_bridge` 的 timed `/cmd_vel` 是后台发布，所以测试脚本不能在 ACK 后立刻 stop，否则会提前截断动作。当前脚本会等待 `duration + 0.5s` 后再下发最终 safety stop。

2026-07-13 真实短时运动实测通过，现场观察 `robot_001` 已短距离前进：

```text
TargetRobot: robot_001
TargetRosBridgeUrl: http://192.168.137.239:8001
Motion: linear_x=0.12 m/s, duration=1.5 s, armed=True
Preflight OK: ros_bridge subscriber_count=1
Safety stop ACKed: command_id=10a95eda6eca45a28e666826cd05a89f, dry_run=False, detail=stop command sent to ROS bridge
Motion ACKed: command_id=34353dfccbff4a02b63f389be2acc354, dry_run=False, detail=corridor crawl motion accepted
Holding motion window for 2s before final safety stop...
Final safety stop ACKed: command_id=25d94b3a7c9645e399c6aef888bf3f8a, dry_run=False, detail=stop command sent to ROS bridge
PASS: controlled motion command completed and final stop was ACKed.
```

后置确认：

```text
robot_001 status=online mode=idle
total_robots=2
online_robots=2
total_commands=7
acked_commands=7
failed_commands=0
timeout_commands=0
```

默认运动参数非常保守：

- `linear_x=0.12 m/s`
- `duration=1.5 s`
- 理论位移约 `0.18 m`
- 动作完成后脚本会再次下发 safety stop

如果要改目标车或速度，仍建议保持在低速短时：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_fleet_stage5_controlled_motion.ps1 `
  -TargetRobot robot_001 `
  -TargetRosBridgeUrl http://192.168.137.239:8001 `
  -LinearX 0.12 `
  -DurationSec 1.5 `
  -ArmMotion
```

注意：车2当前 `robot_agent` 仍以 `--dry-run` 启动，适合验证通信但不会驱动车轮。要让车2真实运动，需要先把车2 agent 改为非 dry-run，再重复阶段 5 预检。不要同时让两台车真实运动，先完成单车闭环，再做错峰双车慢行。

## 当前不建议直接复制车1 Docker 的原因

车1当前 `ros_x3_fixed` 使用自定义镜像：

```text
car10th_ros_x3_ai:fixed_20260712_161002
```

车2没有这个镜像，且车2当前没有 `nvidia-container-runtime`。直接拷贝 30GB+ 镜像成本高，而且 GPU/AI 运行不一定能起来。

更快的路线是：

1. 先用车2已有 `yahboomtechnology/ros-foxy:5.0.1` 打通 ROS、App API、多车 MQTT。
2. AI 权重和 YOLO 加速后续单独迁移。
3. 如确实需要和车1完全一致，再先安装 NVIDIA container runtime，再从车1 `docker save | docker load` 迁移镜像。
