import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.config.database import Base


# ---------- 枚举定义 ----------


class PersonType(str, enum.Enum):
    smoking = "smoking"
    loitering = "loitering"
    intruder = "intruder"
    other = "other"


class PersonStatus(str, enum.Enum):
    active = "active"
    resolved = "resolved"
    ignored = "ignored"


class CameraType(str, enum.Enum):
    rgb = "rgb"
    depth = "depth"
    infrared = "infrared"


class CameraStatus(str, enum.Enum):
    online = "online"
    offline = "offline"
    error = "error"


class EventSource(str, enum.Enum):
    robot = "robot"
    backend = "backend"
    app = "app"
    system = "system"


class EventLevel(str, enum.Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class ZoneType(str, enum.Enum):
    forbidden = "forbidden"
    warning = "warning"
    patrol = "patrol"


class RiskLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class AlarmType(str, enum.Enum):
    foreign_object = "foreign_object"
    crack = "crack"
    pothole = "pothole"
    water = "water"
    smoking = "smoking"
    loitering = "loitering"
    other = "other"


class AlarmStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    closed = "closed"


class FeedbackType(str, enum.Enum):
    alarm_handle = "alarm_handle"
    false_alarm = "false_alarm"
    system = "system"
    suggestion = "suggestion"


class FeedbackStatus(str, enum.Enum):
    pending = "pending"
    reviewed = "reviewed"
    archived = "archived"


class TaskStatus(str, enum.Enum):
    draft = "draft"
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TriggerType(str, enum.Enum):
    manual = "manual"
    scheduled = "scheduled"
    app = "app"


class ReportType(str, enum.Enum):
    daily = "daily"
    night = "night"
    weekly = "weekly"
    custom = "custom"


class ReportGeneratedBy(str, enum.Enum):
    system = "system"
    user = "user"


class ReportStatus(str, enum.Enum):
    generating = "generating"
    completed = "completed"
    failed = "failed"


# ---------- 表 4-1-2 角色表 ----------


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    users: Mapped[list["User"]] = relationship(back_populates="role")


# ---------- 表 4-1-1 用户信息表 ----------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    role: Mapped["Role"] = relationship(back_populates="users")
    operation_logs: Mapped[list["OperationLog"]] = relationship(back_populates="user")
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="user")
    created_zones: Mapped[list["WarningZone"]] = relationship(back_populates="creator")
    created_tasks: Mapped[list["VideoAnalysisTask"]] = relationship(back_populates="creator")
    ai_reports: Mapped[list["AiDailyReport"]] = relationship(back_populates="user")
    handled_alarms: Mapped[list["AlarmLog"]] = relationship(back_populates="handler")


# ---------- 表 4-1-3 操作日志表 ----------


class OperationLog(Base):
    __tablename__ = "operation_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)

    user: Mapped[Optional["User"]] = relationship(back_populates="operation_logs")


# ---------- 表 4-1-5 摄像头信息表 ----------


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    camera_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    camera_name: Mapped[str] = mapped_column(String(128), nullable=False)
    robot_code: Mapped[str] = mapped_column(String(32), nullable=False)
    camera_type: Mapped[CameraType] = mapped_column(
        Enum(CameraType, values_callable=lambda x: [e.value for e in x]),
        default=CameraType.rgb,
        nullable=False,
    )
    install_position: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    fps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ros_topic: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[CameraStatus] = mapped_column(
        Enum(CameraStatus, values_callable=lambda x: [e.value for e in x]),
        default=CameraStatus.offline,
        nullable=False,
    )
    last_online_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    persons: Mapped[list["Person"]] = relationship(back_populates="camera")
    event_logs: Mapped[list["EventLog"]] = relationship(back_populates="camera")
    alarm_logs: Mapped[list["AlarmLog"]] = relationship(back_populates="camera")
    analysis_tasks: Mapped[list["VideoAnalysisTask"]] = relationship(back_populates="camera")


# ---------- 表 4-1-4 主体表 ----------


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    person_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    person_type: Mapped[PersonType] = mapped_column(
        Enum(PersonType, values_callable=lambda x: [e.value for e in x]),
        default=PersonType.other,
        nullable=False,
    )
    label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    appearance_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    latest_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    latest_pos_x: Mapped[Optional[float]] = mapped_column(nullable=True)
    latest_pos_y: Mapped[Optional[float]] = mapped_column(nullable=True)
    map_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    robot_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    camera_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("cameras.id"), nullable=True)
    status: Mapped[PersonStatus] = mapped_column(
        Enum(PersonStatus, values_callable=lambda x: [e.value for e in x]),
        default=PersonStatus.active,
        nullable=False,
    )
    remark: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    camera: Mapped[Optional["Camera"]] = relationship(back_populates="persons")
    alarm_logs: Mapped[list["AlarmLog"]] = relationship(back_populates="person")


# ---------- 表 4-1-6 事件日志表 ----------


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_source: Mapped[EventSource] = mapped_column(
        Enum(EventSource, values_callable=lambda x: [e.value for e in x]),
        default=EventSource.system,
        nullable=False,
    )
    event_level: Mapped[EventLevel] = mapped_column(
        Enum(EventLevel, values_callable=lambda x: [e.value for e in x]),
        default=EventLevel.info,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    robot_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    camera_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("cameras.id"), nullable=True)
    related_alarm_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("alarm_logs.id"), nullable=True
    )
    related_task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("video_analysis_tasks.id"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    camera: Mapped[Optional["Camera"]] = relationship(back_populates="event_logs")
    related_alarm: Mapped[Optional["AlarmLog"]] = relationship(back_populates="related_events")
    related_task: Mapped[Optional["VideoAnalysisTask"]] = relationship(back_populates="related_events")


# ---------- 表 4-1-7 预警区域表 ----------


class WarningZone(Base):
    __tablename__ = "warning_zones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    zone_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    zone_name: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_type: Mapped[ZoneType] = mapped_column(
        Enum(ZoneType, values_callable=lambda x: [e.value for e in x]),
        default=ZoneType.warning,
        nullable=False,
    )
    map_name: Mapped[str] = mapped_column(String(128), nullable=False)
    polygon_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]),
        default=RiskLevel.medium,
        nullable=False,
    )
    is_enabled: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    creator: Mapped[Optional["User"]] = relationship(back_populates="created_zones")
    alarm_logs: Mapped[list["AlarmLog"]] = relationship(back_populates="warning_zone")


# ---------- 表 4-1-10 视频分析任务表 ----------


class VideoAnalysisTask(Base):
    __tablename__ = "video_analysis_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    robot_code: Mapped[str] = mapped_column(String(32), nullable=False)
    camera_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("cameras.id"), nullable=True)
    waypoints_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    loop_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    return_to_start: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    detection_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.draft,
        nullable=False,
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType, values_callable=lambda x: [e.value for e in x]),
        default=TriggerType.manual,
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    alarm_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    camera: Mapped[Optional["Camera"]] = relationship(back_populates="analysis_tasks")
    creator: Mapped[Optional["User"]] = relationship(back_populates="created_tasks")
    alarm_logs: Mapped[list["AlarmLog"]] = relationship(back_populates="task")
    related_events: Mapped[list["EventLog"]] = relationship(back_populates="related_task")


# ---------- 表 4-1-8 报警记录表 ----------


class AlarmLog(Base):
    __tablename__ = "alarm_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alarm_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    alarm_type: Mapped[AlarmType] = mapped_column(
        Enum(AlarmType, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0, nullable=False)
    robot_code: Mapped[str] = mapped_column(String(32), nullable=False)
    camera_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("cameras.id"), nullable=True)
    warning_zone_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("warning_zones.id"), nullable=True
    )
    person_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("person.id"), nullable=True)
    task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("video_analysis_tasks.id"), nullable=True
    )
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    pos_x: Mapped[float] = mapped_column(nullable=False)
    pos_y: Mapped[float] = mapped_column(nullable=False)
    pos_yaw: Mapped[Optional[float]] = mapped_column(nullable=True)
    map_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[AlarmStatus] = mapped_column(
        Enum(AlarmStatus, values_callable=lambda x: [e.value for e in x]),
        default=AlarmStatus.pending,
        nullable=False,
    )
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    handled_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    handled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    handle_remark: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    mqtt_pushed: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    camera: Mapped[Optional["Camera"]] = relationship(back_populates="alarm_logs")
    warning_zone: Mapped[Optional["WarningZone"]] = relationship(back_populates="alarm_logs")
    person: Mapped[Optional["Person"]] = relationship(back_populates="alarm_logs")
    task: Mapped[Optional["VideoAnalysisTask"]] = relationship(back_populates="alarm_logs")
    handler: Mapped[Optional["User"]] = relationship(back_populates="handled_alarms")
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="alarm")
    related_events: Mapped[list["EventLog"]] = relationship(back_populates="related_alarm")


# ---------- 表 4-1-9 反馈表 ----------


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alarm_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("alarm_logs.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType, values_callable=lambda x: [e.value for e in x]),
        default=FeedbackType.alarm_handle,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    attachment_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[FeedbackStatus] = mapped_column(
        Enum(FeedbackStatus, values_callable=lambda x: [e.value for e in x]),
        default=FeedbackStatus.pending,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    alarm: Mapped[Optional["AlarmLog"]] = relationship(back_populates="feedbacks")
    user: Mapped["User"] = relationship(back_populates="feedbacks")


# ---------- 表 4-1-11 AI 日报表 ----------


class AiDailyReport(Base):
    __tablename__ = "ai_daily_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_title: Mapped[str] = mapped_column(String(256), nullable=False)
    report_type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, values_callable=lambda x: [e.value for e in x]),
        default=ReportType.daily,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    alarm_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    context_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_by: Mapped[ReportGeneratedBy] = mapped_column(
        Enum(ReportGeneratedBy, values_callable=lambda x: [e.value for e in x]),
        default=ReportGeneratedBy.system,
        nullable=False,
    )
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, values_callable=lambda x: [e.value for e in x]),
        default=ReportStatus.generating,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[Optional["User"]] = relationship(back_populates="ai_reports")
