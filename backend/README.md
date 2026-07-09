# Backend 后端服务

## 目录结构

```
backend/
├── apps/
│   ├── web_api/              # FastAPI REST 网关
│   │   ├── main.py
│   │   ├── dependencies.py   # JWT 鉴权依赖
│   │   ├── routers/          # 路由（auth 等）
│   │   └── services/         # 业务逻辑
│   ├── ros_bridge/
│   └── ai_service/
├── common/
│   ├── models/               # SQLAlchemy ORM 模型（11张表）
│   ├── schemas/              # Pydantic 请求/响应模型
│   ├── config/
│   └── utils/                # JWT、密码哈希等工具
├── db/schema.sql
├── scripts/init_admin.py     # 初始化 admin 密码
└── main.py
```

## 本地启动

```powershell
cd g:\personal\Desktop\car\car10th\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1. 确认 .env 中 MYSQL_PASSWORD 正确
# 2. 建库建表（数据库存在但无表时执行）
python scripts/init_db.py

# 3. 初始化 admin 密码（默认 admin123）
python scripts/init_admin.py

# 4. 启动服务
python main.py
```

访问 http://127.0.0.1:8000/docs

## 鉴权 API

| 方法 | 路径 | 说明 | 是否需要 Token |
|------|------|------|----------------|
| POST | `/api/auth/register` | 注册账号（默认值班员角色） | 否 |
| POST | `/api/auth/login` | 登录，返回 JWT | 否 |
| GET | `/api/auth/me` | 获取当前用户信息 | 是 |
| POST | `/api/auth/change-password` | 修改密码 | 是 |

### 注册示例

```json
POST /api/auth/register
{
  "username": "zhangsan",
  "password": "123456",
  "display_name": "张三",
  "phone": "13800138000",
  "email": "zhangsan@example.com"
}
```

注册成功后直接返回 JWT，可免登录进入系统。新用户默认角色为 **值班员（operator）**。

### 登录示例

```json
POST /api/auth/login
{
  "username": "admin",
  "password": "admin123"
}
```

响应：

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": 1,
    "username": "admin",
    "display_name": "系统管理员",
    "role": { "role_code": "admin", "role_name": "管理员" }
  }
}
```

后续请求在 Header 携带：`Authorization: Bearer <access_token>`

## Day2：MQTT + 小车控制

### 架构

```
Flutter APP  ──MQTT──►  web_api (8000)  ──HTTP──►  ros_bridge (8001)  ──ROS2──►  /cmd_vel
                ▲              │
                └── 状态推送 ──┘   robot/status/{robot_code}
```

- **ros_bridge**：部署在小车/ROS 环境，直接用 `rclpy` 发布 `Twist`（不依赖 rosbridge WebSocket，设计合理）
- **web_api**：业务网关，MQTT 收发 + REST 接口，遥控指令转发给 ros_bridge

### 启动 Mosquitto

```powershell
cd g:\personal\Desktop\car\car10th
docker compose up -d mosquitto
```

### 启动顺序

```powershell
# 终端1：ROS 环境中小车侧 ros_bridge（有 ROS2 时）
cd backend
python -m apps.ros_bridge.main

# 终端2：web_api
python main.py
```

### MQTT Topic

| Topic | 方向 | 说明 |
|-------|------|------|
| `app/control/{robot_code}` | APP → 后端 | 控制指令 |
| `robot/status/{robot_code}` | 后端 → APP | 实时状态（2s 心跳推送） |
| `alarm/notify` | 后端 → APP | 告警推送（Day3 使用） |

### MQTT 控制消息格式

```json
{
  "command": "cmd_vel",
  "payload": {
    "linear_x": 0.2,
    "angular_z": 0.0,
    "duration": 0.5
  }
}
```

支持指令：`cmd_vel` | `stop` | `patrol_start` | `patrol_stop` | `mode_follow`

### REST 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/mqtt/health` | MQTT 连接状态 |
| GET | `/api/robot/status` | 单车状态（需 Token） |
| GET | `/api/robot/status/all` | 全部小车状态 |
| POST | `/api/robot/control` | 下发控制（写 operation_log） |

### 本地 MQTT 测试

```powershell
python scripts/test_mqtt.py subscribe-status
python scripts/test_mqtt.py publish-control
```
