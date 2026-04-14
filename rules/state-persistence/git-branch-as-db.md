# State persistence — git branch as database

A legitimate pattern for scheduled jobs, aggregators, and static-site
generators. Commit state to a dedicated branch (e.g. `state`) instead
of adopting a full database. Used by `claude-news-aggregator` and
similar weekly-digest shapes.

## 1. When this pattern fits

- The job runs on a schedule (cron, GitHub Actions `schedule:`), not
  in response to user traffic.
- State size is measured in MB, not GB.
- State updates are low-frequency (minutes to days between writes),
  not high-frequency.
- You already have git + a remote you trust for availability.
- You want "what did the job see last week?" to be a git-log query,
  not a migration script.

If any of those are wrong (user-facing writes, multi-host concurrent
writes, sub-second updates), go to `sqlite.md` or a proper database.

## 2. Branch-per-entity strategy

Keep `main` clean (code only). Put state on a dedicated branch:

- `state` — current + historical state commits.
- `archive/<year>-<week>` — rolling snapshots for longer-term history.

A typical layout on the `state` branch:

```
state/
  seen.json           dedup cursor
  sources.json        last-fetched-at per source
  stats.json          counters
archive/
  2026-W15.md         human-readable weekly digest
  2026-W16.md
```

The job code lives on `main`. When it runs, it clones/checks out the
`state` branch into a worktree, reads, mutates, commits, pushes. Never
mix `main` and `state` in one worktree.

## 3. Atomic merge — the commit is the transaction

Each run is one commit on `state`. That commit is the atomic unit:
either all three files (`seen.json`, `sources.json`, `stats.json`)
update together, or none of them do.

```bash
# inside the state worktree
git add seen.json sources.json stats.json
git commit -m "run 2026-W15: 1589 scanned, 10 posted"
git push origin state
```

If the push fails (another job beat you to it), `git pull --rebase`
is NOT a safe recovery — it will try to three-way-merge
machine-generated JSON. Instead:

1. Refuse to continue.
2. Report the conflict up to orchestration.
3. Re-run from scratch: another job already advanced state; your work
   was redundant or needs a recompute from the new state.

## 4. Serialize at the orchestration boundary

Two jobs hitting the same `state` branch concurrently will race. The
only robust fix is to prevent the concurrency, not recover from it:

- **GitHub Actions:** set `concurrency: <group>` at the workflow
  level. GHA serializes jobs with the same group.
- **Cron on a VM:** use `flock /var/lock/<job>.lock cron-job-cmd` or
  wrap the job in a shell script that exits if another instance is
  running.
- **Kubernetes CronJob:** `spec.concurrencyPolicy: Forbid`.

```yaml
# .github/workflows/weekly-digest.yml
name: weekly-digest
on:
  schedule:
    - cron: "0 13 * * MON"
concurrency:
  group: weekly-digest
  cancel-in-progress: false
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with:
          ref: state
          path: ./state-wt
      # ... clone deps, run the job, commit + push state
```

`cancel-in-progress: false` ensures a late run waits rather than
clobbering a still-in-flight run.

## 5. Limitations (read before adopting)

1. **No joins.** JSON files don't have secondary indexes. If you find
   yourself scanning `seen.json` linearly on every run, it is time to
   move to SQLite.
2. **No multi-branch transactions.** If you split state across
   `state-a` and `state-b` branches, an atomic update across both is
   impossible with git alone. Keep related state co-located on one
   branch.
3. **No concurrent writers.** §4 is not optional.
4. **Clone time grows with history.** Use shallow clones (`--depth=1`)
   for the state branch in CI. Rotate heavy archives to
   `archive/<period>` directories and consider a periodic
   `git gc --aggressive` + force-push of a pruned history.
5. **No RLS.** The branch is public to anyone with repo access. Don't
   store secrets, don't store PII. Encrypt anything sensitive before
   commit (rare use case; usually a signal that this is the wrong
   pattern).
6. **Diffs on large JSON are noisy.** Reviewers can't eyeball a
   100-line JSON object diff meaningfully. Generate a human-readable
   markdown sibling (`archive/2026-W15.md`) so the weekly run produces
   a readable artifact the team actually reviews.

## 6. Read-side conventions

Consumers of state-branch data have two choices:

1. **Clone at read time.** Cheap for small state; the consumer always
   sees the latest.
2. **GitHub Raw URL with `If-None-Match`.** For read-heavy consumers,
   cache `seen.json` at the CDN edge and invalidate on commit SHA.

In both cases, validate the JSON against a Zod/Pydantic schema on read
(see `json-file.md` §3). The branch is the source of truth; the schema
is the contract; the client MUST NOT trust the shape.
