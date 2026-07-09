"""MQTT Topic 约定（与 Flutter APP 对齐）。"""

# APP → 后端：遥控/任务指令
APP_CONTROL = "app/control/{robot_code}"

# 后端 → APP：小车实时状态
ROBOT_STATUS = "robot/status/{robot_code}"

# 后端 → APP：告警推送
ALARM_NOTIFY = "alarm/notify"

# 后端 → APP：系统广播（可选）
SYSTEM_BROADCAST = "system/broadcast"


def app_control_topic(robot_code: str) -> str:
    return APP_CONTROL.format(robot_code=robot_code)


def robot_status_topic(robot_code: str) -> str:
    return ROBOT_STATUS.format(robot_code=robot_code)


# 订阅通配：app/control/#
APP_CONTROL_SUBSCRIBE = "app/control/#"
