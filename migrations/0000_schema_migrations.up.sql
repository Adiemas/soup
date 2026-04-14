-- 0000 — schema_migrations bookkeeping table.
--
-- This migration is also available via `psql-wrap migrations-init`.
-- Historical note: an earlier version of cli_wrappers.psql ran this
-- DDL implicitly at migrate-up time, which violated Constitution Art.
-- V ("No raw DDL in runtime code"). It has been promoted to a real
-- migration. Operators must run either:
--
--   psql-wrap migrations-init
--
-- or apply this file explicitly before any other migration.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
