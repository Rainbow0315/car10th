-- 迁移：移除 operation_log.ip 列
-- 用法: python scripts/run_migration.py db/migrations/002_drop_operation_log_ip.sql

USE parking_inspection_robot;

ALTER TABLE operation_log DROP COLUMN ip;
