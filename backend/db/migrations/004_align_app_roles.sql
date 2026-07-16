-- Align backend roles with current mobile App role names.
-- Usage: python scripts/run_migration.py db/migrations/004_align_app_roles.sql

USE parking_inspection_robot;

START TRANSACTION;

-- Existing databases used `operator` for duty officer and `maintainer` for operator.
-- Rename through a temporary code to avoid unique-key collisions.
UPDATE `role`
SET role_code = 'operator_legacy'
WHERE role_code = 'operator';

UPDATE `role`
SET
    role_code = 'operator',
    role_name = '运维人员',
    permissions = '["robot:read","robot:control","alarm:read","alarm:handle","patrol:read","patrol:write","camera:read"]',
    description = '遥控小车、现场核查、任务配置',
    sort_order = 3,
    status = 1
WHERE role_code = 'maintainer';

UPDATE `role`
SET
    role_code = 'dutyOfficer',
    role_name = '值班员',
    permissions = '["dashboard:read","robot:read","alarm:read","alarm:handle","patrol:read","patrol:write","report:read","llm:use"]',
    description = '值班监控、告警处置、巡检任务',
    sort_order = 2,
    status = 1
WHERE role_code = 'operator_legacy';

INSERT INTO `role` (role_code, role_name, permissions, description, sort_order, status)
VALUES
    ('admin', '管理员', '["*"]', '全部权限', 1, 1),
    (
        'dutyOfficer',
        '值班员',
        '["dashboard:read","robot:read","alarm:read","alarm:handle","patrol:read","patrol:write","report:read","llm:use"]',
        '值班监控、告警处置、巡检任务',
        2,
        1
    ),
    (
        'operator',
        '运维人员',
        '["robot:read","robot:control","alarm:read","alarm:handle","patrol:read","patrol:write","camera:read"]',
        '遥控小车、现场核查、任务配置',
        3,
        1
    )
ON DUPLICATE KEY UPDATE
    role_name = VALUES(role_name),
    permissions = VALUES(permissions),
    description = VALUES(description),
    sort_order = VALUES(sort_order),
    status = VALUES(status);

COMMIT;
