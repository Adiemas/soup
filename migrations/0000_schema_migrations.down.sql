-- 0000 down — drop the bookkeeping table.
-- Running this leaves the database unable to track further migrations
-- via the wrapper. Intended only as part of a full teardown.
DROP TABLE IF EXISTS schema_migrations;
