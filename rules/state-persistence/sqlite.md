# State persistence — SQLite

For single-node apps, scripts, and desktop tools where Postgres is
overkill. SQLite is a file with ACID transactions, not a toy.

## 1. WAL mode — turn it on

```sql
PRAGMA journal_mode = WAL;          -- many-reader / one-writer concurrency
PRAGMA synchronous = NORMAL;        -- fsync at commit+checkpoint, not every op
PRAGMA foreign_keys = ON;           -- SQLite defaults to OFF (!); enforce FKs
PRAGMA busy_timeout = 5000;         -- wait 5s when another writer holds the lock
```

Rationale:

- **WAL** lets readers proceed during writes. Default `DELETE` journal
  mode blocks readers on every write — fine for a single thread, bad
  for any real workload.
- **`synchronous = NORMAL`** is the right trade-off for most
  applications on WAL: durable across process crashes, may lose the
  last few seconds of writes on a hard power failure. `FULL` syncs
  every commit and is slower; `OFF` trades durability for throughput
  and is rarely correct. With WAL + `NORMAL`, the checkpoint is the
  durability boundary, not every commit.
- **`foreign_keys = ON`** must be set on EVERY connection; SQLite does
  not persist it. Forgetting it means FK constraints silently do
  nothing.
- **`busy_timeout`** handles the "database is locked" class of errors
  gracefully instead of failing immediately.

Run these PRAGMAs in your connection-factory, once per connection.

## 2. Connection pooling caveats

SQLite is single-writer. Pooling N connections does NOT give you N
writers in parallel — they serialize on the database file lock. Pooling
helps for reader concurrency (WAL), not writer throughput.

Rules:

1. One writer thread / coroutine; N readers fine. If the app has
   "burst-write" patterns (ingestion), funnel writes through a single
   channel/queue and let readers do what they like.
2. In a web server (`better-sqlite3`, `aiosqlite`, `sqlite3`), keep a
   reader pool (size 4-8) and a dedicated writer connection. Do not
   let request handlers open raw connections.
3. Never share a connection across threads unless the driver
   explicitly supports it AND you take the driver's lock. The default
   `sqlite3` module is single-thread.
4. Short transactions. A long-held write lock kills every other
   writer that's queued behind it.

## 3. ATTACH DATABASE — multi-file state

When state logically splits (hot working set + cold archive), use
`ATTACH`:

```sql
ATTACH DATABASE 'archive.sqlite' AS archive;

INSERT INTO archive.events SELECT * FROM main.events
WHERE created_at < datetime('now', '-30 days');

DELETE FROM main.events WHERE created_at < datetime('now', '-30 days');
```

1. Each attached database contributes to the transaction if writable.
   Commits span both — atomicity across files, within one process.
2. `ATTACH` is per-connection. It does not persist. Attach in your
   connection factory (same place as the PRAGMAs).
3. Backups of `ATTACH`ed databases need to copy each file separately.

## 4. Migrations with `PRAGMA user_version`

SQLite has no migrations framework baked in. Roll your own:

```python
def migrate(conn) -> None:
    cur = conn.execute("PRAGMA user_version")
    version = cur.fetchone()[0]

    if version < 1:
        conn.executescript("""
            CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            PRAGMA user_version = 1;
        """)
    if version < 2:
        conn.executescript("""
            ALTER TABLE items ADD COLUMN tags TEXT;
            PRAGMA user_version = 2;
        """)
    # ... etc, in order
```

Rules:

1. `user_version` is the source of truth for "what schema is this DB
   at." Never gate on introspection (`PRAGMA table_info(...)`) — it
   races.
2. Every migration step is idempotent by the version check. Running
   `migrate()` twice is a no-op.
3. SQLite's `ALTER TABLE` is LIMITED. You can `ADD COLUMN` and
   (since 3.25) `RENAME COLUMN` / `DROP COLUMN`. You CANNOT change a
   column type or add a constraint to an existing column. For those,
   do the 12-step dance:
   - Create a new table with the desired shape.
   - `INSERT INTO new SELECT ... FROM old`.
   - `DROP TABLE old; ALTER TABLE new RENAME TO old;`.
   - Recreate indexes and triggers.
4. Do destructive migrations inside a transaction (`BEGIN; ... COMMIT;`)
   so a failure mid-migration leaves the DB at the previous
   `user_version`.

## 5. Backup & recovery

Don't `cp` a hot SQLite file — you'll get a WAL-inconsistent copy.
Use the backup API or `VACUUM INTO`:

```sql
VACUUM INTO '/backups/app-2026-04-14.sqlite';   -- atomic, consistent
```

Or from code: `sqlite3.Connection.backup()` (Python),
`db.backup("path")` (better-sqlite3).

## 6. What NOT to do

1. Do not build a REST service with sqlite as the primary store if
   you expect many concurrent writers. Postgres is right for that.
2. Do not rely on `DELETE ... WHERE rowid = N` when `rowid` could be
   reused. Use `AUTOINCREMENT` on the primary key if you need stable
   ids.
3. Do not put BLOBs larger than a few MB in the DB. Store them on
   disk and keep the path in SQLite.
4. Do not open the same file in two processes WITHOUT WAL. Default
   journal mode cannot coordinate cross-process readers during writes.
5. Do not forget `PRAGMA foreign_keys = ON` on every new connection.
   It's the most common footgun.
