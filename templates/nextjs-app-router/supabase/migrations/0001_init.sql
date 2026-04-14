-- 0001_init.sql — baseline schema.
-- Migrations are immutable once applied. Never edit a migration that has
-- shipped; create a new one and use expand/contract to change shape.

-- Extensions. Enable once; idempotent under Supabase migration semantics.
create extension if not exists "pgcrypto";
-- Uncomment when the project adds semantic search / embeddings:
-- create extension if not exists "vector";

-- Example table. Delete and replace with real schema.
create table if not exists public.items (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (length(title) between 1 and 200),
  body text
);

-- Row-Level Security. Default-deny, then add explicit policies per role.
alter table public.items enable row level security;

create policy "items_select_own"
  on public.items
  for select
  to authenticated
  using (user_id = auth.uid());

create policy "items_insert_own"
  on public.items
  for insert
  to authenticated
  with check (user_id = auth.uid());

create policy "items_update_own"
  on public.items
  for update
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create policy "items_delete_own"
  on public.items
  for delete
  to authenticated
  using (user_id = auth.uid());

-- Performance: index the FK column (Postgres doesn't auto-index FKs).
create index if not exists items_user_id_idx on public.items (user_id);
