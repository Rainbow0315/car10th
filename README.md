# car10th 园区地下通道智能巡检机器人

基于 Jetson Orin Nano + ROS 2 的地下停车场/地下通道巡检小车项目，当前仓库包含后端服务、ROS 控车桥接、TCP 控车桥接、移动端 Flutter 应用脚手架，以及 MySQL/MQTT 的本地联调环境。

## 项目定位

这个仓库更像一个“系统集成仓库”，而不是单一算法仓库。它把下面几部分放在了一起：

- `backend`：FastAPI 后端，负责认证、机器人状态、REST 网关、MQTT 收发
- `backend/apps/ros_bridge`：将 HTTP 遥控请求转换为 ROS 2 `/cmd_vel`
- `backend/apps/tcp_car_bridge`：将 TCP 小车协议转换为 ROS 2 `/cmd_vel`
- `mobile_app`：Flutter 移动端界面与控车演示端
- `docs`：联调说明、MQTT 配置说明

## 当前已实现内容

- 用户认证：注册、登录、查看当前用户、修改密码
- 数据库初始化：提供完整 `schema.sql` 和初始化脚本
- MQTT 联调：支持控制消息订阅、机器人状态心跳推送、告警推送 topic
- REST 遥控链路：`web_api -> ros_bridge -> /cmd_vel`
- TCP 遥控链路：`Flutter App -> tcp_car_bridge -> /cmd_vel`
- Flutter 前端骨架：登录、总览、地图、告警、设置等页面
- 本地 Docker 环境：MySQL + Mosquitto + Backend 一键拉起

## 当前未完全落地的部分

- `backend/apps/ai_service` 目前还是占位入口
- 后端数据库 schema 设计得比较完整，但已实际开放的 API 仍以认证、状态、遥控为主
- Flutter 端很多业务页面仍使用 Mock 数据，当前真正接入的是 TCP 控车链路

## 技术栈

- 车端：Jetson Orin Nano、ROS 2
- 后端：FastAPI、SQLAlchemy、MySQL、Pydantic
- 消息通道：MQTT（Mosquitto）
- 移动端：Flutter、Provider、SharedPreferences
- 容器编排：Docker Compose

## 仓库结构

```text
car10th/
├─ backend/                 # 后端与桥接服务
│  ├─ apps/
│  │  ├─ web_api/           # FastAPI 主服务
│  │  ├─ ros_bridge/        # HTTP -> ROS2 /cmd_vel
│  │  ├─ tcp_car_bridge/    # TCP 协议 -> ROS2 /cmd_vel
│  │  └─ ai_service/        # AI 服务占位
│  ├─ common/               # 配置、模型、Schema、MQTT、工具
│  ├─ db/                   # 数据库 schema 与迁移脚本
│  ├─ scripts/              # 初始化和测试脚本
│  └─ docker/               # 后端镜像与 Mosquitto 配置
├─ mobile_app/              # Flutter 移动端
├─ docs/                    # 联调与配置文档
├─ test_resource/           # 测试资源
└─ docker-compose.yml       # 本地联调环境
```

## 系统架构

当前仓库里实际存在两条控制链路：

### 1. 后端遥控链路

```text
APP / Client
   -> FastAPI web_api (:8000)
   -> ros_bridge (:8001)
   -> ROS 2 /cmd_vel
   -> 机器人底盘
```

这个链路适合做统一业务接入，便于后续接权限、日志、任务、告警和状态管理。

### 2. 直接 TCP 控车链路

```text
Flutter App
   -> TCP Socket (:6000)
   -> tcp_car_bridge
   -> ROS 2 /cmd_vel
   -> 机器人底盘
```

这个链路更轻，适合先打通移动端直接控车。

### 3. MQTT 状态/控制链路

```text
App publish:    app/control/{robot_code}
Backend sub:    app/control/{robot_code}
Backend publish: robot/status/{robot_code}
App subscribe:   robot/status/{robot_code}
```

其中后端会周期性推送机器人状态，并可额外推送 `alarm/notify`。

## 快速开始

### 1. 环境准备

- Python 3.10 及以上
- Docker / Docker Compose
- Flutter 3.x（如果要运行移动端）
- MySQL 8、Mosquitto 也可以交给 `docker compose` 启动
- ROS 2 环境

说明：仓库简介写的是 ROS 2 Humble，但现有联调文档中也出现了 Foxy 示例，实际以车端安装环境为准。

### 2. 准备后端配置

后端通过 `backend/.env` 读取配置。至少需要确认这些变量：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=parking_inspection_robot

JWT_SECRET_KEY=change-me

MQTT_BROKER_HOST=127.0.0.1
MQTT_BROKER_PORT=1883
MQTT_USERNAME=parking_backend
MQTT_PASSWORD=parking_backend_dev
MQTT_APP_USERNAME=parking_app
MQTT_APP_PASSWORD=parking_app_dev

ROS_BRIDGE_HTTP_URL=http://127.0.0.1:8001
```

如果使用 `docker compose` 启动后端容器，`MQTT_BROKER_HOST` 会被覆盖为 `mosquitto`。

### 3. 启动基础服务

在仓库根目录执行：

```powershell
docker compose up -d mysql mosquitto
```

如果你希望连后端也一起拉起，可以直接执行：

```powershell
docker compose up -d
```

### 4. 初始化数据库

```powershell
cd backend
python -m pip install -r requirements.txt
python scripts/init_db.py
python scripts/init_admin.py
```

默认会把 `admin` 账号密码设置为 `admin123`，联调完成后建议立即修改。

### 5. 启动后端 API

```powershell
cd backend
python main.py
```

启动后可访问：

- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

## ROS 控车联调

### 方案 A：启动 ros_bridge

如果你走的是“后端遥控链路”，需要在 ROS 2 环境中启动：

```powershell
cd backend
python -m apps.ros_bridge.main
```

默认监听 `8001`，可通过下面接口验证：

- `GET /health`
- `POST /api/teleop/cmd-vel`
- `POST /api/teleop/stop`

后端 `web_api` 会转发到这个服务。

### 方案 B：启动 tcp_car_bridge

如果你走的是“Flutter 直接 TCP 控车链路”，需要启动：

```powershell
cd backend
python -m apps.tcp_car_bridge.main
```

默认监听 `0.0.0.0:6000`，移动端会通过 TCP 发送协议帧给它，再由它转换成 ROS 2 `Twist` 指令。

## Flutter 移动端

```powershell
cd mobile_app
flutter pub get
flutter run
```

当前移动端特点：

- 已有登录、总览、地图、告警、设置等页面
- 数据层保留了较完整的业务接口定义
- 多数业务页仍是 Mock 数据
- 当前实际使用 `AppSettings` 中保存的 `tcpHost` / `tcpPort` 直接控车

默认 TCP 配置可在设置页修改，本地会持久化保存。

## 后端核心接口

### 认证接口

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/change-password`

### 机器人与 MQTT

- `GET /api/mqtt/health`
- `GET /api/robot/status`
- `GET /api/robot/status/all`
- `POST /api/robot/control`

`/api/robot/control` 当前支持的命令：

- `cmd_vel`
- `stop`
- `patrol_start`
- `patrol_stop`
- `mode_follow`

其中 `cmd_vel` 和 `stop` 会真正转发到 `ros_bridge`；其余命令目前主要更新状态缓存，便于后续扩展任务逻辑。

## 数据库说明

`backend/db/schema.sql` 已包含较完整的业务表设计，主要覆盖：

- 用户与角色
- 操作日志
- 摄像头与事件日志
- 预警区域
- 告警记录
- 反馈
- 视频分析任务
- AI 日报

这说明项目的数据层规划已经比较完整，但 API 实现还在逐步补齐。

## 相关文档

- [MQTT 配置说明](./docs/mqtt_setup.md)
- [GitHub 分支与 CI 配置说明](./docs/github_cicd_setup.md)
- [分布式通信与多车协同开发记录](./docs/fleet_communication.md)
- [LLM 手机任务助手接入说明](./docs/llm_mobile_task_assistant.md)
- [小车端长期稳定部署方案](./docs/robot_agent_cicd.md)
- [小车端自动 CD 配置手册](./docs/robot_agent_cd_runbook.md)
- [后端控车联调说明](./docs/teleop_backend.md)
- [后端模块说明](./backend/README.md)
- [移动端说明](./mobile_app/README.md)

## 开发建议

- 优先先打通 `ros_bridge` 或 `tcp_car_bridge` 中的一条真实控车链路
- 再把 Flutter 端从 Mock Repository 逐步切到真实 API / MQTT
- 部署到真实网络前，务必修改默认 JWT 密钥与 MQTT 默认密码
