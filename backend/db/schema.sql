-- ============================================================
-- 园区地下通道智能巡检机器人 - MySQL 数据库表结构
-- 字符集: utf8mb4 | 引擎: InnoDB
-- ============================================================

CREATE DATABASE IF NOT EXISTS parking_inspection_robot
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE parking_inspection_robot;

-- ============================================================
-- 表 4-1-1 用户信息表 users
-- ============================================================
CREATE TABLE users (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    username        VARCHAR(64)     NOT NULL COMMENT '登录用户名',
    password_hash   VARCHAR(255)    NOT NULL COMMENT 'bcrypt 密码哈希',
    display_name    VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '显示名称/昵称',
    role_id         BIGINT UNSIGNED NOT NULL COMMENT '关联角色ID',
    phone           VARCHAR(20)     NULL COMMENT '手机号',
    email           VARCHAR(128)    NULL COMMENT '邮箱',
    avatar_url      VARCHAR(512)    NULL COMMENT '头像地址',
    status          TINYINT         NOT NULL DEFAULT 1 COMMENT '1=启用 0=禁用',
    last_login_at   DATETIME        NULL COMMENT '最后登录时间',
    last_login_ip   VARCHAR(45)     NULL COMMENT '最后登录IP',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username),
    KEY idx_users_role_id (role_id),
    KEY idx_users_status (status)
) ENGINE=InnoDB COMMENT='表4-1-1 用户信息表';

-- ============================================================
-- 表 4-1-2 角色表 role
-- ============================================================
CREATE TABLE role (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '角色ID',
    role_code       VARCHAR(32)     NOT NULL COMMENT '角色编码，如 admin/operator/maintainer',
    role_name       VARCHAR(64)     NOT NULL COMMENT '角色名称',
    permissions     JSON            NULL COMMENT '权限列表 JSON，如 ["alarm:read","patrol:write"]',
    description     VARCHAR(255)    NULL COMMENT '角色描述',
    sort_order      INT             NOT NULL DEFAULT 0 COMMENT '排序',
    status          TINYINT         NOT NULL DEFAULT 1 COMMENT '1=启用 0=禁用',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_role_code (role_code)
) ENGINE=InnoDB COMMENT='表4-1-2 角色表';

-- ============================================================
-- 表 4-1-3 操作日志表 operation_log
-- ============================================================
CREATE TABLE operation_log (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    user_id         BIGINT UNSIGNED NULL COMMENT '操作用户ID，系统任务可为空',
    username        VARCHAR(64)     NULL COMMENT '操作用户名快照',
    module          VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '操作模块，如 alarm/patrol/robot/auth',
    action_type     VARCHAR(64)     NOT NULL COMMENT '操作类型，如 login/patrol_start/alarm_close',
    action_desc     VARCHAR(512)    NOT NULL DEFAULT '' COMMENT '操作描述',
    request_method  VARCHAR(16)     NULL COMMENT 'HTTP 方法',
    request_url     VARCHAR(512)    NULL COMMENT '请求路径',
    request_params  JSON            NULL COMMENT '请求参数快照',
    response_code   INT             NULL COMMENT '响应状态码',
    ip_address      VARCHAR(45)     NULL COMMENT '客户端IP',
    user_agent      VARCHAR(512)    NULL COMMENT '客户端UA',
    robot_code      VARCHAR(32)     NULL COMMENT '关联机器人编码',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (id),
    KEY idx_op_log_user (user_id),
    KEY idx_op_log_module (module),
    KEY idx_op_log_action (action_type),
    KEY idx_op_log_time (created_at),
    CONSTRAINT fk_op_log_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='表4-1-3 操作日志表';

-- ============================================================
-- 表 4-1-4 主体表 person
-- 说明：视觉检测到的关注主体（违规抽烟人员、长时间滞留人员等）
-- ============================================================
CREATE TABLE person (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主体ID',
    person_code     VARCHAR(64)     NOT NULL COMMENT '主体唯一编码',
    person_type     ENUM('smoking', 'loitering', 'intruder', 'other')
                    NOT NULL DEFAULT 'other' COMMENT '主体类型',
    label           VARCHAR(64)     NULL COMMENT '标签/备注名',
    first_seen_at   DATETIME        NOT NULL COMMENT '首次发现时间',
    last_seen_at    DATETIME        NOT NULL COMMENT '最近发现时间',
    appearance_count INT UNSIGNED   NOT NULL DEFAULT 1 COMMENT '累计出现次数',
    latest_image_path VARCHAR(512)  NULL COMMENT '最近抓拍图路径',
    latest_pos_x    DOUBLE          NULL COMMENT '最近位置X',
    latest_pos_y    DOUBLE          NULL COMMENT '最近位置Y',
    map_name        VARCHAR(128)    NULL COMMENT '所在地图名称',
    robot_code      VARCHAR(32)     NULL COMMENT '发现该主体的机器人',
    camera_id       BIGINT UNSIGNED NULL COMMENT '发现该主体的摄像头',
    status          ENUM('active', 'resolved', 'ignored') NOT NULL DEFAULT 'active' COMMENT '跟踪状态',
    remark          VARCHAR(512)    NULL COMMENT '备注',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_person_code (person_code),
    KEY idx_person_type (person_type),
    KEY idx_person_last_seen (last_seen_at),
    KEY idx_person_robot (robot_code)
) ENGINE=InnoDB COMMENT='表4-1-4 主体表';

-- ============================================================
-- 表 4-1-5 摄像头信息表 cameras
-- 说明：巡检小车载摄像头（本项目无实时视频流，用于绑定检测源）
-- ============================================================
CREATE TABLE cameras (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '摄像头ID',
    camera_code     VARCHAR(64)     NOT NULL COMMENT '摄像头编码',
    camera_name     VARCHAR(128)    NOT NULL COMMENT '摄像头名称',
    robot_code      VARCHAR(32)     NOT NULL COMMENT '所属机器人编码',
    camera_type     ENUM('rgb', 'depth', 'infrared') NOT NULL DEFAULT 'rgb' COMMENT '摄像头类型',
    install_position VARCHAR(64)    NULL COMMENT '安装位置，如 front/left',
    resolution      VARCHAR(32)     NULL COMMENT '分辨率，如 1920x1080',
    fps             INT UNSIGNED    NULL COMMENT '帧率',
    ros_topic       VARCHAR(256)    NULL COMMENT 'ROS 图像话题',
    status          ENUM('online', 'offline', 'error') NOT NULL DEFAULT 'offline' COMMENT '设备状态',
    last_online_at  DATETIME        NULL COMMENT '最后在线时间',
    remark          VARCHAR(255)    NULL COMMENT '备注',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_camera_code (camera_code),
    KEY idx_cameras_robot (robot_code),
    KEY idx_cameras_status (status)
) ENGINE=InnoDB COMMENT='表4-1-5 摄像头信息表';

-- ============================================================
-- 表 4-1-6 事件日志表 event_logs
-- 说明：系统运行事件（巡检启停、模式切换、断连重连等）
-- ============================================================
CREATE TABLE event_logs (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '事件ID',
    event_no        VARCHAR(64)     NOT NULL COMMENT '事件编号',
    event_type      VARCHAR(64)     NOT NULL COMMENT '事件类型，如 patrol_start/mode_switch/offline',
    event_source    ENUM('robot', 'backend', 'app', 'system') NOT NULL DEFAULT 'system' COMMENT '事件来源',
    event_level     ENUM('info', 'warning', 'error', 'critical') NOT NULL DEFAULT 'info' COMMENT '事件级别',
    title           VARCHAR(256)    NOT NULL COMMENT '事件标题',
    content         JSON            NULL COMMENT '事件详情 JSON',
    robot_code      VARCHAR(32)     NULL COMMENT '关联机器人',
    camera_id       BIGINT UNSIGNED NULL COMMENT '关联摄像头',
    related_alarm_id BIGINT UNSIGNED NULL COMMENT '关联报警记录',
    related_task_id  BIGINT UNSIGNED NULL COMMENT '关联分析任务',
    occurred_at     DATETIME        NOT NULL COMMENT '事件发生时间',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_event_no (event_no),
    KEY idx_event_type (event_type),
    KEY idx_event_level (event_level),
    KEY idx_event_robot (robot_code),
    KEY idx_event_occurred (occurred_at)
) ENGINE=InnoDB COMMENT='表4-1-6 事件日志表';

-- ============================================================
-- 表 4-1-7 预警区域表 warning_zones
-- 说明：地图上的预警/禁区区域（电子围栏）
-- ============================================================
CREATE TABLE warning_zones (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '区域ID',
    zone_code       VARCHAR(64)     NOT NULL COMMENT '区域编码',
    zone_name       VARCHAR(128)    NOT NULL COMMENT '区域名称',
    zone_type       ENUM('forbidden', 'warning', 'patrol') NOT NULL DEFAULT 'warning'
                    COMMENT 'forbidden=禁区 warning=预警 patrol=巡检重点',
    map_name        VARCHAR(128)    NOT NULL COMMENT '所属地图名称',
    polygon_json    JSON            NOT NULL COMMENT '多边形坐标 [{x,y},...]',
    risk_level      ENUM('high', 'medium', 'low') NOT NULL DEFAULT 'medium' COMMENT '风险等级',
    is_enabled      TINYINT         NOT NULL DEFAULT 1 COMMENT '1=启用 0=禁用',
    description     VARCHAR(512)    NULL COMMENT '区域说明',
    created_by      BIGINT UNSIGNED NULL COMMENT '创建人',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_zone_code (zone_code),
    KEY idx_zone_map (map_name),
    KEY idx_zone_type (zone_type),
    KEY idx_zone_enabled (is_enabled),
    CONSTRAINT fk_zone_creator FOREIGN KEY (created_by) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='表4-1-7 预警区域表';

-- ============================================================
-- 表 4-1-8 报警记录表 alarm_logs
-- 说明：YOLO 视觉检测异常报警（异物/裂缝/积水/抽烟等）
-- ============================================================
CREATE TABLE alarm_logs (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '报警ID',
    alarm_no        VARCHAR(64)     NOT NULL COMMENT '报警编号',
    alarm_type      ENUM('foreign_object', 'crack', 'pothole', 'water', 'smoking', 'loitering', 'other')
                    NOT NULL COMMENT '报警类型',
    risk_level      ENUM('high', 'medium', 'low') NOT NULL COMMENT '风险等级',
    confidence      DECIMAL(5,4)    NOT NULL DEFAULT 0.0000 COMMENT '检测置信度 0-1',
    robot_code      VARCHAR(32)     NOT NULL COMMENT '来源机器人',
    camera_id       BIGINT UNSIGNED NULL COMMENT '来源摄像头',
    warning_zone_id BIGINT UNSIGNED NULL COMMENT '所属预警区域',
    person_id       BIGINT UNSIGNED NULL COMMENT '关联主体（人员类报警）',
    task_id         BIGINT UNSIGNED NULL COMMENT '关联分析/巡检任务',
    image_path      VARCHAR(512)    NOT NULL COMMENT '抓拍图存储路径',
    image_url       VARCHAR(512)    NULL COMMENT 'HTTP 访问地址',
    pos_x           DOUBLE          NOT NULL COMMENT '发生位置X',
    pos_y           DOUBLE          NOT NULL COMMENT '发生位置Y',
    pos_yaw         DOUBLE          NULL COMMENT '朝向弧度',
    map_name        VARCHAR(128)    NULL COMMENT '地图名称',
    status          ENUM('pending', 'processing', 'closed') NOT NULL DEFAULT 'pending' COMMENT '处理状态',
    dedup_key       VARCHAR(64)     NOT NULL COMMENT '去重键',
    handled_by      BIGINT UNSIGNED NULL COMMENT '处理人',
    handled_at      DATETIME        NULL COMMENT '处理时间',
    handle_remark   VARCHAR(512)    NULL COMMENT '处置备注',
    detected_at     DATETIME        NOT NULL COMMENT '检测时间',
    mqtt_pushed     TINYINT         NOT NULL DEFAULT 0 COMMENT '1=已MQTT推送',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_alarm_no (alarm_no),
    KEY idx_alarm_type (alarm_type),
    KEY idx_alarm_risk (risk_level),
    KEY idx_alarm_status (status),
    KEY idx_alarm_robot_time (robot_code, detected_at),
    KEY idx_alarm_dedup (dedup_key, detected_at),
    KEY idx_alarm_zone (warning_zone_id),
    KEY idx_alarm_person (person_id),
    CONSTRAINT fk_alarm_camera FOREIGN KEY (camera_id) REFERENCES cameras(id),
    CONSTRAINT fk_alarm_zone FOREIGN KEY (warning_zone_id) REFERENCES warning_zones(id),
    CONSTRAINT fk_alarm_person FOREIGN KEY (person_id) REFERENCES person(id),
    CONSTRAINT fk_alarm_handler FOREIGN KEY (handled_by) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='表4-1-8 报警记录表';

-- ============================================================
-- 表 4-1-9 反馈表 feedback
-- 说明：值班员对报警/系统的反馈评价
-- ============================================================
CREATE TABLE feedback (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '反馈ID',
    alarm_id        BIGINT UNSIGNED NULL COMMENT '关联报警ID',
    user_id         BIGINT UNSIGNED NOT NULL COMMENT '反馈人',
    feedback_type   ENUM('alarm_handle', 'false_alarm', 'system', 'suggestion')
                    NOT NULL DEFAULT 'alarm_handle' COMMENT '反馈类型',
    content         TEXT            NOT NULL COMMENT '反馈内容',
    rating          TINYINT UNSIGNED NULL COMMENT '评分 1-5',
    attachment_url  VARCHAR(512)    NULL COMMENT '附件地址',
    status          ENUM('pending', 'reviewed', 'archived') NOT NULL DEFAULT 'pending' COMMENT '处理状态',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_feedback_alarm (alarm_id),
    KEY idx_feedback_user (user_id),
    KEY idx_feedback_type (feedback_type),
    CONSTRAINT fk_feedback_alarm FOREIGN KEY (alarm_id) REFERENCES alarm_logs(id),
    CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='表4-1-9 反馈表';

-- ============================================================
-- 表 4-1-10 视频分析任务表 video_analysis_tasks
-- 说明：巡检过程中的视觉分析任务（对应自主巡航+YOLO检测）
-- ============================================================
CREATE TABLE video_analysis_tasks (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '任务ID',
    task_code       VARCHAR(64)     NOT NULL COMMENT '任务编码',
    task_name       VARCHAR(128)    NOT NULL COMMENT '任务名称',
    robot_code      VARCHAR(32)     NOT NULL COMMENT '执行机器人',
    camera_id       BIGINT UNSIGNED NULL COMMENT '分析摄像头',
    waypoints_json  JSON            NOT NULL COMMENT '巡检航点 [{seq,x,y,yaw,name},...]',
    schedule_cron   VARCHAR(64)     NULL COMMENT '定时 cron，NULL=仅手动',
    loop_count      INT UNSIGNED    NOT NULL DEFAULT 1 COMMENT '循环次数',
    return_to_start TINYINT         NOT NULL DEFAULT 1 COMMENT '1=完成后回起点',
    detection_config JSON           NULL COMMENT '检测开关与阈值 {"foreign_object":0.7}',
    status          ENUM('draft', 'pending', 'running', 'completed', 'failed', 'cancelled')
                    NOT NULL DEFAULT 'draft' COMMENT '任务状态',
    trigger_type    ENUM('manual', 'scheduled', 'app') NOT NULL DEFAULT 'manual' COMMENT '触发方式',
    started_at      DATETIME        NULL COMMENT '开始时间',
    finished_at     DATETIME        NULL COMMENT '结束时间',
    alarm_count     INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '本次任务报警数',
    result_summary  TEXT            NULL COMMENT '任务结果摘要',
    error_message   VARCHAR(512)    NULL COMMENT '失败原因',
    created_by      BIGINT UNSIGNED NULL COMMENT '创建人',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_code (task_code),
    KEY idx_task_robot (robot_code),
    KEY idx_task_status (status),
    KEY idx_task_started (started_at),
    CONSTRAINT fk_task_camera FOREIGN KEY (camera_id) REFERENCES cameras(id),
    CONSTRAINT fk_task_creator FOREIGN KEY (created_by) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='表4-1-10 视频分析任务表';

-- ============================================================
-- 表 4-1-11 AI 日报表 ai_daily_reports
-- 说明：LLM 自动生成的巡检日报/分析报告
-- ============================================================
CREATE TABLE ai_daily_reports (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '日报ID',
    report_no       VARCHAR(64)     NOT NULL COMMENT '报告编号',
    report_date     DATE            NOT NULL COMMENT '报告日期',
    report_title    VARCHAR(256)    NOT NULL COMMENT '报告标题',
    report_type     ENUM('daily', 'night', 'weekly', 'custom') NOT NULL DEFAULT 'daily' COMMENT '报告类型',
    content         LONGTEXT        NOT NULL COMMENT '报告正文（Markdown/纯文本）',
    summary         VARCHAR(1024)   NULL COMMENT '摘要',
    alarm_count     INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '统计报警数',
    event_count     INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '统计事件数',
    task_count      INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '统计巡检任务数',
    context_snapshot JSON           NULL COMMENT '生成时注入的上下文快照',
    llm_model       VARCHAR(64)     NULL COMMENT '使用的大模型名称',
    token_count     INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '消耗 token 数',
    generated_by    ENUM('system', 'user') NOT NULL DEFAULT 'system' COMMENT '生成方式',
    user_id         BIGINT UNSIGNED NULL COMMENT '请求生成的用户',
    status          ENUM('generating', 'completed', 'failed') NOT NULL DEFAULT 'generating' COMMENT '生成状态',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_report_no (report_no),
    KEY idx_report_date (report_date),
    KEY idx_report_type (report_type),
    KEY idx_report_user (user_id),
    CONSTRAINT fk_report_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='表4-1-11 AI日报表';

-- ============================================================
-- 补充外键（users.role_id 需在 role 表创建后添加）
-- ============================================================
ALTER TABLE users
    ADD CONSTRAINT fk_users_role FOREIGN KEY (role_id) REFERENCES role(id);

ALTER TABLE alarm_logs
    ADD CONSTRAINT fk_alarm_task FOREIGN KEY (task_id) REFERENCES video_analysis_tasks(id);

ALTER TABLE event_logs
    ADD CONSTRAINT fk_event_camera FOREIGN KEY (camera_id) REFERENCES cameras(id),
    ADD CONSTRAINT fk_event_alarm FOREIGN KEY (related_alarm_id) REFERENCES alarm_logs(id),
    ADD CONSTRAINT fk_event_task FOREIGN KEY (related_task_id) REFERENCES video_analysis_tasks(id);

ALTER TABLE person
    ADD CONSTRAINT fk_person_camera FOREIGN KEY (camera_id) REFERENCES cameras(id);

-- ============================================================
-- 初始种子数据
-- ============================================================
INSERT INTO role (role_code, role_name, permissions, description, sort_order) VALUES
('admin',     '管理员', '["*"]',                                              '全部权限',           1),
('operator',  '值班员', '["alarm:read","alarm:handle","patrol:read","report:read"]', '查看告警、处理告警', 2),
('maintainer','运维',   '["robot:control","patrol:write","config:write"]',    '遥控小车、配置任务',   3);

INSERT INTO users (username, password_hash, display_name, role_id) VALUES
('admin', '$2b$12$PLACEHOLDER_CHANGE_ON_DEPLOY', '系统管理员', 1);

INSERT INTO cameras (camera_code, camera_name, robot_code, camera_type, install_position, ros_topic, status) VALUES
('cam_robot_001_front', '巡检小车前置摄像头', 'robot_001', 'rgb', 'front', '/camera/image_raw', 'offline');
