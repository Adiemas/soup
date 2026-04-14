"""One-shot migration: split mixed ``experiments.tsv`` into two files.

Background (iter-3 dogfood ε2)
------------------------------
Up through soup v0.x, two writers shared ``logging/experiments.tsv``:

* ``orchestrator/orchestrator.py::_append_experiment`` writes a 9-column
  row per ExecutionPlan run::

      ts  run_id  status  duration_sec  n_steps  budget_sec  cost_usd  aborted_reason  goal

* ``.claude/hooks/stop.py`` writes a 4-column row per Claude Code
  session::

      ts  session_id  files_touched  verdict_placeholder

Whichever writer ran first set the header; the second wrote rows that
did not match it. Any TSV consumer (jq | csvkit | duckdb) broke on the
first mixed file.

iter-3 ε2 splits the writers:

* The orchestrator keeps ``logging/experiments.tsv`` (9-col).
* The stop hook now writes ``logging/sessions.tsv`` (4-col).

This script migrates an existing mixed file in place. Each row is
classified by tab-count and routed to the correct destination. Header
rows are detected and skipped (re-emitted by their owning writer on the
next append). A ``~/<file>.bak`` backup of the input is written before
any output is touched.

Usage
-----
::

    python -m scripts.split_experiments_tsv \
        --in logging/experiments.tsv \
        --experiments-out logging/experiments.tsv \
        --sessions-out logging/sessions.tsv

Exit codes
----------
0  Success (or no-op when input does not exist).
1  Bad input (unreadable / empty).
2  Output write failure.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

EXPERIMENTS_HEADER_COLS = (
    "ts",
    "run_id",
    "status",
    "duration_sec",
    "n_steps",
    "budget_sec",
    "cost_usd",
    "aborted_reason",
    "goal",
)
SESSIONS_HEADER_COLS = (
    "ts",
    "session_id",
    "files_touched",
    "verdict_placeholder",
)


def _classify(row: list[str]) -> str:
    """Return ``"experiments"``, ``"sessions"``, or ``"unknown"`` for *row*."""
    if len(row) == len(EXPERIMENTS_HEADER_COLS):
        return "experiments"
    if len(row) == len(SESSIONS_HEADER_COLS):
        return "sessions"
    return "unknown"


def _is_header(row: list[str]) -> bool:
    """Detect either schema's header row (so we don't migrate it as data)."""
    if not row:
        return False
    return row[0] == "ts"


def split(
    src: Path,
    experiments_out: Path,
    sessions_out: Path,
) -> tuple[int, int, int]:
    """Split *src* into the two destination files.

    Returns ``(n_experiments, n_sessions, n_unknown)``.

    The destination files are always rewritten from scratch (the source
    is preserved as ``<src>.bak``). Each output starts with the
    appropriate ``# soup-schema:<name>-vN`` comment + tab-joined header
    so the result is parseable by ``csv.reader(delimiter="\\t")``.
    """
    if not src.exists():
        return (0, 0, 0)
    raw = src.read_text(encoding="utf-8")
    if not raw.strip():
        return (0, 0, 0)

    # Backup before touching anything.
    backup = src.with_suffix(src.suffix + ".bak")
    shutil.copyfile(src, backup)

    experiments_rows: list[list[str]] = []
    sessions_rows: list[list[str]] = []
    unknown = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            continue  # schema comment from a previous run
        row = line.split("\t")
        if _is_header(row):
            continue
        kind = _classify(row)
        if kind == "experiments":
            experiments_rows.append(row)
        elif kind == "sessions":
            sessions_rows.append(row)
        else:
            unknown += 1

    experiments_out.parent.mkdir(parents=True, exist_ok=True)
    sessions_out.parent.mkdir(parents=True, exist_ok=True)

    with experiments_out.open("w", encoding="utf-8") as fh:
        fh.write("# soup-schema:experiments-v1\n")
        fh.write("\t".join(EXPERIMENTS_HEADER_COLS) + "\n")
        for row in experiments_rows:
            fh.write("\t".join(row) + "\n")

    with sessions_out.open("w", encoding="utf-8") as fh:
        fh.write("# soup-schema:sessions-v1\n")
        fh.write("\t".join(SESSIONS_HEADER_COLS) + "\n")
        for row in sessions_rows:
            fh.write("\t".join(row) + "\n")

    return (len(experiments_rows), len(sessions_rows), unknown)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="src",
        type=Path,
        default=Path("logging/experiments.tsv"),
        help="Mixed input TSV to migrate (default: logging/experiments.tsv).",
    )
    parser.add_argument(
        "--experiments-out",
        type=Path,
        default=Path("logging/experiments.tsv"),
        help="Path to write the orchestrator-only file (default: in place).",
    )
    parser.add_argument(
        "--sessions-out",
        type=Path,
        default=Path("logging/sessions.tsv"),
        help="Path to write the stop-hook file (default: logging/sessions.tsv).",
    )
    args = parser.parse_args(argv)

    if not args.src.exists():
        print(
            f"[ok] {args.src} does not exist; nothing to migrate.",
            file=sys.stderr,
        )
        return 0

    try:
        n_exp, n_sess, n_unk = split(
            args.src, args.experiments_out, args.sessions_out
        )
    except OSError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    print(
        f"[ok] migrated {n_exp} experiments rows, {n_sess} sessions rows, "
        f"{n_unk} unknown",
        file=sys.stderr,
    )
    print(
        f"      → {args.experiments_out}\n      → {args.sessions_out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
