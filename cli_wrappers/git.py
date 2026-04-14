"""git-wrap — agent-callable wrapper around git.

Subcommands:
- status
- diff [--staged]
- log [--limit N]
- branch-list
- worktree-add <path> <branch>
- worktree-remove <path>

All commands emit JSON by default.
"""

from __future__ import annotations

from typing import Any

import click

from . import SoupWrapperError, emit_error, emit_ok, run_cmd


def _git(args: list[str], cwd: str | None = None) -> str:
    """Run git with args, return stdout, raise on non-zero."""
    res = run_cmd(["git", *args], cwd=cwd, check=True)
    return res.stdout


def _parse_porcelain_z(raw: str) -> list[dict[str, str]]:
    """Parse ``git status --porcelain=v1 -z`` output.

    Format: ``XY<space><path>\x00`` with rename sources appended.
    """
    entries: list[dict[str, str]] = []
    tokens = raw.split("\x00")
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok:
            i += 1
            continue
        if len(tok) < 3:
            i += 1
            continue
        xy, path = tok[:2], tok[3:]
        entry: dict[str, str] = {"index": xy[0], "worktree": xy[1], "path": path}
        # Renames (R/C) consume a following orig-path token.
        if xy[0] in ("R", "C") or xy[1] in ("R", "C"):
            i += 1
            if i < len(tokens):
                entry["orig_path"] = tokens[i]
        entries.append(entry)
        i += 1
    return entries


@click.group(name="git-wrap", help="JSON-first git wrapper for soup agents.")
def cli() -> None:
    """Root command group."""


@cli.command("status")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option("--cwd", default=None, help="Run in this working directory.")
def status_cmd(json_mode: bool, cwd: str | None) -> None:
    """Structured ``git status`` (porcelain v1 -z)."""
    try:
        raw = _git(["status", "--porcelain=v1", "-z", "--branch"], cwd=cwd)
        lines = raw.split("\x00")
        branch_line = lines[0] if lines else ""
        branch: str | None = None
        ahead, behind = 0, 0
        if branch_line.startswith("## "):
            header = branch_line[3:]
            # e.g. "main...origin/main [ahead 1, behind 2]"
            branch = header.split("...")[0].split(" ")[0]
            if "ahead " in header:
                try:
                    ahead = int(header.split("ahead ")[1].split(",")[0].split("]")[0])
                except (ValueError, IndexError):
                    pass
            if "behind " in header:
                try:
                    behind = int(header.split("behind ")[1].split("]")[0])
                except (ValueError, IndexError):
                    pass
        files = _parse_porcelain_z("\x00".join(lines[1:]))
        emit_ok(
            {"status": "ok", "branch": branch, "ahead": ahead, "behind": behind, "files": files},
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("diff")
@click.option("--staged", is_flag=True, help="Diff staged changes.")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option("--cwd", default=None)
def diff_cmd(staged: bool, json_mode: bool, cwd: str | None) -> None:
    """Return ``git diff`` as JSON (files + raw patch)."""
    try:
        args = ["diff", "--no-color"]
        if staged:
            args.append("--staged")
        # Parse --numstat for a structured per-file summary.
        numstat_raw = _git([*args, "--numstat"], cwd=cwd)
        files: list[dict[str, Any]] = []
        for line in numstat_raw.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            added = 0 if parts[0] == "-" else int(parts[0])
            removed = 0 if parts[1] == "-" else int(parts[1])
            files.append({"path": parts[2], "added": added, "removed": removed})
        patch = _git(args, cwd=cwd)
        emit_ok({"status": "ok", "staged": staged, "files": files, "patch": patch}, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("log")
@click.option("--limit", "limit", default=20, show_default=True, type=int)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option("--cwd", default=None)
def log_cmd(limit: int, json_mode: bool, cwd: str | None) -> None:
    """Return recent commits as JSON list."""
    try:
        sep = "\x1f"
        rec = "\x1e"
        fmt = sep.join(["%H", "%an", "%ae", "%at", "%s"]) + rec
        raw = _git(["log", f"-n{limit}", f"--pretty=format:{fmt}"], cwd=cwd)
        commits: list[dict[str, Any]] = []
        for entry in raw.split(rec):
            if not entry.strip():
                continue
            parts = entry.lstrip("\n").split(sep)
            if len(parts) < 5:
                continue
            sha, author, email, ts, subject = parts[0], parts[1], parts[2], parts[3], parts[4]
            commits.append(
                {
                    "sha": sha,
                    "author": author,
                    "email": email,
                    "timestamp": int(ts) if ts.isdigit() else ts,
                    "subject": subject,
                }
            )
        emit_ok({"status": "ok", "count": len(commits), "commits": commits}, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("branch-list")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option("--cwd", default=None)
def branch_list_cmd(json_mode: bool, cwd: str | None) -> None:
    """List local branches with current marker."""
    try:
        raw = _git(["branch", "--list", "--no-color"], cwd=cwd)
        branches: list[dict[str, Any]] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            current = line.startswith("* ")
            name = line[2:].strip()
            branches.append({"name": name, "current": current})
        emit_ok({"status": "ok", "count": len(branches), "branches": branches}, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("worktree-add")
@click.argument("path")
@click.argument("branch")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option("--cwd", default=None)
@click.option("--new-branch", is_flag=True, help="Create branch if it doesn't exist.")
def worktree_add_cmd(
    path: str, branch: str, json_mode: bool, cwd: str | None, new_branch: bool
) -> None:
    """Add a git worktree at ``path`` for ``branch``."""
    try:
        args = ["worktree", "add"]
        if new_branch:
            args.extend(["-b", branch, path])
        else:
            args.extend([path, branch])
        raw = _git(args, cwd=cwd)
        emit_ok(
            {"status": "ok", "path": path, "branch": branch, "output": raw.strip()},
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("worktree-remove")
@click.argument("path")
@click.option("--force", is_flag=True, help="Force removal of dirty worktree.")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.option("--cwd", default=None)
def worktree_remove_cmd(path: str, force: bool, json_mode: bool, cwd: str | None) -> None:
    """Remove a git worktree."""
    try:
        args = ["worktree", "remove", path]
        if force:
            args.append("--force")
        raw = _git(args, cwd=cwd)
        emit_ok({"status": "ok", "path": path, "output": raw.strip()}, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


if __name__ == "__main__":  # pragma: no cover
    cli()
