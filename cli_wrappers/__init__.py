"""CLI wrappers for soup.

Each module exposes a Click command group that wraps an external CLI
(git, docker, psql, dotnet, az devops, gh) and returns JSON by default.

Contract (CLI-Anything pattern):
- Every subcommand accepts ``--json`` (default True for agent use).
- Errors are serialized as ``{"status":"error","message":"...","code":N}``.
- Success responses include ``{"status":"ok", ...}`` with structured data.
- No side-channel prints: stdout is a single JSON document (or NDJSON where noted).

Intended consumers: soup orchestrator subagents and agent tool calls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

__all__ = [
    "emit_error",
    "emit_ok",
    "run_cmd",
    "CmdResult",
]


@dataclass
class CmdResult:
    """Result of running a subprocess command."""

    returncode: int
    stdout: str
    stderr: str


def run_cmd(
    argv: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    input_bytes: bytes | None = None,
    check: bool = False,
    timeout: float | None = 300.0,
) -> CmdResult:
    """Run a subprocess and return stdout/stderr/returncode.

    No shell interpolation; ``argv`` is a list. Binary-safe via
    ``subprocess.run`` with ``capture_output=True``.
    """
    try:
        proc = subprocess.run(  # noqa: S603 — trusted argv from wrapper
            argv,
            cwd=cwd,
            env=env,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        raise SoupWrapperError(f"executable not found: {argv[0]}", code=127) from e
    except subprocess.TimeoutExpired as e:
        raise SoupWrapperError(f"timeout after {timeout}s: {' '.join(argv)}", code=124) from e

    result = CmdResult(
        returncode=proc.returncode,
        stdout=proc.stdout.decode("utf-8", errors="replace"),
        stderr=proc.stderr.decode("utf-8", errors="replace"),
    )
    if check and result.returncode != 0:
        raise SoupWrapperError(
            f"command failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}",
            code=result.returncode,
        )
    return result


class SoupWrapperError(Exception):
    """Structured wrapper error carrying an exit code."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def emit_ok(payload: dict[str, Any] | list[Any], *, json_mode: bool = True) -> None:
    """Emit a success response on stdout and return."""
    if json_mode:
        body = {"status": "ok", "data": payload} if not isinstance(payload, dict) or "status" not in payload else payload
        sys.stdout.write(json.dumps(body, default=str, ensure_ascii=False))
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        sys.stdout.write(json.dumps(payload, default=str, indent=2))
        sys.stdout.write("\n")


def emit_error(message: str, code: int = 1, *, json_mode: bool = True) -> None:
    """Emit a structured error on stdout and exit with ``code``."""
    payload = {"status": "error", "message": message, "code": code}
    if json_mode:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False))
        sys.stdout.write("\n")
    else:
        sys.stderr.write(f"error ({code}): {message}\n")
    sys.stdout.flush()
    sys.exit(code)
