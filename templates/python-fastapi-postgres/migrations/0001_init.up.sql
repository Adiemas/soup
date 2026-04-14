-- 0001_init: bootstrap schema
CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO app_meta(key, value) VALUES ('schema_version', '0001')
ON CONFLICT (key) DO NOTHING;
