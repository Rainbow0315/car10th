-- Add model detection details to alarm_logs.
-- Usage: python scripts/run_migration.py db/migrations/003_extend_alarm_detection_fields.sql

USE parking_inspection_robot;

ALTER TABLE alarm_logs
    ADD COLUMN camera_code VARCHAR(64) NULL COMMENT 'Camera code' AFTER robot_code,
    ADD COLUMN detection_model VARCHAR(32) NULL COMMENT 'AI model tag' AFTER image_url,
    ADD COLUMN detection_label VARCHAR(128) NULL COMMENT 'Model output label' AFTER detection_model,
    ADD COLUMN bbox_json JSON NULL COMMENT 'Detection bbox [x1,y1,x2,y2]' AFTER detection_label,
    ADD COLUMN raw_result JSON NULL COMMENT 'Raw model output item' AFTER bbox_json;

ALTER TABLE alarm_logs
    ADD KEY idx_alarm_camera_code (camera_code),
    ADD KEY idx_alarm_detection_model (detection_model);
