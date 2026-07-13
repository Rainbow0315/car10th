# SLAM 建图接入 App 计划

## 目标

不重写 SLAM、不替代老师原来的导航算法。继续使用车上原有 ROS 2 建图/导航 launch，把 ROS 输出的地图和位姿接到我们自己的后端和移动端 App。

当前车端信息：

- 小车 IP：`192.168.137.239`
- SSH/系统密码：`yahboom`
- Docker 主容器：`ros_x3_fixed`
- ROS_DOMAIN_ID：`30`

## 最小闭环

1. 车上启动原有建图：
   `ros2 launch yahboomcar_nav map_gmapping_launch.py`
2. ROS 输出 `/map`，类型为 `nav_msgs/msg/OccupancyGrid`。
3. 后端 `ros_bridge` 订阅 `/map` 和 `/odom`。
4. `web_api` 暴露统一接口：`GET /api/slam/map`。
5. App 地图页请求接口，显示真实栅格地图。
6. App 支持刷新地图、选择目标点、显示小车当前位置。

## 导航目标闭环

第一版不改老师/原厂导航算法，只把 App 选点转成 ROS 目标点：

1. App 地图页点击地图，按 `/map` 的 `origin + resolution` 转成地图坐标。
2. App 请求 `POST /api/slam/goal`，请求体包含 `x`、`y`、`yaw`、`frame_id`。
3. `web_api` 转发给 `ros_bridge`。
4. `ros_bridge` 发布 `geometry_msgs/msg/PoseStamped` 到 `/goal_pose`。
5. 车上原有导航节点继续负责路径规划和运动控制。

已经在车上原 `yahboomcar_nav` 的 RViz 配置里确认目标话题是 `/goal_pose`。如果后续换了导航配置，实际目标话题不是 `/goal_pose`，不改 App，只在启动 `ros_bridge` 前设置：

```bash
export ROS_GOAL_TOPIC=/实际目标话题
```

注意：`map_gmapping_launch.py` 主要用于建图并发布 `/map`。App 能显示地图，只要求建图链路正常；App 下发目标点后要让车真正自动导航，还需要车上原有导航 launch 也处于可用状态，例如 DWA/TEB/RTABMap 导航流程。也就是说：

- 建图显示验收：看 `/map`、`/odom`、`GET /api/slam/map`。
- 导航目标验收：看 `/goal_pose` 是否收到消息，再看导航节点是否规划和发布 `/cmd_vel`。

## 已接入接口

- `GET /api/slam/map`：获取最新 `/map` 栅格地图和 `/odom` 位姿。
- `POST /api/slam/goal`：下发导航目标点。

目标点请求示例：

```json
{
  "x": 1.2,
  "y": 0.6,
  "yaw": 0.0,
  "frame_id": "map"
}
```

## RViz 的角色

RViz 继续作为调试对照工具，不作为最终演示入口。

- RViz 能看到地图，App 看不到：优先查后端桥接或 App 渲染。
- RViz 也看不到地图：优先查 SLAM、雷达、TF。

## 明天上车验证顺序

1. 清理重复容器和重复 launch，只保留一套底盘驱动。
2. 如果容器刚重启，先补原厂脚本依赖的串口链接：
   ```bash
   ln -sf /dev/ttyUSB1 /dev/myserial
   ln -sf /dev/ttyUSB0 /dev/rplidar
   chmod 666 /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2
   ```
3. 启动雷达/底盘/建图：
   ```bash
   export ROBOT_TYPE=x3
   export RPLIDAR_TYPE=a1
   ros2 launch yahboomcar_nav map_gmapping_launch.py
   ```
   这个 launch 会包含底盘、雷达和 gmapping，不需要再单独启动一遍底盘。
4. 启动后端：
   - `ros_bridge`：`python3 -m apps.ros_bridge.main`
   - `web_api`：`uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000`
5. 验证话题：
   - `ros2 topic info /map`
   - `ros2 topic echo /map --once`
   - `ros2 topic echo /odom --once`
6. 验证接口：
   `curl http://127.0.0.1:8000/api/slam/map`
7. 验证目标点转发：
   `curl -X POST http://127.0.0.1:8000/api/slam/goal -H "Content-Type: application/json" -d "{\"x\":0.5,\"y\":0.0,\"yaw\":0.0,\"frame_id\":\"map\"}"`
8. 打开 App 地图页，点击刷新，应显示真实地图；点击地图并下发目标，应能在 ROS 侧看到目标点消息。

目标点 ROS 侧检查：

```bash
ros2 topic echo /goal_pose --once
```

如果只看到 `/goal_pose`，但车不规划/不动，优先检查导航 launch 是否启动，而不是改 App 或改接口。

如果从电脑连车：

```bash
ssh jetson@192.168.137.239
docker exec -it ros_x3_fixed bash
export ROS_DOMAIN_ID=30
source /opt/ros/foxy/setup.bash
source /root/yahboomcar_ros2_ws/software/library_ws/install/setup.bash
source /root/yahboomcar_ros2_ws/yahboomcar_ws/install/setup.bash
```

也可以直接使用项目脚本：

```bash
cd /root/car10th/backend

# 终端 1：启动原厂底盘、雷达、gmapping
./scripts/start_slam_mapping.sh

# 终端 2：启动我们的 ROS 桥接和业务 API
./scripts/start_slam_services.sh

# 检查地图接口
./scripts/slam_smoke_test.sh
```

## 旧镜像命令对应关系

旧镜像中的 `icar_*` 包在当前容器里对应为 `yahboomcar_*`：

- `ros2 run icar_bringup Mcnamu_driver_X3` -> `ros2 run yahboomcar_bringup Mcnamu_driver_X3`
- `ros2 launch sllidar_ros2 sllidar_launch.py` -> 当前仍然是 `ros2 launch sllidar_ros2 sllidar_launch.py`
- `ros2 run icar_laser laser_Avoidance_a1_X3` -> `ros2 run yahboomcar_laser laser_Avoidance_a1_X3`
- `ros2 run icar_laser laser_Tracker_a1_X3` -> `ros2 run yahboomcar_laser laser_Tracker_a1_X3`
- `ros2 run icar_laser laser_Warning_a1_X3` -> `ros2 run yahboomcar_laser laser_Warning_a1_X3`
- `ros2 launch astra_camera astra.launch.xml` -> 当前仍然是 `ros2 launch astra_camera astra.launch.xml`
- `ros2 run icar_astra colorHSV` -> `ros2 run yahboomcar_astra colorHSV`
- `ros2 run icar_astra colorTracker` -> `ros2 run yahboomcar_astra colorTracker`

当前已实测，建图链路真正需要的是：

```bash
export ROBOT_TYPE=x3
export RPLIDAR_TYPE=a1
ros2 launch yahboomcar_nav map_gmapping_launch.py
```

实测结果：

- `/scan`：1 个发布者
- `/odom`：1 个发布者
- `/map`：1 个发布者
- `GET http://192.168.137.239:8000/api/slam/map` 返回 `available=true`，地图尺寸 `384 x 384`，`data_len=147456`

## 先不做的部分

- 不重写 gmapping / cartographer。
- 不做 RViz 级完整交互。
- 不在第一版做复杂路径规划编辑。
- 多车协同先做多 robot_id 展示，不阻塞单车建图闭环。
