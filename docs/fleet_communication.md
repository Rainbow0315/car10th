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
