# 分布式通信与多车协同开发记录

## 第 1 步：单车上线与心跳

目标效果：

- 启动 MQTT broker 和后端后，后端订阅 `robot/+/+`。
- 启动一台小车上的 `robot_agent` 后，agent 定时发布心跳和状态。
- 后端通过 `/api/fleet/robots` 能看到这台车 `online`。
- 停止 agent 后，超过 `FLEET_ROBOT_OFFLINE_SEC` 后该车显示为 `offline`。

### Topic 约定

车端上报：

```text
robot/{robot_code}/heartbeat
robot/{robot_code}/status
robot/{robot_code}/pose
robot/{robot_code}/event
robot/{robot_code}/ack
```

后端下发：

```text
fleet/command/{robot_code}
fleet/task/{robot_code}
fleet/broadcast
```

### 本地 dry-run 测试

终端 1：启动 MQTT 和后端依赖。

```powershell
docker compose up -d mysql mosquitto
```

如果修改过 Mosquitto ACL，需要重建 broker：

```powershell
docker compose up -d --force-recreate mosquitto
```

终端 2：启动后端。

```powershell
cd backend
python -m pip install -r requirements.txt
python main.py
```

终端 3：启动一个模拟车端 agent。

```powershell
cd backend
python -m apps.robot_agent.main --robot-code robot_001 --dry-run
```

终端 4：查看车队状态。

```powershell
curl http://127.0.0.1:8000/api/fleet/robots
```

预期返回中包含：

```json
{
  "robot_code": "robot_001",
  "status": "online",
  "mode": "idle"
}
```

停止终端 3 的 agent 后，等待约 10 秒再次查询，预期 `robot_001` 变为 `offline`。

### 上车测试

把电脑和小车接入同一个网络后，在小车终端运行：

```bash
cd /path/to/car10th/backend
python -m apps.robot_agent.main --robot-code robot_001
```

如果后端不在小车本机，确认小车的 `backend/.env` 或环境变量中：

```env
MQTT_BROKER_HOST=<后端电脑或服务器IP>
MQTT_BROKER_PORT=1883
MQTT_ROBOT_USERNAME=parking_robot
MQTT_ROBOT_PASSWORD=parking_robot_dev
```

第一步只验证通信在线，不要求小车运动。小车能在后端显示在线，就说明分布式通信底座已经跑通。

## 第 2 步：后端下发命令与车端 ACK

目标效果：

- 后端通过 HTTP 接口向指定 `robot_code` 发布 `fleet/command/{robot_code}`。
- 小车 `robot_agent` 收到命令后发布 `robot/{robot_code}/ack`。
- 后端收到 ACK 后，可以通过 `command_id` 查询该命令是否已送达。

本地 dry-run 测试时，保持后端和 agent 都在运行，然后执行：

```powershell
$body = '{"command":"set_mode","payload":{"mode":"patrol"}}'
curl.exe -s -X POST http://127.0.0.1:8000/api/fleet/robots/robot_001/commands -H "Content-Type: application/json" -d $body
```

返回中会包含 `command_id`，例如：

```json
{
  "command_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "robot_code": "robot_001",
  "command": "set_mode",
  "status": "published"
}
```

等待 1 秒后查询 ACK：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/commands/<command_id>
```

预期 `status` 变为 `acked`，`ack.detail` 包含 agent 的处理结果。dry-run 模式只模拟模式变化，不会让真实小车运动；上车后可以先发 `stop` 或 `set_mode` 验证通信，再逐步接入 ROS2 控制。

## 第 3 步：多车批量协同指令

目标效果：

- 同时启动两台 agent，例如 `robot_001` 和 `robot_002`。
- 后端通过一次 HTTP 请求向多台车分别下发同一个指令。
- 每台车都有独立 `command_id`，每台车都需要独立 ACK。
- 查询 `/api/fleet/robots` 可以看到两台车都进入预期模式。

终端 3：启动第一台模拟车。

```powershell
cd backend
python -m apps.robot_agent.main --robot-code robot_001 --dry-run
```

终端 4：启动第二台模拟车。

```powershell
cd backend
python -m apps.robot_agent.main --robot-code robot_002 --dry-run
```

终端 5：批量下发协同模式。

```powershell
$body = @{
  robot_codes = @("robot_001", "robot_002")
  command = "set_mode"
  payload = @{ mode = "patrol" }
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/commands/batch" -ContentType "application/json" -Body $body
```

预期返回中包含两条 `commands`，分别对应 `robot_001` 和 `robot_002`。等待 1 秒后分别用返回的 `command_id` 查询：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/commands/<command_id>
```

预期两条命令都变为 `acked`。再查询：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/robots
```

预期两台车都为 `online`，且 `mode` 都为 `patrol`。这一步仍然不控制真实电机，只验证多车通信和协同指令分发闭环。

## 第 4 步：编队任务与角色分配

目标效果：

- 后端生成一个 `formation_id`。
- 第一台车被分配为 `leader`，后续车辆被分配为 `follower`。
- 每台车收到 `set_formation` 后 ACK，并在状态上报中携带 `formation_id`、`formation_role` 和 `formation_slot`。

保持两台 agent 运行后执行：

```powershell
$body = @{
  robot_codes = @("robot_001", "robot_002")
  formation_type = "line"
  mode = "patrol"
  spacing_m = 1.2
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/formations" -ContentType "application/json" -Body $body
```

预期返回一个 `formation_id` 和两条命令。等待 1 秒后查询：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/robots
```

预期：

```json
[
  {
    "robot_code": "robot_001",
    "mode": "patrol",
    "formation_role": "leader",
    "formation_slot": 0
  },
  {
    "robot_code": "robot_002",
    "mode": "patrol",
    "formation_role": "follower",
    "formation_slot": 1
  }
]
```

这一步仍是通信层和协同状态层，不直接让车运动。真正接入运动控制时，可以让 `leader` 执行导航/巡检目标，`follower` 根据 `offset_x/offset_y` 做跟随。

## 第 5 步：编队就绪状态聚合

目标效果：

- 创建编队后，后端保存 `formation_id` 和每台车的角色、槽位、命令 ID。
- 查询编队详情时，可以看到每台车是否在线、是否 ACK、角色是否匹配。
- 只有所有成员都在线、命令都 ACK、上报角色/槽位都匹配时，编队 `ready` 才为 `true`。

创建编队后，用返回的 `formation_id` 查询：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/formations/<formation_id>
```

也可以列出当前后端内存中的所有编队：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/formations
```

预期核心字段：

```json
{
  "ready": true,
  "total_robots": 2,
  "online_robots": 2,
  "acked_commands": 2,
  "members": [
    {
      "robot_code": "robot_001",
      "role": "leader",
      "ready": true
    },
    {
      "robot_code": "robot_002",
      "role": "follower",
      "ready": true
    }
  ]
}
```

停止任意一台 agent 并等待约 10 秒后，再查同一个 `formation_id`，预期 `ready` 变为 `false`，对应成员的 `robot.status` 变为 `offline`。

## 第 6 步：车端部署版本可观测

目标效果：

- 小车 agent 状态上报携带 `agent_hostname`、`agent_ip` 和 `agent_version`。
- `agent_version` 来自部署目录中的 `DEPLOYED_COMMIT`。
- 后端 `/api/fleet/robots` 能直接看到每台车当前运行的是哪个部署提交。

查询：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/robots
```

预期每台车状态中包含：

```json
{
  "robot_code": "robot_001",
  "agent_hostname": "jetson-desktop",
  "agent_ip": "192.168.247.227",
  "agent_version": "13b9ab6"
}
```

这样可以快速判断“GitHub/部署机上的代码是否真的已经跑到对应小车上”。

## 第 7 步：命令 ACK 超时判定

目标效果：

- 后端下发命令后，如果车端没有在 `FLEET_COMMAND_ACK_TIMEOUT_SEC` 秒内回 ACK，命令状态从 `published` 变为 `timeout`。
- 多车编队中任意成员命令超时，编队 `ready` 保持 `false`。
- 默认超时时间为 5 秒，可在 `backend/.env` 中调整：

```env
FLEET_COMMAND_ACK_TIMEOUT_SEC=5
```

测试方法：对一个不存在或未启动 agent 的车辆下发命令：

```powershell
$body = @{ command = "set_mode"; payload = @{ mode = "patrol" } } | ConvertTo-Json -Compress -Depth 5
$result = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/robots/robot_missing/commands" -ContentType "application/json" -Body $body
Start-Sleep -Seconds 6
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands/$($result.command_id)"
```

预期：

```json
{
  "robot_code": "robot_missing",
  "status": "timeout",
  "error": "ACK timeout after 5s"
}
```

## 第 8 步：车队总览接口

目标效果：

- 一次查询看到车辆在线/离线数量。
- 一次查询看到命令 ACK、失败、超时数量。
- 一次查询看到编队总数和 ready 编队数量。

查询：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/summary
```

预期核心字段：

```json
{
  "total_robots": 2,
  "online_robots": 1,
  "offline_robots": 1,
  "total_commands": 3,
  "acked_commands": 2,
  "timeout_commands": 1,
  "total_formations": 1,
  "ready_formations": 0
}
```

这个接口适合做调试面板或移动端首页的车队健康概览。

## 第 9 步：命令列表与筛选接口

目标效果：

- 下发单车或多车命令后，不需要手动记录每个 `command_id`。
- 可以按车辆筛选最新命令，快速判断某台车是否收到并 ACK。
- 可以按状态筛选 `published`、`acked`、`failed`、`timeout` 命令，定位协同任务卡在哪一步。

查询最新命令：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?limit=20"
```

只看某台车：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?robot_code=robot_001&limit=20"
```

只看已 ACK 的命令：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?status=acked&limit=20"
```

预期核心字段：

```json
{
  "total": 1,
  "limit": 20,
  "commands": [
    {
      "robot_code": "robot_001",
      "command": "set_mode",
      "status": "acked"
    }
  ]
}
```

这个接口适合真机调试时持续观察“命令是否发出、是否被小车确认、是否超时”。

## 第 10 步：协同任务前置检查接口

目标效果：

- 编队或批量命令下发前，先检查目标车辆是否在线。
- 快速识别某台车离线、未上报心跳或处于 error 状态。
- 避免协同任务发出去后才发现某个成员没有响应。

检查一台在线车和一台不存在的车：

```powershell
$body = @{ robot_codes = @("robot_001", "robot_missing") } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/readiness" -ContentType "application/json" -Body $body
```

预期核心字段：

```json
{
  "all_ready": false,
  "total_robots": 2,
  "ready_robots": 1,
  "members": [
    {
      "robot_code": "robot_001",
      "ready_to_command": true
    },
    {
      "robot_code": "robot_missing",
      "ready_to_command": false,
      "reason": "robot is offline or has not reported heartbeat"
    }
  ]
}
```

只检查当前真机：

```powershell
$body = @{ robot_codes = @("robot_001") } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/readiness" -ContentType "application/json" -Body $body
```

如果小车在线，预期 `all_ready=true`、`ready_robots=1`。

## 第 11 步：批量命令与编队的前置检查保护

目标效果：

- 批量命令和编队创建默认保持兼容，仍按原方式下发。
- 如果请求中设置 `require_all_ready=true`，后端会先做 readiness 检查。
- 只要有目标车离线或 error，后端返回 `409 Conflict`，不会下发任何命令。

安全拒绝测试：包含一台不存在的车。

```powershell
$body = @{
  robot_codes = @("robot_001", "robot_missing")
  command = "set_mode"
  payload = @{ mode = "idle" }
  require_all_ready = $true
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/commands/batch" -ContentType "application/json" -Body $body
```

预期返回 `409 Conflict`，核心内容包含：

```json
{
  "message": "not all robots are ready for fleet command",
  "readiness": {
    "all_ready": false,
    "ready_robots": 1
  }
}
```

安全通过测试：只包含当前在线真机。

```powershell
$body = @{
  robot_codes = @("robot_001")
  command = "set_mode"
  payload = @{ mode = "idle" }
  require_all_ready = $true
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/commands/batch" -ContentType "application/json" -Body $body
```

如果 `robot_001` 在线，预期命令可以下发并 ACK。随后可用命令列表确认：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?robot_code=robot_001&status=acked&limit=5"
```

编队创建接口 `/api/fleet/formations` 同样支持 `require_all_ready=true`。

## 第 12 步：地下空间抛锚救援调度

场景故事：

大型工业园区地下空间里，某台车在巡检或运输过程中抛锚、失联或上报 error。调度后端需要把“救援/协助”任务发给另一台在线车辆，让它去寻找或接近故障车的位置。

目标效果：

- 后端生成一个 `incident_id`，代表一次地下空间异常事件。
- 指定或自动选择一台在线车辆作为 `responder_robot`。
- 后端向救援车下发 `assist_robot` 命令，并在命令列表里持续观察 ACK。
- 当前阶段只验证通信和任务闭环，不直接控制车辆移动。

单真机安全测试：把 `robot_missing` 当成抛锚车，让 `robot_001` 接救援任务。

```powershell
$body = @{
  disabled_robot_code = "robot_missing"
  responder_robot_code = "robot_001"
  incident_type = "breakdown"
  note = "地下空间B2区疑似抛锚，请前往协助"
  require_responder_ready = $true
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/rescue" -ContentType "application/json" -Body $body
```

预期核心字段：

```json
{
  "disabled_robot_code": "robot_missing",
  "responder_robot_code": "robot_001",
  "incident_type": "breakdown",
  "command": {
    "command": "assist_robot",
    "status": "published"
  }
}
```

随后查询 ACK：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?robot_code=robot_001&status=acked&limit=5"
```

如果 `robot_001` 在线，预期能看到 `assist_robot` 命令已 ACK。后续接入真实定位/导航后，车端可以把 `target_pose` 转成实际导航目标。

## 第 13 步：救援车低速接近动作

场景故事：

地下空间里确认某台车抛锚后，救援车不应该一上来就高速移动，而是先执行一个短时、低速、可停止的接近动作。这个动作由后端通过 MQTT 下发给指定救援车，真正的 `/cmd_vel` 发布发生在救援车本机的 `robot_agent -> ros_bridge -> ROS2` 链路上。

目标效果：

- 后端向救援车下发 `rescue_approach` 命令。
- 车端 agent 进入 `rescue` 模式。
- 车端通过本地 `ros_bridge` 发布低速 `/cmd_vel`。
- 如果 `ros_bridge` 或底盘订阅者未就绪，命令 ACK 会变成 `failed`，便于定位真实运动链路问题。

安全参数限制：

- `linear_x` 范围：`0.0 ~ 0.12 m/s`
- `angular_z` 范围：`-0.4 ~ 0.4 rad/s`
- `duration` 范围：`0.1 ~ 2.0 s`

先确认车上运动链路：

```bash
curl http://127.0.0.1:8001/health
ros2 topic info /cmd_vel
```

从后端下发低速接近任务：

```powershell
$body = @{
  responder_robot_code = "robot_001"
  disabled_robot_code = "robot_missing"
  incident_id = "demo_breakdown_001"
  linear_x = 0.08
  angular_z = 0.0
  duration = 0.8
  require_responder_ready = $true
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/rescue/approach" -ContentType "application/json" -Body $body
```

观察命令结果：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?robot_code=robot_001&limit=5"
```

如果车端 `ros_bridge` 和底盘都就绪，预期 `rescue_approach` 最终 `status=acked`，且小车执行一次短时低速前进。如果未就绪，预期 `status=failed`，`error/detail` 会说明是 `ros_bridge` 不可达或 `/cmd_vel` 没有订阅者。

## 第 14 步：地下空间区域管制急停

场景故事：

工业园区地下空间通道狭窄、遮挡多。一旦某台车抛锚、通信异常或通道被占用，调度端需要先让相关车辆停住，再派救援车低速接近，避免多车继续进入事故区域。

目标效果：

- 不传 `robot_codes` 时，后端自动对当前在线车辆下发 `emergency_stop`。
- 传入 `robot_codes` 时，只管制指定车辆。
- 车端 dev 版本收到 `emergency_stop` 后，会调用本车 `ros_bridge /api/teleop/stop`。
- 如果车端 `ros_bridge` 未启动，ACK 会标记失败并带上原因，方便定位运动链路。

对所有在线车辆下发区域管制急停：

```powershell
$body = @{
  incident_id = "demo_breakdown_001"
  reason = "地下空间B2区通道管制，所有在线车辆停止"
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/safety/stop" -ContentType "application/json" -Body $body
```

只停止指定车辆：

```powershell
$body = @{
  robot_codes = @("robot_001")
  incident_id = "demo_breakdown_001"
  reason = "救援车测试前安全停车"
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/safety/stop" -ContentType "application/json" -Body $body
```

观察命令结果：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?robot_code=robot_001&limit=5"
```

这一步是后续真机运动测试的安全兜底：先验证 stop 可用，再验证 `rescue_approach` 低速接近。

## 第 15 步：救援车原地搜索抛锚车

场景故事：

地下空间 GPS 不稳定、遮挡多，救援车到达疑似区域后，需要低速原地旋转，配合摄像头、雷达或后续视觉识别寻找抛锚车、反光标识或人工标记。这一步是从“前往事故区域”过渡到“现场搜索确认”的动作。

目标效果：

- 后端向救援车下发 `rescue_search` 命令。
- 车端 dev 版本进入 `rescue` 模式。
- 车端通过本地 `ros_bridge` 发布原地旋转 `/cmd_vel`。
- 动作被限制为低速、短时，便于真机调试。

安全参数限制：

- `linear_x` 固定为 `0.0`
- `angular_z` 范围：`0.1 ~ 0.4 rad/s`
- `duration` 范围：`0.5 ~ 3.0 s`

下发原地搜索：

```powershell
$body = @{
  responder_robot_code = "robot_001"
  disabled_robot_code = "robot_missing"
  incident_id = "demo_breakdown_001"
  angular_z = 0.25
  duration = 1.5
  require_responder_ready = $true
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/rescue/search" -ContentType "application/json" -Body $body
```

观察命令结果：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?robot_code=robot_001&limit=5"
```

如果车端 `ros_bridge` 和底盘都就绪，预期 `rescue_search` 最终 `status=acked`，小车短时低速原地旋转；如果未就绪，预期 `status=failed` 并带运动链路错误原因。

## 第 16 步：地下狭窄通道编队慢行

场景故事：

大型工业园区地下空间常见单车道、坡道、设备间窄通道。事故解除或救援车通过后，多车不能同时抢占通道，需要由调度端按队列下发低速慢行动作，形成“单列通过”的协同故事。

目标效果：

- 后端向一组车辆下发 `corridor_crawl` 命令。
- 每台车 payload 包含 `slot_index` 和 `spacing_m`，表示通行顺序和队间距。
- 车端 dev 版本进入 `busy` 模式，并通过本地 `ros_bridge` 发布低速直行 `/cmd_vel`。
- 动作被限制为低速、短时，便于真机测试。

安全参数限制：

- `linear_x` 范围：`0.0 ~ 0.12 m/s`
- `angular_z` 固定为 `0.0`
- `duration` 范围：`0.2 ~ 3.0 s`

单车安全测试：

```powershell
$body = @{
  robot_codes = @("robot_001")
  corridor_id = "B2-narrow-corridor-A"
  linear_x = 0.06
  duration = 1.0
  spacing_m = 1.0
  require_all_ready = $true
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/corridor/crawl" -ContentType "application/json" -Body $body
```

多车演示时，把 `robot_codes` 扩展为：

```powershell
robot_codes = @("robot_001", "robot_002", "robot_003")
```

观察命令结果：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?limit=10"
```

如果车端 `ros_bridge` 和底盘都就绪，预期 `corridor_crawl` 最终 `status=acked`，车辆短时低速直行；如果未就绪，预期 `status=failed` 并带运动链路错误原因。

## 第 17 步：地下狭窄通道会车让行

场景故事：

地下空间经常出现单车道会车：救援车、载货车或优先巡检车需要通过时，普通车辆不能抢行，而是短时低速后退，让出通道。这一步和 `corridor_crawl` 配合，可以讲成“会车管制 -> 让行 -> 单列慢行通过”。

目标效果：

- 后端向让行车辆下发 `corridor_yield` 命令。
- payload 记录 `priority_robot_code`、`corridor_id` 和让行原因。
- 车端 dev 版本进入 `busy` 模式，并通过本地 `ros_bridge` 发布低速倒退 `/cmd_vel`。
- 动作被限制为短时低速，方便真机安全验证。

安全参数限制：

- `linear_x` 范围：`-0.08 ~ 0.0 m/s`
- `angular_z` 固定为 `0.0`
- `duration` 范围：`0.2 ~ 2.0 s`

单车安全测试：

```powershell
$body = @{
  yielding_robot_code = "robot_001"
  priority_robot_code = "rescue_robot_001"
  corridor_id = "B2-narrow-corridor-A"
  linear_x = -0.05
  duration = 0.8
  reason = "救援车优先通过，当前车短时后退让行"
  require_yielding_ready = $true
} | ConvertTo-Json -Compress -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/fleet/corridor/yield" -ContentType "application/json" -Body $body
```

观察命令结果：

```powershell
curl.exe -s "http://127.0.0.1:8000/api/fleet/commands?robot_code=robot_001&limit=5"
```

如果车端 `ros_bridge` 和底盘都就绪，预期 `corridor_yield` 最终 `status=acked`，车辆短时低速后退；如果未就绪，预期 `status=failed` 并带运动链路错误原因。
