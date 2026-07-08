# MySQL 表结构说明
## 表清单

| 编号 | 表名 | 说明 | 对应业务 |
|------|------|------|----------|
| 4-1-1 | `users` | 用户信息表 | APP 登录账号 |
| 4-1-2 | `role` | 角色表 | 管理员/值班员/运维权限 |
| 4-1-3 | `operation_log` | 业务操作日志表 | 任务下发、告警处理、遥控等（不含登录/注册） |
| 4-1-4 | `person` | 主体表 | 抽烟/滞留等人员目标跟踪 |
| 4-1-5 | `cameras` | 摄像头信息表 | 小车载摄像头绑定 |
| 4-1-6 | `event_logs` | 事件日志表 | 巡检启停、断连等系统事件 |
| 4-1-7 | `warning_zones` | 预警区域表 | 地图禁区/预警/重点巡检区 |
| 4-1-8 | `alarm_logs` | 报警记录表 | YOLO 异常检测报警 |
| 4-1-9 | `feedback` | 反馈表 | 误报反馈、处置评价 |
| 4-1-10 | `video_analysis_tasks` | 视频分析任务表 | 自主巡航+视觉分析任务 |
| 4-1-11 | `ai_daily_reports` | AI 日报表 | LLM 生成的巡检日报 |

## ER 关系

```
role ── users ──┬── operation_log
                ├── feedback
                ├── warning_zones (created_by)
                ├── video_analysis_tasks (created_by)
                └── ai_daily_reports (user_id)

cameras ──┬── person
          ├── event_logs
          ├── alarm_logs
          └── video_analysis_tasks

warning_zones ── alarm_logs
person ── alarm_logs
video_analysis_tasks ── alarm_logs / event_logs

alarm_logs ── feedback / event_logs
```

## 与项目需求的映射

| 需求规格功能 | 使用表 |
|-------------|--------|
| 用户鉴权、角色权限 | users + role |
| 操作审计（业务） | operation_log |
| 异常告警、去重、处置 | alarm_logs |
| 预警/禁区地图 | warning_zones |
| 自主巡检任务调度 | video_analysis_tasks |
| 人员抽烟/滞留检测 | person + alarm_logs |
| 系统运行事件 | event_logs |
| LLM 巡检报告 | ai_daily_reports |
| 处置反馈 | feedback |

## 报警去重规则（alarm_logs.dedup_key）

```
dedup_key = MD5(f"{alarm_type}:{grid_x}:{grid_y}:{time_window}")
grid_x = round(pos_x / 2.0)   # 2m 网格
time_window = detected_at 按 5 分钟取整
```

## 枚举速查

**alarm_logs.alarm_type**: foreign_object / crack / pothole / water / smoking / loitering / other

**alarm_logs.status**: pending / processing / closed

**video_analysis_tasks.status**: draft / pending / running / completed / failed / cancelled

**ai_daily_reports.report_type**: daily / night / weekly / custom

## operation_log.action 示例（仅业务操作）

| action | 说明 |
|--------|------|
| `task_create` | 创建巡检任务 |
| `task_dispatch` | 下发巡检任务 |
| `patrol_start` | 启动自主巡检 |
| `patrol_stop` | 停止巡检 |
| `alarm_handle` | 处理告警 |
| `robot_control` | 遥控小车 |
| `zone_update` | 更新预警区域 |

登录、注册、改密等鉴权行为 **不写入** 此表。
