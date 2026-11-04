BEGIN;

-- Running upgrade 20261103_0001 -> 20261103_0002

ALTER TABLE user_profiles ADD COLUMN planning_details JSON DEFAULT '{}' NOT NULL;

UPDATE alembic_version SET version_num='20261103_0002' WHERE alembic_version.version_num = '20261103_0001';

COMMIT;
