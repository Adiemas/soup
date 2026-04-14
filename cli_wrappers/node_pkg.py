"""node-wrap — agent-callable wrapper around npm / pnpm / yarn.

Auto-detects the package manager from the lockfile in the target directory:

- ``pnpm-lock.yaml`` -> pnpm
- ``yarn.lock``      -> yarn
- ``package-lock.json`` (or nothing) -> npm

Subcommands:
- install [--frozen]
- run <script> [extra args]
- test
- build
- audit
- ci     -- orchestrated install --frozen && test && build

All commands emit JSON by default, matching the ``{status, data}``
contract of the other soup wrappers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from . import SoupWrapperError, emit_error, emit_ok, run_cmd


# Lockfile -> package manager. Order matters: the first match wins, so
# pnpm beats yarn beats npm when multiple lockfiles exist.
_LOCKFILES: tuple[tuple[str, str], ...] = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
)


def detect_pm(cwd: str | Path | None = None) -> str:
    """Detect the package manager from lockfiles in ``cwd``.

    Returns one of ``"npm" | "pnpm" | "yarn"``. Defaults to ``"npm"``
    when no lockfile is present.
    """
    root = Path(cwd) if cwd else Path.cwd()
    for fname, pm in _LOCKFILES:
        if (root / fname).exists():
            return pm
    return "npm"


def _install_argv(pm: str, frozen: bool) -> list[str]:
    """Build the package-manager-specific install command."""
    if pm == "pnpm":
        base = ["pnpm", "install"]
        if frozen:
            base.append("--frozen-lockfile")
        return base
    if pm == "yarn":
        base = ["yarn", "install"]
        if frozen:
            base.append("--frozen-lockfile")
        return base
    # npm
    if frozen:
        return ["npm", "ci"]
    return ["npm", "install"]


def _run_argv(pm: str, script: str, extra: tuple[str, ...]) -> list[str]:
    """Build ``<pm> run <script> -- [extra...]`` for each PM."""
    if pm == "pnpm":
        argv = ["pnpm", "run", script]
    elif pm == "yarn":
        argv = ["yarn", "run", script]
    else:
        argv = ["npm", "run", script]
    if extra:
        # npm/yarn/pnpm all accept ``--`` as a flag-passthrough sentinel.
        argv.append("--")
        argv.extend(extra)
    return argv


def _audit_argv(pm: str) -> list[str]:
    """Build ``<pm> audit --json`` (best-effort; yarn's shape differs)."""
    if pm == "pnpm":
        return ["pnpm", "audit", "--json"]
    if pm == "yarn":
        # classic yarn: ``yarn audit --json`` is NDJSON;
        # berry: ``yarn npm audit --json`` is a single JSON doc.
        return ["yarn", "audit", "--json"]
    return ["npm", "audit", "--json"]


def _run(argv: list[str], *, cwd: str | None, timeout: float = 1800.0) -> tuple[int, str, str]:
    """Invoke a subprocess; return (returncode, stdout, stderr)."""
    res = run_cmd(argv, cwd=cwd, check=False, timeout=timeout)
    return res.returncode, res.stdout, res.stderr


@click.group(name="node-wrap", help="JSON-first npm/pnpm/yarn wrapper for soup agents.")
def cli() -> None:
    """Root command group."""


@cli.command("detect")
@click.option("--cwd", default=None, help="Directory to inspect (defaults to current).")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def detect_cmd(cwd: str | None, json_mode: bool) -> None:
    """Report the detected package manager and lockfile for ``cwd``."""
    try:
        root = Path(cwd) if cwd else Path.cwd()
        pm = detect_pm(root)
        lockfile: str | None = None
        for fname, pm_name in _LOCKFILES:
            if (root / fname).exists():
                lockfile = fname
                if pm_name == pm:
                    break
        emit_ok(
            {
                "status": "ok",
                "package_manager": pm,
                "lockfile": lockfile,
                "cwd": str(root),
            },
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("install")
@click.option("--frozen/--no-frozen", "frozen", default=True, show_default=True,
              help="Fail if lockfile is out of sync (CI-safe). --no-frozen for dev.")
@click.option("--cwd", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def install_cmd(frozen: bool, cwd: str | None, json_mode: bool) -> None:
    """Install deps. Maps to ``npm ci`` / ``pnpm install --frozen-lockfile`` / ``yarn install --frozen-lockfile`` when ``--frozen``."""
    try:
        pm = detect_pm(cwd)
        argv = _install_argv(pm, frozen)
        rc, out, err = _run(argv, cwd=cwd)
        tail_out = "\n".join(out.splitlines()[-40:])
        tail_err = "\n".join(err.splitlines()[-20:])
        if rc != 0:
            emit_error(
                tail_err or tail_out or f"{pm} install failed",
                code=rc,
                json_mode=json_mode,
            )
            return
        emit_ok(
            {
                "status": "ok",
                "package_manager": pm,
                "frozen": frozen,
                "argv": argv,
                "stdout_tail": tail_out,
            },
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("run")
@click.argument("script")
@click.argument("extra", nargs=-1)
@click.option("--cwd", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def run_cmd_cli(script: str, extra: tuple[str, ...], cwd: str | None, json_mode: bool) -> None:
    """Run an npm script. Auto-prefixes ``<pm> run`` for the detected PM."""
    try:
        pm = detect_pm(cwd)
        argv = _run_argv(pm, script, extra)
        rc, out, err = _run(argv, cwd=cwd)
        tail_out = "\n".join(out.splitlines()[-60:])
        tail_err = "\n".join(err.splitlines()[-30:])
        if rc != 0:
            emit_error(
                tail_err or tail_out or f"{pm} run {script} failed",
                code=rc,
                json_mode=json_mode,
            )
            return
        emit_ok(
            {
                "status": "ok",
                "package_manager": pm,
                "script": script,
                "argv": argv,
                "stdout_tail": tail_out,
            },
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("test")
@click.option("--cwd", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def test_cmd(cwd: str | None, json_mode: bool) -> None:
    """Shortcut for ``<pm> run test``."""
    try:
        pm = detect_pm(cwd)
        argv = _run_argv(pm, "test", ())
        rc, out, err = _run(argv, cwd=cwd)
        tail_out = "\n".join(out.splitlines()[-60:])
        tail_err = "\n".join(err.splitlines()[-30:])
        if rc != 0:
            emit_error(
                tail_err or tail_out or "tests failed",
                code=rc,
                json_mode=json_mode,
            )
            return
        emit_ok(
            {
                "status": "ok",
                "package_manager": pm,
                "argv": argv,
                "stdout_tail": tail_out,
            },
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("build")
@click.option("--cwd", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def build_cmd(cwd: str | None, json_mode: bool) -> None:
    """Shortcut for ``<pm> run build``."""
    try:
        pm = detect_pm(cwd)
        argv = _run_argv(pm, "build", ())
        rc, out, err = _run(argv, cwd=cwd)
        tail_out = "\n".join(out.splitlines()[-60:])
        tail_err = "\n".join(err.splitlines()[-30:])
        if rc != 0:
            emit_error(
                tail_err or tail_out or "build failed",
                code=rc,
                json_mode=json_mode,
            )
            return
        emit_ok(
            {
                "status": "ok",
                "package_manager": pm,
                "argv": argv,
                "stdout_tail": tail_out,
            },
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("audit")
@click.option("--cwd", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def audit_cmd(cwd: str | None, json_mode: bool) -> None:
    """Run ``<pm> audit --json`` and parse the report. Non-zero exits are still parsed."""
    try:
        pm = detect_pm(cwd)
        argv = _audit_argv(pm)
        rc, out, err = _run(argv, cwd=cwd, timeout=600.0)
        # Audit output may be a single JSON doc (npm/yarn-berry) or NDJSON
        # (classic yarn, pnpm in some versions). Try both.
        parsed: Any = None
        parse_mode: str = "none"
        body = out.strip()
        if body:
            try:
                parsed = json.loads(body)
                parse_mode = "json"
            except ValueError:
                parsed = []
                for line in body.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed.append(json.loads(line))
                    except ValueError:
                        continue
                if parsed:
                    parse_mode = "ndjson"
        payload: dict[str, Any] = {
            "status": "ok" if rc == 0 else "error",
            "package_manager": pm,
            "returncode": rc,
            "parse_mode": parse_mode,
            "report": parsed,
            "stdout_tail": "\n".join(out.splitlines()[-20:]),
            "stderr_tail": "\n".join(err.splitlines()[-20:]),
        }
        if rc != 0:
            # npm/yarn/pnpm audit exit non-zero on findings; pass the payload
            # up so the caller can inspect the report.
            emit_error(
                f"{pm} audit returned {rc} (findings or error)",
                code=rc,
                json_mode=json_mode,
            )
        else:
            emit_ok(payload, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("ci")
@click.option("--cwd", default=None)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def ci_cmd(cwd: str | None, json_mode: bool) -> None:
    """Orchestrated: install --frozen && test && build. First failure wins."""
    try:
        pm = detect_pm(cwd)
        steps = [
            ("install", _install_argv(pm, frozen=True)),
            ("test", _run_argv(pm, "test", ())),
            ("build", _run_argv(pm, "build", ())),
        ]
        results: list[dict[str, Any]] = []
        for name, argv in steps:
            rc, out, err = _run(argv, cwd=cwd)
            results.append(
                {
                    "step": name,
                    "argv": argv,
                    "returncode": rc,
                    "stdout_tail": "\n".join(out.splitlines()[-20:]),
                    "stderr_tail": "\n".join(err.splitlines()[-10:]),
                }
            )
            if rc != 0:
                emit_error(
                    f"ci failed at step '{name}' ({pm}): rc={rc}",
                    code=rc,
                    json_mode=json_mode,
                )
                return
        emit_ok(
            {
                "status": "ok",
                "package_manager": pm,
                "steps": results,
            },
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


if __name__ == "__main__":  # pragma: no cover
    cli()
