-- 20260414120000_Init.down.sql — reverse migration authored by sql-specialist
--
-- Drops in reverse order of creation. Guarded with IF EXISTS so reapply
-- in mixed environments does not fail (rules/postgres/migrations.md §4.2).
-- pgcrypto is NOT dropped; other objects may rely on it.

begin;

drop index if exists idx_assets_calibration_due;
drop index if exists idx_assets_owner_id;
drop index if exists idx_assets_location_id;
drop index if exists ux_assets_serial;

drop table if exists assets;

drop index if exists ux_owners_email;
drop table if exists owners;

drop table if exists locations;

commit;
