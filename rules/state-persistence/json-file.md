# State persistence — JSON file

For scripts and scheduled jobs that keep a small amount of state
(dedup sets, last-seen cursors, run counters) in a single JSON file.
Canonical patterns, in the order every agent should apply them.

## 1. Atomic write: tmpfile + rename

Never write directly to the target file. A crash mid-write leaves a
truncated file, and concurrent readers see torn data. Instead:

1. Write to `state.json.tmp` in the SAME directory as `state.json`.
2. `fsync` the tmpfile (Node: `fh.sync()`; Python: `os.fsync(fd)`).
3. Atomically rename over the target (`fs.rename` / `os.replace`).

On POSIX and on Windows (with `os.replace` / `fs.rename`) this is
atomic from the reader's point of view — either the old file or the
new file, never a partial one.

```ts
// Node / TypeScript
import { writeFile, rename, open } from "node:fs/promises";
import { dirname, join } from "node:path";

async function writeAtomic(targetPath: string, body: string): Promise<void> {
  const dir = dirname(targetPath);
  const tmp = join(dir, `.${Date.now()}-${process.pid}.tmp`);
  const fh = await open(tmp, "w");
  try {
    await fh.writeFile(body, "utf8");
    await fh.sync();          // force to disk before rename
  } finally {
    await fh.close();
  }
  await rename(tmp, targetPath);
}
```

```python
# Python
import json, os, tempfile

def write_atomic(path: str, obj) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic on POSIX and Windows
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```

## 2. File lock for same-host concurrency

Atomic rename prevents torn files. It does NOT prevent two writers
from racing on read-modify-write — the second rename silently
overwrites the first writer's changes.

Take a lock around the full read-modify-write cycle:

- **Linux/macOS:** `fcntl.flock(fd, fcntl.LOCK_EX)` (Python) or
  `proper-lockfile` npm package.
- **Windows:** `msvcrt.locking()` on the handle, or use a library that
  abstracts both (`filelock` on PyPI; `proper-lockfile` for Node).

Prefer a library. `filelock` / `proper-lockfile` handle the corner
cases (stale locks from crashed processes) better than hand-rolled
code.

```python
from filelock import FileLock

with FileLock(f"{path}.lock", timeout=30):
    state = read_json(path)           # defensive-revalidate (§3)
    state["seen"].add(new_id)
    write_atomic(path, state)         # §1
```

For MULTI-HOST concurrency (two VMs, two containers), a file lock on
the local filesystem is not enough. Use an orchestration-level
constraint instead — see `git-branch-as-db.md` §4 and
`rules/state-persistence/sqlite.md` §2. If the data must stay in a JSON
file, a GitHub Actions `concurrency: <group>` block or a cron-lock
record in Redis is the load-bearing defense, not the filesystem.

## 3. Defensive revalidation on read

The file on disk may have been edited by another process (or hand-
edited by a sleepy engineer) between your last write and this read.
Revalidate against a schema BEFORE using the data:

```ts
import { z } from "zod";

const StateSchema = z.object({
  version: z.literal(1),
  seen: z.array(z.string()).max(100_000),
  updatedAt: z.string().datetime(),
});

function readState(path: string): z.infer<typeof StateSchema> {
  const body = readFileSync(path, "utf8");
  const parsed = JSON.parse(body);
  return StateSchema.parse(parsed); // throws on shape drift
}
```

1. Bump `version` when the shape changes. Read code matches on
   `version` and migrates forward.
2. Cap array/map sizes in the schema. Unbounded state is a latent
   denial-of-service — treat the local file as untrusted input.
3. Never trust a partial read. If the JSON is invalid, fall back to
   the backup (§4) or fail loudly — do not silently write a new file
   with "whatever we could salvage."

## 4. Backup-on-write

Before writing a new version, copy the current file to `state.json.bak`
(atomic rename). Keep one generation; older ones live in git (see
`git-branch-as-db.md`).

```python
import shutil, os

def write_with_backup(path: str, obj) -> None:
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    write_atomic(path, obj)
```

Rationale: if a newly-deployed version corrupts the state shape
(missing field, wrong type), the backup is the last known-good. Without
it, recovery means grep through logs.

## 5. What NOT to do

1. Do not write JSON with `fs.writeFile(path, ...)` directly. It is
   NOT atomic; a crash mid-write truncates the target.
2. Do not lock by "check if `state.lock` exists; else create it." That
   race window is wide open; use a proper OS lock.
3. Do not assume your only process writes this file. The cron job,
   the admin script, and the dev laptop all count.
4. Do not skip the schema. A seemingly-minor drift (`number` vs
   `string`) manifests at 3AM.
5. Do not keep unbounded state (uncapped `seen` sets, ever-growing
   arrays). Rotate, archive, compact.
