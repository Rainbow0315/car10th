"""MQTT Topic 约定（与 Flutter APP 对齐）。"""

# APP → 后端：遥控/任务指令
APP_CONTROL = "app/control/{robot_code}"

# 后端 → APP：小车实时状态
ROBOT_STATUS = "robot/status/{robot_code}"

# 后端 → APP：告警推送
ALARM_NOTIFY = "alarm/notify"

# 后端 → APP：系统广播（可选）
SYSTEM_BROADCAST = "system/broadcast"

# Robot -> backend: fleet uplink messages.
ROBOT_HEARTBEAT = "robot/{robot_code}/heartbeat"
ROBOT_STATUS_UP = "robot/{robot_code}/status"
ROBOT_POSE_UP = "robot/{robot_code}/pose"
ROBOT_EVENT_UP = "robot/{robot_code}/event"
ROBOT_ACK_UP = "robot/{robot_code}/ack"

# Backend -> robot: fleet downlink messages.
FLEET_COMMAND = "fleet/command/{robot_code}"
FLEET_TASK = "fleet/task/{robot_code}"
FLEET_BROADCAST = "fleet/broadcast"


def app_control_topic(robot_code: str) -> str:
    return APP_CONTROL.format(robot_code=robot_code)


def robot_status_topic(robot_code: str) -> str:
    return ROBOT_STATUS.format(robot_code=robot_code)


def robot_heartbeat_topic(robot_code: str) -> str:
    return ROBOT_HEARTBEAT.format(robot_code=robot_code)


def robot_status_up_topic(robot_code: str) -> str:
    return ROBOT_STATUS_UP.format(robot_code=robot_code)


def robot_pose_topic(robot_code: str) -> str:
    return ROBOT_POSE_UP.format(robot_code=robot_code)


def robot_ack_topic(robot_code: str) -> str:
    return ROBOT_ACK_UP.format(robot_code=robot_code)


def fleet_command_topic(robot_code: str) -> str:
    return FLEET_COMMAND.format(robot_code=robot_code)


# 订阅通配：app/control/#
APP_CONTROL_SUBSCRIBE = "app/control/#"

# Subscribe all robot uplink messages: robot/{robot_code}/{message_type}
ROBOT_UPLINK_SUBSCRIBE = "robot/+/+"
ROBOT_UPLINK_SUBSCRIBE_TOPICS = [
    "robot/+/heartbeat",
    "robot/+/status",
    "robot/+/pose",
    "robot/+/event",
    "robot/+/ack",
]
