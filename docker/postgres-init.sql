-- Soup — Postgres initialization
-- Runs once, on a fresh data volume. Idempotent for safety.
-- Creates the `soup` role + `soup_rag` database to match .env.example.

-- Safety: nothing here should fail a re-run.
DO $$
BEGIN
    -- Role
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'soup') THEN
        CREATE ROLE soup WITH LOGIN PASSWORD 'soup';
    END IF;

    -- Allow createdb for local dev convenience
    EXECUTE 'ALTER ROLE soup CREATEDB';
END
$$;

-- Database (outside the DO block — CREATE DATABASE cannot run inside one).
SELECT 'CREATE DATABASE soup_rag OWNER soup'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'soup_rag')
\gexec

-- Connect to the fresh db to load extensions.
\connect soup_rag

-- Extensions LightRAG + semantic search require.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Schemas: one for RAG pipeline, one for orchestrator metadata.
CREATE SCHEMA IF NOT EXISTS rag AUTHORIZATION soup;
CREATE SCHEMA IF NOT EXISTS orchestrator AUTHORIZATION soup;

GRANT ALL ON SCHEMA rag TO soup;
GRANT ALL ON SCHEMA orchestrator TO soup;
GRANT ALL ON ALL TABLES IN SCHEMA rag TO soup;
GRANT ALL ON ALL TABLES IN SCHEMA orchestrator TO soup;

-- The actual LightRAG tables are created on first `just rag-ingest` run
-- (LightRAG owns its own DDL). This file only provisions the environment.

-- Sanity row in a heartbeat table so `just doctor` can confirm connectivity.
CREATE TABLE IF NOT EXISTS orchestrator.heartbeat (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    note        text NOT NULL DEFAULT 'soup-init'
);
INSERT INTO orchestrator.heartbeat(note) VALUES ('db initialized');
