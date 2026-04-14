"""docker-wrap — agent-callable wrapper around docker / docker compose.

Subcommands:
- ps [--all]
- images
- build <path> [--tag T]
- run <image> [--env KEY=VAL ...]
- compose-up [--file F] [--detach]
- compose-down [--file F]
- logs <container> [--tail N]
"""

from __future__ import annotations

import json
from typing import Any

import click

from . import SoupWrapperError, emit_error, emit_ok, run_cmd


def _docker(args: list[str], *, check: bool = True) -> str:
    """Invoke ``docker`` with args; return stdout."""
    res = run_cmd(["docker", *args], check=check)
    return res.stdout


def _parse_jsonlines(raw: str) -> list[dict[str, Any]]:
    """Parse ``docker ... --format '{{json .}}'`` NDJSON output."""
    items: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


@click.group(name="docker-wrap", help="JSON-first docker wrapper for soup agents.")
def cli() -> None:
    """Root command group."""


@cli.command("ps")
@click.option("--all", "show_all", is_flag=True, help="Include stopped containers.")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def ps_cmd(show_all: bool, json_mode: bool) -> None:
    """List containers."""
    try:
        args = ["ps", "--format", "{{json .}}"]
        if show_all:
            args.append("-a")
        raw = _docker(args)
        containers = _parse_jsonlines(raw)
        emit_ok(
            {"status": "ok", "count": len(containers), "containers": containers},
            json_mode=json_mode,
        )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("images")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def images_cmd(json_mode: bool) -> None:
    """List local images."""
    try:
        raw = _docker(["images", "--format", "{{json .}}"])
        images = _parse_jsonlines(raw)
        emit_ok({"status": "ok", "count": len(images), "images": images}, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("build")
@click.argument("path")
@click.option("--tag", "-t", default=None, help="Image tag.")
@click.option("--file", "-f", "dockerfile", default=None, help="Path to Dockerfile.")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def build_cmd(path: str, tag: str | None, dockerfile: str | None, json_mode: bool) -> None:
    """Build an image from ``path``."""
    try:
        args = ["build", path]
        if tag:
            args.extend(["-t", tag])
        if dockerfile:
            args.extend(["-f", dockerfile])
        res = run_cmd(["docker", *args], check=False, timeout=1800.0)
        payload: dict[str, Any] = {
            "status": "ok" if res.returncode == 0 else "error",
            "tag": tag,
            "path": path,
            "returncode": res.returncode,
            "stdout_tail": "\n".join(res.stdout.splitlines()[-30:]),
            "stderr_tail": "\n".join(res.stderr.splitlines()[-30:]),
        }
        if res.returncode != 0:
            emit_error(
                payload["stderr_tail"] or f"build failed: {tag or path}",
                res.returncode,
                json_mode=json_mode,
            )
        else:
            emit_ok(payload, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("run")
@click.argument("image")
@click.option("--env", "-e", "env_kv", multiple=True, help="KEY=VAL env var.")
@click.option("--name", default=None)
@click.option("--detach", "-d", is_flag=True)
@click.option("--rm", "auto_rm", is_flag=True, default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
@click.argument("extra_args", nargs=-1)
def run_cmd_cmd(
    image: str,
    env_kv: tuple[str, ...],
    name: str | None,
    detach: bool,
    auto_rm: bool,
    json_mode: bool,
    extra_args: tuple[str, ...],
) -> None:
    """Run a container (foreground by default; --detach for background)."""
    try:
        args = ["run"]
        if auto_rm and not detach:
            args.append("--rm")
        if detach:
            args.append("-d")
        if name:
            args.extend(["--name", name])
        for kv in env_kv:
            if "=" not in kv:
                emit_error(f"malformed --env '{kv}' (expected KEY=VAL)", 2, json_mode=json_mode)
            args.extend(["-e", kv])
        args.append(image)
        args.extend(list(extra_args))
        res = run_cmd(["docker", *args], check=False, timeout=600.0)
        payload = {
            "status": "ok" if res.returncode == 0 else "error",
            "image": image,
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
        if res.returncode != 0:
            emit_error(res.stderr.strip() or "docker run failed", res.returncode, json_mode=json_mode)
        else:
            emit_ok(payload, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("compose-up")
@click.option("--file", "-f", "compose_file", default=None)
@click.option("--detach/--no-detach", default=True, show_default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def compose_up_cmd(compose_file: str | None, detach: bool, json_mode: bool) -> None:
    """Run ``docker compose up``."""
    try:
        args = ["compose"]
        if compose_file:
            args.extend(["-f", compose_file])
        args.append("up")
        if detach:
            args.append("-d")
        res = run_cmd(["docker", *args], check=False, timeout=900.0)
        if res.returncode != 0:
            emit_error(
                res.stderr.strip() or "compose up failed", res.returncode, json_mode=json_mode
            )
        else:
            emit_ok(
                {"status": "ok", "detached": detach, "output": res.stdout},
                json_mode=json_mode,
            )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("compose-down")
@click.option("--file", "-f", "compose_file", default=None)
@click.option("--volumes", "-v", is_flag=True, help="Remove named volumes.")
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def compose_down_cmd(compose_file: str | None, volumes: bool, json_mode: bool) -> None:
    """Run ``docker compose down``."""
    try:
        args = ["compose"]
        if compose_file:
            args.extend(["-f", compose_file])
        args.append("down")
        if volumes:
            args.append("-v")
        res = run_cmd(["docker", *args], check=False, timeout=300.0)
        if res.returncode != 0:
            emit_error(
                res.stderr.strip() or "compose down failed", res.returncode, json_mode=json_mode
            )
        else:
            emit_ok({"status": "ok", "output": res.stdout}, json_mode=json_mode)
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


@cli.command("logs")
@click.argument("container")
@click.option("--tail", default=100, type=int, show_default=True)
@click.option("--json/--no-json", "json_mode", default=True, show_default=True)
def logs_cmd(container: str, tail: int, json_mode: bool) -> None:
    """Tail container logs."""
    try:
        res = run_cmd(
            ["docker", "logs", "--tail", str(tail), container],
            check=False,
            timeout=60.0,
        )
        if res.returncode != 0:
            emit_error(
                res.stderr.strip() or f"logs failed for {container}",
                res.returncode,
                json_mode=json_mode,
            )
        else:
            emit_ok(
                {
                    "status": "ok",
                    "container": container,
                    "tail": tail,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                },
                json_mode=json_mode,
            )
    except SoupWrapperError as e:
        emit_error(e.message, e.code, json_mode=json_mode)


if __name__ == "__main__":  # pragma: no cover
    cli()
