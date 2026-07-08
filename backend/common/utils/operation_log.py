"""业务操作日志工具：记录任务下发、告警处理、遥控等业务行为。"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from common.models import OperationLog


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def write_operation_log(
    db: Session,
    *,
    user_id: int,
    action: str,
    description: str,
) -> OperationLog:
    """写入一条业务操作日志。

    action 示例:
        patrol_start / patrol_stop / task_create / task_dispatch
        alarm_handle / robot_control / zone_update
    """
    log = OperationLog(
        user_id=user_id,
        action=action,
        timestamp=utcnow_naive(),
        description=description,
    )
    db.add(log)
    return log
