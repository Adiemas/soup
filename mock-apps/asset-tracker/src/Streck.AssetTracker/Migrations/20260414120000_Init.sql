-- 20260414120000_Init.sql — forward migration authored by sql-specialist
-- (Constitution V.4: sole author of migrations).
--
-- Creates locations, owners, assets + FKs + indexes.
-- EF Core's model snapshot remains the source of truth for the C#
-- migration class; this raw-SQL companion satisfies Constitution V.1
-- ("every migration ships up + down") because EF Core's `dotnet ef
-- migrations script` does not emit a reversible down file by default.

begin;

create extension if not exists pgcrypto;

create table if not exists locations (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    site        text not null,
    created_at  timestamptz not null default now()
);

create table if not exists owners (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    email       text not null,
    created_at  timestamptz not null default now()
);

create unique index if not exists ux_owners_email on owners (email);

create table if not exists assets (
    id               uuid primary key,  -- app-generated UUID v7
    asset_type       text not null,
    serial           text not null,
    manufacturer     text,
    location_id      uuid not null,
    owner_id         uuid not null,
    calibrated_at    timestamptz,
    calibration_due  timestamptz,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    constraint assets_location_id_fkey
        foreign key (location_id) references locations(id) on delete restrict,
    constraint assets_owner_id_fkey
        foreign key (owner_id)    references owners(id)    on delete restrict
);

create unique index if not exists ux_assets_serial          on assets (serial);
create        index if not exists idx_assets_location_id    on assets (location_id);
create        index if not exists idx_assets_owner_id       on assets (owner_id);
create        index if not exists idx_assets_calibration_due on assets (calibration_due);

commit;
