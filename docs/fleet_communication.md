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
