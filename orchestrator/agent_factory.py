"""Spawn a fresh Claude Code subagent for one TaskStep.

Per DESIGN §4, each TaskStep runs in a fresh subagent with only the spec +
its file scope. The factory is responsible for:

1. Constructing the CLI invocation (``claude -p --agent <role> ...``).
2. Injecting ``files_allowed``, ``max_turns``, ``model`` tier, and any
   pre-computed RAG context into the prompt.
3. Capturing stderr (where hooks emit AgentLogEntry lines) and writing
   them to the session JSONL file.
4. Returning a :class:`StepResult` with status, output, duration, and log path.

The design favors a CLI subprocess over the SDK so the subagent runs in its
own process (fresh context, independent token budget). The actual binary
path is configurable via the ``SOUP_CLAUDE_BIN`` env var (default ``claude``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from schemas.agent_log import AgentLogEntry
from schemas.execution_plan import TaskStep

_LOGGER = logging.getLogger(__name__)

# Cap sizes so a pathological ``context_excerpts``/``spec_refs`` entry does
# not bloat the subagent prompt beyond workable bounds.
_EXCERPT_MAX_BYTES = 20 * 1024
_SPEC_REF_MAX_BYTES = 40 * 1024

# ``:NN-MM`` tail regex — anchored on a leading non-colon to avoid matching
# Windows drive letters (``C:\path``).
_LINE_RANGE_TAIL = re.compile(r"(?<=[^:]):(\d+)-(\d+)$")

# URI schemes that context_excerpts may carry unresolved — the
# rag-researcher is expected to materialise these upstream into local
# paths if the actual content needs to inline into the brief. When
# such a URI appears here we inject it as a ``[source:<uri>]``
# citation only, without touching disk (F5: iter-3 dogfood).
_RAG_URI_SCHEMES = re.compile(
    r"^(github|gh|ghe|ado|adowiki|ado-wi|file|https?|web)://",
    flags=re.IGNORECASE,
)

# What we inject when a ``context_excerpts`` entry is a RAG URI —
# a visible placeholder so the subagent knows a materialised copy was
# not supplied. If the snippet body is required verbatim, the
# rag-researcher should materialise to ``.soup/research/...`` and
# reference the local path instead.
_RAG_URI_PLACEHOLDER_TEXT = (
    "[source:{uri}] (RAG citation; body not materialised — "
    "rag-researcher should inline via .soup/research/ if needed)"
)

StepStatus = Literal["passed", "failed", "timed_out", "spawn_error"]

_DEFAULT_LOG_DIR = Path("logging/agent-runs")

# Baseline env keys every subagent may see. Anything not in this list or
# matching ``_DEFAULT_ENV_PREFIXES`` is stripped from the parent
# environment before spawn. Secret-bearing keys (``GITHUB_TOKEN``,
# ``ADO_PAT``, ``POSTGRES_PASSWORD``, ``ANTHROPIC_API_KEY``) are
# intentionally absent — they are only forwarded via ``TaskStep.env``
# when a step explicitly opts in.
#
# ``ANTHROPIC_API_KEY`` is the one secret in the baseline set because
# the subagent is the Claude binary itself and cannot make API calls
# without it. Agents that do not need it (e.g. a pure-local linter
# step) can drop it later; for v1 we ship the baseline with it in.
_DEFAULT_ENV_KEYS: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "USERNAME",  # Windows
        "USERPROFILE",  # Windows
        "SYSTEMROOT",  # Windows
        "COMSPEC",  # Windows
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "PWD",
        "SHELL",
        "TERM",
        "PYTHONIOENCODING",
        "PYTHONUNBUFFERED",
        "ANTHROPIC_API_KEY",
    }
)

# Any env var whose name begins with one of these prefixes is also
# forwarded by default. Prefer this over adding to the explicit set.
_DEFAULT_ENV_PREFIXES: tuple[str, ...] = (
    "LC_",
    "CLAUDE_",
    "SOUP_",
)

# Additional keys a TaskStep may whitelist via ``TaskStep.env`` — the
# wider set of credentials we are willing to forward to *specific*
# agents that declare they need them. Keys listed in ``step.env`` but
# not present here are silently ignored to avoid accidental leak via
# mis-naming.
_STEP_INJECTABLE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "ADO_PAT",
        "AZURE_DEVOPS_EXT_PAT",
        "POSTGRES_DSN",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "OPENAI_API_KEY",
    }
)


def _filter_parent_env(parent: Mapping[str, str]) -> dict[str, str]:
    """Return the subset of *parent* that is safe to forward by default.

    This is the core of the subagent env hardening (cycle-1 critical
    finding #3): we treat the parent environment as secret-bearing and
    only forward keys that match the explicit whitelist or one of the
    approved prefixes. Credential-bearing keys like ``GITHUB_TOKEN``,
    ``ADO_PAT`` and ``POSTGRES_PASSWORD`` are **never** forwarded by
    default — steps that need them declare so via
    :attr:`schemas.execution_plan.TaskStep.env`.
    """
    out: dict[str, str] = {}
    for k, v in parent.items():
        if k in _DEFAULT_ENV_KEYS:
            out[k] = v
            continue
        if any(k.startswith(p) for p in _DEFAULT_ENV_PREFIXES):
            out[k] = v
    return out


def _inject_step_env(
    base: dict[str, str],
    parent: Mapping[str, str],
    step: TaskStep,
) -> dict[str, str]:
    """Overlay step-declared env onto *base*.

    A TaskStep declares the credentials it needs by listing env-var
    names in ``step.env``. The values are pulled from *parent* (the
    operator's env) and copied onto *base*. Keys that are not in
    :data:`_STEP_INJECTABLE_ENV_KEYS` are ignored so an over-eager plan
    cannot smuggle arbitrary parent vars through. Unknown / missing
    keys are silently omitted — the spawned agent gets an absent var
    rather than a surprise one.
    """
    requested = getattr(step, "env", None) or []
    if not requested:
        return base
    for key in requested:
        if key not in _STEP_INJECTABLE_ENV_KEYS:
            continue
        val = parent.get(key)
        if val is None:
            continue
        base[key] = val
    return base


@dataclass(slots=True)
class StepResult:
    """Return value from :func:`spawn`.

    Attributes:
        step_id: The TaskStep ``id``.
        status: Terminal status of the subagent invocation.
        exit_code: Process exit code (-1 if never started).
        stdout: Captured stdout.
        stderr: Captured stderr (hook event stream).
        duration_ms: Wall-clock.
        log_path: Path to the JSONL log file written by the factory.
        session_id: Correlation id for all events from this spawn.
    """

    step_id: str
    status: StepStatus
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    log_path: Path | None = None
    session_id: str = ""
    cost_estimate: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def _build_invocation(
    step: TaskStep,
    *,
    claude_bin: str,
    plan_context: Mapping[str, Any],
    session_id: str,
) -> list[str]:
    """Construct the argv array for the subagent process.

    Exposed for testing. We favor `--agent`, `--model`, `--max-turns`,
    and `--permission-mode` flags that mirror the Claude Agent SDK/CLI.
    """
    brief = _compose_brief(step, plan_context)
    files_arg = ",".join(step.files_allowed) if step.files_allowed else ""
    argv = [
        claude_bin,
        "-p",
        brief,
        "--agent",
        step.agent,
        "--model",
        step.model,
        "--max-turns",
        str(step.max_turns),
        "--session-id",
        session_id,
    ]
    if files_arg:
        argv.extend(["--files-allowed", files_arg])
    if step.rag_queries:
        argv.extend(["--rag-queries", json.dumps(step.rag_queries)])
    return argv


def _compose_brief(step: TaskStep, plan_context: Mapping[str, Any]) -> str:
    """Combine the step prompt with plan-level context into the final brief.

    If ``step.context_excerpts`` or ``step.spec_refs`` are present they are
    resolved against the current working directory (repo root) and
    appended under a ``## Context excerpts (verbatim)`` section. Resolution
    failures log a warning and skip the offending entry — the subagent
    gets whatever context was resolvable rather than failing the spawn.
    """
    header_lines = [
        f"# Task {step.id}",
        f"Agent role: {step.agent}",
        f"Model tier: {step.model}",
        f"Max turns: {step.max_turns}",
        f"Files allowed: {step.files_allowed or 'UNRESTRICTED (discouraged)'}",
        f"Verify cmd: {step.verify_cmd}",
    ]
    if "goal" in plan_context:
        header_lines.append(f"Plan goal: {plan_context['goal']}")
    if "constitution_ref" in plan_context:
        header_lines.append(
            f"Constitution: {plan_context['constitution_ref']}"
        )
    header = "\n".join(header_lines)
    body = f"{header}\n\n---\n\n{step.prompt}"
    excerpts_block = _resolve_context_excerpts(step)
    if excerpts_block:
        body = f"{body}\n\n---\n\n{excerpts_block}"
    return body


def _resolve_context_excerpts(step: TaskStep) -> str:
    """Resolve ``context_excerpts`` + ``spec_refs`` into a markdown block.

    Returns an empty string when both lists are empty OR when every entry
    failed to resolve. Individual failures are logged via ``WARNING`` and
    skipped so a missing file never blocks a spawn.
    """
    rendered: list[str] = []
    for entry in step.context_excerpts:
        text, label = _load_excerpt(entry, cap_bytes=_EXCERPT_MAX_BYTES)
        if text is None:
            continue
        rendered.append(f"### {label}\n\n```\n{text}\n```\n")
    for entry in step.spec_refs:
        text, label = _load_spec_ref(entry, cap_bytes=_SPEC_REF_MAX_BYTES)
        if text is None:
            continue
        rendered.append(f"### spec: {label}\n\n```\n{text}\n```\n")
    if not rendered:
        return ""
    return "## Context excerpts (verbatim)\n\n" + "\n".join(rendered)


def _load_excerpt(
    entry: str, *, cap_bytes: int
) -> tuple[str | None, str]:
    """Read a ``context_excerpts`` entry into text + label.

    Returns ``(None, entry)`` on failure so the caller can log + skip.
    Supports four forms:
      - ``<scheme>://...`` URI (``github://``, ``ado://``, ``ado-wi://``,
        ``file://``, ``http(s)://``, ``web://``) - injected as a
        ``[source:<uri>]`` citation WITHOUT reading disk. The
        rag-researcher materialises the snippet upstream; if you need
        the body inlined, point the excerpt at the materialised local
        path instead.
      - ``path#anchor`` - section under a heading matching ``anchor``.
      - ``path:line_from-line_to`` - 1-based inclusive line range.
      - ``path`` - whole file, capped at ``cap_bytes``.
    """
    raw = entry.strip()
    if not raw:
        return None, entry
    if _RAG_URI_SCHEMES.match(raw):
        # F5: iter-3 dogfood — RAG URI schemes flow through as citation
        # tags without disk I/O. Caller materialises upstream if needed.
        return _RAG_URI_PLACEHOLDER_TEXT.format(uri=raw), f"source:{raw}"
    if "#" in raw:
        path_part, anchor = raw.split("#", 1)
        path_obj = _safe_relative_path(path_part)
        if path_obj is None:
            _LOGGER.warning(
                "context_excerpts: refusing absolute path %r", entry
            )
            return None, entry
        if not path_obj.exists():
            _LOGGER.warning(
                "context_excerpts: %s not found; skipping", path_obj
            )
            return None, entry
        text = path_obj.read_text(encoding="utf-8", errors="replace")
        section = _extract_markdown_section(text, anchor)
        if section is None:
            _LOGGER.warning(
                "context_excerpts: anchor %r not found in %s; skipping",
                anchor,
                path_obj,
            )
            return None, entry
        return _cap_text(section, cap_bytes), raw

    m = _LINE_RANGE_TAIL.search(raw)
    if m is not None:
        path_part = raw[: m.start()]
        line_from = int(m.group(1))
        line_to = int(m.group(2))
        path_obj = _safe_relative_path(path_part)
        if path_obj is None:
            _LOGGER.warning(
                "context_excerpts: refusing absolute path %r", entry
            )
            return None, entry
        if not path_obj.exists():
            _LOGGER.warning(
                "context_excerpts: %s not found; skipping", path_obj
            )
            return None, entry
        text = path_obj.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if line_from < 1 or line_to < line_from:
            _LOGGER.warning(
                "context_excerpts: bad line range %r; skipping", entry
            )
            return None, entry
        slice_ = "\n".join(lines[line_from - 1 : line_to])
        return _cap_text(slice_, cap_bytes), raw

    path_obj = _safe_relative_path(raw)
    if path_obj is None:
        _LOGGER.warning("context_excerpts: refusing absolute path %r", entry)
        return None, entry
    if not path_obj.exists():
        _LOGGER.warning(
            "context_excerpts: %s not found; skipping", path_obj
        )
        return None, entry
    text = path_obj.read_text(encoding="utf-8", errors="replace")
    return _cap_text(text, cap_bytes), raw


def _load_spec_ref(
    entry: str, *, cap_bytes: int
) -> tuple[str | None, str]:
    """Read a ``spec_refs`` entry; whole file, capped at ``cap_bytes``.

    ``<scheme>://`` URIs (``github://``, ``ado-wi://``, etc.) are
    injected as ``[source:<uri>]`` citations instead of being read off
    disk — mirrors the F5 rule in :func:`_load_excerpt`.
    """
    raw = entry.strip()
    if not raw:
        return None, entry
    if _RAG_URI_SCHEMES.match(raw):
        return _RAG_URI_PLACEHOLDER_TEXT.format(uri=raw), f"source:{raw}"
    path_obj = _safe_relative_path(raw)
    if path_obj is None:
        _LOGGER.warning("spec_refs: refusing absolute path %r", entry)
        return None, entry
    if isinstance(path_obj, str):
        # URI returned verbatim (see _safe_relative_path). spec_refs don't
        # reach here because URIs are handled above, but be explicit.
        return None, entry
    if not path_obj.exists():
        _LOGGER.warning("spec_refs: %s not found; skipping", path_obj)
        return None, entry
    text = path_obj.read_text(encoding="utf-8", errors="replace")
    return _cap_text(text, cap_bytes), raw


def _safe_relative_path(raw: str) -> Path | str | None:
    """Return a safe path or URI for *raw*; else ``None``.

    Behaviour (F5: iter-3 dogfood):
      - RAG URI schemes (``github://``, ``ado://``, ``ado-wi://``,
        ``file://``, ``http(s)://``, ``web://``) are returned as-is
        (str) — they are not filesystem paths and must not be resolved.
      - Otherwise enforce relative-path safety: reject absolute paths,
        Windows drive letters, UNC paths. Return a ``Path`` for a
        repo-relative reference.

    The return type is a union: callers must check ``isinstance(result,
    Path)`` before doing filesystem I/O. Tests rely on both branches.
    """
    if _RAG_URI_SCHEMES.match(raw):
        return raw
    p = Path(raw)
    if p.is_absolute():
        return None
    if len(raw) >= 2 and raw[1] == ":":
        return None  # Windows drive letter
    if raw.startswith("\\\\"):
        return None  # UNC path
    return p


def _extract_markdown_section(text: str, anchor: str) -> str | None:
    """Return the body of the markdown section whose heading matches *anchor*.

    Matching strategy (try in order):
      1. Exact slug match (``lowercase + spaces->hyphens``).
      2. Case-insensitive substring match on the heading text.

    The section starts at the matching heading line and ends at the next
    heading of the same or shallower depth.
    """
    lines = text.splitlines()
    heading_re = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
    target_slug = _slugify(anchor)
    match_idx: int | None = None
    match_depth = 0
    for i, line in enumerate(lines):
        hm = heading_re.match(line)
        if hm is None:
            continue
        depth = len(hm.group(1))
        title = hm.group(2).strip()
        if _slugify(title) == target_slug or anchor.lower() in title.lower():
            match_idx = i
            match_depth = depth
            break
    if match_idx is None:
        return None
    end_idx = len(lines)
    for j in range(match_idx + 1, len(lines)):
        hm2 = heading_re.match(lines[j])
        if hm2 is not None and len(hm2.group(1)) <= match_depth:
            end_idx = j
            break
    return "\n".join(lines[match_idx:end_idx]).rstrip() + "\n"


def _slugify(text: str) -> str:
    """Lowercase ascii slug used for markdown-anchor lookups."""
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


def _cap_text(text: str, cap_bytes: int) -> str:
    """Truncate *text* to ``cap_bytes``; append a warning marker on cut."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= cap_bytes:
        return text
    cut = encoded[:cap_bytes].decode("utf-8", errors="ignore")
    return (
        cut
        + f"\n\n[... truncated at {cap_bytes} bytes (was {len(encoded)}) ...]\n"
    )


def _resolve_claude_bin() -> str:
    """Pick the Claude Code binary: env override → PATH ``claude`` → error marker."""
    override = os.environ.get("SOUP_CLAUDE_BIN")
    if override:
        return override
    found = shutil.which("claude")
    return found or "claude"


async def spawn(
    step: TaskStep,
    plan_context: Mapping[str, Any] | None = None,
    *,
    log_dir: str | Path = _DEFAULT_LOG_DIR,
    timeout_sec: float | None = None,
    env: Mapping[str, str] | None = None,
    claude_bin: str | None = None,
    parent_session_id: str | None = None,
    root_run_id: str | None = None,
    wave_idx: int | None = None,
) -> StepResult:
    """Run one TaskStep as a fresh Claude Code subagent.

    Args:
        step: The TaskStep to execute.
        plan_context: Plan-level attributes forwarded to the brief
            (``goal``, ``constitution_ref``, etc.).
        log_dir: Directory for session JSONL logs.
        timeout_sec: Hard wall-clock cap for the subagent process.
        env: Extra environment overrides (merged onto current env).
        claude_bin: Override the CLI path; normally auto-resolved.
        parent_session_id: Calling agent's session id (wave-tree
            threading; iter-3 ε1). Exported as
            ``SOUP_PARENT_SESSION_ID`` and stamped on every JSONL line.
        root_run_id: Orchestrator-level run id this spawn belongs to.
            Exported as ``SOUP_ROOT_RUN_ID``.
        wave_idx: 0-based wave index in the parent ExecutionPlan.
            Exported as ``SOUP_WAVE_IDX``.

    Returns:
        StepResult with status, exit code, captured I/O, and log path.
    """
    plan_ctx = dict(plan_context or {})
    session_id = f"{step.agent}-{uuid.uuid4().hex[:10]}"
    log_dir_p = Path(log_dir)
    log_dir_p.mkdir(parents=True, exist_ok=True)
    log_path = log_dir_p / f"session-{session_id}.jsonl"

    bin_path = claude_bin or _resolve_claude_bin()
    argv = _build_invocation(
        step,
        claude_bin=bin_path,
        plan_context=plan_ctx,
        session_id=session_id,
    )
    # Build the child env via an explicit whitelist. We do NOT spread
    # os.environ directly — that previously leaked GITHUB_TOKEN,
    # ADO_PAT, POSTGRES_PASSWORD, etc. into every subagent, regardless
    # of whether the step needed them. Secrets flow in only when the
    # step's ``env`` field names them. See _filter_parent_env and
    # _inject_step_env above.
    full_env = _filter_parent_env(os.environ)
    full_env = _inject_step_env(full_env, os.environ, step)
    # Export the step's files_allowed globs so the ``.githooks/pre-commit``
    # scanner can enforce scope at commit time (F4). Colon-separated —
    # same dialect as ``$PATH`` so engineers can read it via ``echo``.
    # If ``files_allowed`` is empty, we deliberately do not set the var,
    # which makes the hook a no-op (and lets bash-only steps that do not
    # write repo files pass through untouched).
    if step.files_allowed:
        full_env["SOUP_FILES_ALLOWED"] = ":".join(step.files_allowed)
    # iter-3 ε1: thread the wave-tree identifiers into the subagent env.
    # The PostToolUse hook reads these and stamps every JSONL line so
    # ``soup logs tree`` can reconstruct the dispatch tree from the
    # logs alone. Always export ``SOUP_STEP_ID`` so even orphan spawns
    # carry the originating step.
    full_env["SOUP_STEP_ID"] = step.id
    if parent_session_id:
        full_env["SOUP_PARENT_SESSION_ID"] = parent_session_id
    if root_run_id:
        full_env["SOUP_ROOT_RUN_ID"] = root_run_id
    if wave_idx is not None:
        full_env["SOUP_WAVE_IDX"] = str(wave_idx)
    if env:
        # Caller-side explicit overrides (tests, nested orchestrators).
        # These are trusted — whoever constructed ``env`` already made
        # the forwarding decision.
        for k, v in env.items():
            full_env[k] = v

    t0 = time.monotonic()
    # Record a "started" log line before spawning so crashes are still traceable.
    _append_log(
        log_path,
        AgentLogEntry(
            session_id=session_id,
            agent=step.agent,
            action="Spawn",
            input_summary=f"step={step.id} argv={shlex.join(argv)[:400]}",
            status="started",
            parent_session_id=parent_session_id,
            root_run_id=root_run_id,
            wave_idx=wave_idx,
            step_id=step.id,
        ),
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
        )
    except FileNotFoundError:
        dur_ms = int((time.monotonic() - t0) * 1000)
        _append_log(
            log_path,
            AgentLogEntry(
                session_id=session_id,
                agent=step.agent,
                action="Spawn",
                output_summary=f"binary not found: {bin_path}",
                duration_ms=dur_ms,
                status="error",
                parent_session_id=parent_session_id,
                root_run_id=root_run_id,
                wave_idx=wave_idx,
                step_id=step.id,
            ),
        )
        return StepResult(
            step_id=step.id,
            status="spawn_error",
            exit_code=-1,
            stderr=f"claude binary not found: {bin_path}",
            duration_ms=dur_ms,
            log_path=log_path,
            session_id=session_id,
        )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_sec
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        dur_ms = int((time.monotonic() - t0) * 1000)
        _append_log(
            log_path,
            AgentLogEntry(
                session_id=session_id,
                agent=step.agent,
                action="Spawn",
                output_summary=f"timed out after {timeout_sec}s",
                duration_ms=dur_ms,
                status="timeout",
                parent_session_id=parent_session_id,
                root_run_id=root_run_id,
                wave_idx=wave_idx,
                step_id=step.id,
            ),
        )
        return StepResult(
            step_id=step.id,
            status="timed_out",
            exit_code=-1,
            duration_ms=dur_ms,
            log_path=log_path,
            session_id=session_id,
        )

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    dur_ms = int((time.monotonic() - t0) * 1000)

    # Forward every hook-emitted JSON event on stderr into our session log.
    _forward_stderr_events(stderr, log_path, session_id, step.agent)

    status: StepStatus = "passed" if proc.returncode == 0 else "failed"
    _append_log(
        log_path,
        AgentLogEntry(
            session_id=session_id,
            agent=step.agent,
            action="Spawn",
            output_summary=f"exit={proc.returncode} stdout_len={len(stdout)}",
            duration_ms=dur_ms,
            status="success" if status == "passed" else "error",
            parent_session_id=parent_session_id,
            root_run_id=root_run_id,
            wave_idx=wave_idx,
            step_id=step.id,
        ),
    )
    return StepResult(
        step_id=step.id,
        status=status,
        exit_code=proc.returncode or 0,
        stdout=stdout,
        stderr=stderr,
        duration_ms=dur_ms,
        log_path=log_path,
        session_id=session_id,
    )


def _append_log(path: Path, entry: AgentLogEntry) -> None:
    """Append one AgentLogEntry as a JSONL line."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.to_jsonl())


def _forward_stderr_events(
    stderr: str,
    log_path: Path,
    session_id: str,
    agent: str,
) -> None:
    """Parse AgentLogEntry JSON lines from stderr and append to session log.

    Hooks are expected to emit their structured events on stderr, one JSON
    object per line. Any non-JSON chatter is ignored (not swallowed silently
    — a summary marker is written so grep is still useful).
    """
    if not stderr.strip():
        return
    noise = 0
    for line in stderr.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            noise += 1
            continue
        if not isinstance(raw, dict):
            noise += 1
            continue
        raw.setdefault("session_id", session_id)
        raw.setdefault("agent", agent)
        raw.setdefault(
            "ts", datetime.now(UTC).isoformat()
        )
        try:
            entry = AgentLogEntry.model_validate(raw)
        except Exception:
            noise += 1
            continue
        _append_log(log_path, entry)
    if noise:
        _append_log(
            log_path,
            AgentLogEntry(
                session_id=session_id,
                agent=agent,
                action="stderr.noise",
                output_summary=f"{noise} non-JSON lines discarded",
                status="success",
            ),
        )


__all__ = ["StepResult", "StepStatus", "spawn"]
