-- 迁移：简化 operation_log 表结构
-- 用法: 在 backend 目录执行 python scripts/run_migration.py db/migrations/001_simplify_operation_log.sql

USE parking_inspection_robot;

DROP TABLE IF EXISTS operation_log;

CREATE TABLE operation_log (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    user_id         BIGINT UNSIGNED NULL COMMENT '操作用户ID',
    action          VARCHAR(64)     NOT NULL COMMENT '操作类型',
    timestamp       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    description     VARCHAR(512)    NOT NULL DEFAULT '' COMMENT '操作描述',
    PRIMARY KEY (id),
    KEY idx_op_log_user (user_id),
    KEY idx_op_log_action (action),
    KEY idx_op_log_timestamp (timestamp),
    CONSTRAINT fk_op_log_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='表4-1-3 操作日志表';
