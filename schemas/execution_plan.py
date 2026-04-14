"""Execution plan schemas — the meta-prompter -> orchestrator contract.

Per DESIGN.md §3, an ExecutionPlan is a Pydantic-validated DAG of TaskSteps.
Each step declares its agent, prompt, dependencies, verify command, and file
scope. The orchestrator honors ``depends_on`` and ``parallel`` to compute
execution waves; the validator rejects cycles, missing dependencies, and
agents not in the roster.

The :class:`TaskStep` model now also enforces the roster check at parse
time via a field validator. The roster is loaded once at module import
from ``library.yaml`` (the path declared in ``DEFAULT_LIBRARY_PATH``);
callers can rebind the active roster for tests via
:func:`set_active_roster` or by passing ``context={"roster": {...}}`` to
``model_validate``.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

ModelTier = Literal["haiku", "sonnet", "opus"]

DEFAULT_LIBRARY_PATH = Path("library.yaml")

# ``path:NN-MM`` line range suffix used by ``TaskStep.context_excerpts``.
# The leading ``:`` is anchored with a preceding non-colon char to avoid
# matching Windows drive letters (``C:\path``).
_LINE_RANGE_TAIL = re.compile(r"(?<=[^:]):\d+-\d+$")

# Active roster used by the field-level validator. Loaded once at import
# from ``DEFAULT_LIBRARY_PATH`` if the file exists; tests may override via
# :func:`set_active_roster` or by passing ``context={"roster": {...}}``
# to ``ExecutionPlan.model_validate`` / ``TaskStep.model_validate``.
_ACTIVE_ROSTER: set[str] = set()


def set_active_roster(names: set[str] | list[str] | tuple[str, ...]) -> None:
    """Replace the module-level roster used by the field validator.

    Useful for tests that build mini libraries and want
    :class:`TaskStep` to validate against them without juggling
    ``model_validate(..., context=...)``.
    """
    global _ACTIVE_ROSTER
    _ACTIVE_ROSTER = set(names)


def get_active_roster() -> set[str]:
    """Return a copy of the currently-active roster."""
    return set(_ACTIVE_ROSTER)


def _try_load_default_roster() -> None:
    global _ACTIVE_ROSTER
    try:
        if DEFAULT_LIBRARY_PATH.exists():
            _ACTIVE_ROSTER = load_agent_roster(DEFAULT_LIBRARY_PATH)
    except Exception:
        # Module import must not crash on a malformed library.yaml — the
        # explicit ``ExecutionPlanValidator.from_library`` path will surface
        # the error in production callers.
        _ACTIVE_ROSTER = set()


class TaskStep(BaseModel):
    """A single unit of work executed by a fresh subagent.

    Attributes:
        id: Short unique identifier (e.g. ``"S1"``).
        agent: Name of the subagent role; must appear in ``library.yaml``.
            Validated at parse time against the active roster (see
            :func:`set_active_roster`). Pass ``context={"roster": {...}}``
            to ``model_validate`` to override per-call.
        prompt: Full natural-language brief handed to the subagent.
        depends_on: IDs of other steps that must complete before this one.
        parallel: If True, the step may run concurrently with peers in a wave.
        model: Claude model tier to use for this step.
        verify_cmd: Bash command whose exit code 0 indicates success.
            The orchestrator splits this via :func:`shlex.split` and
            rejects commands whose argv[0] is not on the verify
            allowlist (``pytest``, ``dotnet``, ``just``, etc.). No
            shell metacharacters are honoured. A leading ``! `` prefix
            inverts the exit code (TDD RED-phase; see PATTERNS §0b).
        verify_timeout_sec: Per-step wall-clock cap (seconds) on the
            verify subprocess. Bounded to 1..600 to keep pathological
            plans from wedging the orchestrator; the orchestrator's
            global ``verify_timeout_sec`` still caps this.
        files_allowed: Glob patterns limiting which files the subagent may edit.
        max_turns: Hard cap on subagent tool-use turns.
        rag_queries: Queries run against the RAG pipeline before subagent spawn.
        env: Names of environment variables the spawned subagent needs.
            Only keys in the agent-factory injectable set
            (``GITHUB_TOKEN``, ``ADO_PAT``, ``POSTGRES_*``,
            ``OPENAI_API_KEY``, etc.) are honored; anything else is
            silently dropped. Default: empty. Steps that do not need
            credentials must leave this blank — the framework does
            **not** inherit the parent env indiscriminately (cycle-1
            critical finding #3).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., min_length=1, max_length=32)
    agent: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    parallel: bool = False
    model: ModelTier = "sonnet"
    verify_cmd: str = Field(..., min_length=1)
    verify_timeout_sec: int = Field(default=60, ge=1, le=600)
    files_allowed: list[str] = Field(default_factory=list)
    max_turns: int = Field(default=10, ge=1, le=50)
    rag_queries: list[str] = Field(default_factory=list)
    env: list[str] = Field(default_factory=list)
    context_excerpts: list[str] = Field(
        default_factory=list,
        description=(
            "Paths with optional anchors (e.g. 'specs/combat.md#phase-1' or "
            "'src/api/auth.py:45-89') to inject verbatim into this step's "
            "prompt. Lets project-specific domain knowledge travel with fresh "
            "subagent context without bloating the shared roster prompt."
        ),
    )
    spec_refs: list[str] = Field(
        default_factory=list,
        description=(
            "Spec paths this step implements (e.g. "
            "'specs/prompt-library-2026-04-14.md'). Loaded whole."
        ),
    )

    @field_validator("agent")
    @classmethod
    def _agent_in_roster(cls, v: str, info: ValidationInfo) -> str:
        """Reject agent names not present in the active roster.

        The roster comes from (in priority order):
            1. ``info.context["roster"]`` if the caller passed one.
            2. The module-level ``_ACTIVE_ROSTER`` (loaded from
               ``library.yaml`` at import).

        If neither yields a non-empty roster (e.g. ``library.yaml`` was
        not present at import and no context was passed), the field
        validator skips the membership check and lets
        :class:`ExecutionPlanValidator` enforce it later. This keeps unit
        tests that build ``TaskStep`` objects in isolation working.
        """
        ctx = info.context if isinstance(info.context, dict) else None
        roster: set[str] = set()
        if ctx and isinstance(ctx.get("roster"), (set, list, tuple)):
            roster = set(ctx["roster"])
        if not roster:
            roster = _ACTIVE_ROSTER
        if not roster:
            return v  # roster unknown — defer to ExecutionPlanValidator
        if v not in roster:
            raise ValueError(
                f"agent {v!r} is not in the roster "
                f"({sorted(roster)[:8]}{'...' if len(roster) > 8 else ''})"
            )
        return v

    @field_validator("depends_on")
    @classmethod
    def _no_self_dep(cls, v: list[str], info: Any) -> list[str]:
        step_id = info.data.get("id")
        if step_id is not None and step_id in v:
            raise ValueError(f"step {step_id!r} cannot depend on itself")
        return v

    @field_validator("context_excerpts", "spec_refs")
    @classmethod
    def _relative_paths_only(cls, v: list[str], info: Any) -> list[str]:
        """Reject absolute paths on ``context_excerpts`` / ``spec_refs``.

        Paths feed ``agent_factory.spawn`` which resolves them relative to
        the project root; absolute paths in a plan are a portability trap
        (encoded operator filesystem) and a mild exfiltration surface
        (``/etc/passwd`` would otherwise resolve). The ``path#anchor`` and
        ``path:line_from-line_to`` suffixes are tolerated — we parse the
        path portion and only check its absolute-ness.
        """
        for entry in v:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError(
                    f"{info.field_name} entries must be non-empty strings"
                )
            # Strip an optional ``#anchor`` or ``:lineFrom-lineTo`` suffix
            # before checking the path shape.
            path_part = entry.split("#", 1)[0]
            # ``:`` can legitimately appear in Windows drive letters
            # ("C:\\..."); only treat a trailing ``:NN-MM`` as a line range.
            m = _LINE_RANGE_TAIL.search(path_part)
            if m is not None:
                path_part = path_part[: m.start()]
            p = Path(path_part)
            if p.is_absolute() or (
                len(path_part) >= 2 and path_part[1] == ":"
            ):
                raise ValueError(
                    f"{info.field_name}: path {entry!r} must be relative "
                    f"(absolute paths are rejected for portability)"
                )
        return v


class ExecutionPlan(BaseModel):
    """A DAG of TaskSteps produced by the meta-prompter.

    Attributes:
        goal: Natural-language statement of what the plan delivers.
        constitution_ref: Path (relative or absolute) to the CONSTITUTION.md
            snapshot that governs this run.
        steps: Ordered list of steps (order is informational; the orchestrator
            uses ``depends_on`` to compute waves).
        budget_sec: Hard wall-clock cap in seconds; orchestrator aborts on
            exceed.
        worktree: If True, run each step inside an isolated git worktree.
        regression_baseline_cmd: Optional brownfield baseline-capture command
            (see ``.claude/skills/brownfield-baseline-capture``). When set,
            the orchestrator runs the command once before the first wave and
            once after the final wave, then diffs the two artifacts.
            Non-zero diff on tests-that-previously-passed marks the run as
            ``REGRESSION`` (surfaced to the QA gate as a high-severity
            finding; does not auto-reject). The same allowlist that applies
            to :attr:`TaskStep.verify_cmd` is enforced here.
        regression_baseline_timeout_sec: Wall-clock cap for each baseline
            capture run (pre + post separately). Bounded to 1..600.
        compliance_flags: Mirrored from the intake form; hooks may inject
            compliance rules (e.g. ``["hipaa", "soc2"]``). Purely
            informational at the schema layer — downstream pre_tool_use
            hooks are what turn these into rule injections.
    """

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=1)
    constitution_ref: str = Field(..., min_length=1)
    steps: list[TaskStep] = Field(..., min_length=1)
    budget_sec: int = Field(default=3600, ge=1)
    worktree: bool = True
    regression_baseline_cmd: str | None = Field(
        default=None,
        description=(
            "Optional bash command that captures the pre-edit baseline "
            "(e.g., 'pytest --co -q > .soup/baseline/tests.txt && "
            "curl -s http://localhost:8000/openapi.json | jq . > .soup/baseline/openapi.json'). "
            "Orchestrator runs this once before step S1 and once after the "
            "final step, then diffs. Non-zero diff on tests-that-previously-"
            "passed blocks merge. Subject to the same argv[0] allowlist as "
            "``verify_cmd`` — the LLM-authored command cannot reach outside "
            "the sanctioned toolset."
        ),
    )
    regression_baseline_timeout_sec: int = Field(default=120, ge=1, le=600)
    compliance_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Mirrored from the intake form; hooks may inject compliance "
            "rules. Values are short lowercase tags "
            "(``hipaa``, ``soc2``, ``pci-dss``). Unknown tags are allowed "
            "but ignored by default; the ``pre_tool_use`` hook is the "
            "registrar of which tags map to which rule injections."
        ),
    )

    @field_validator("steps")
    @classmethod
    def _unique_ids(cls, v: list[TaskStep]) -> list[TaskStep]:
        ids = [s.id for s in v]
        if len(set(ids)) != len(ids):
            dupes = {i for i in ids if ids.count(i) > 1}
            raise ValueError(f"duplicate step ids: {sorted(dupes)}")
        return v

    @field_validator("regression_baseline_cmd")
    @classmethod
    def _baseline_cmd_passes_allowlist(cls, v: str | None) -> str | None:
        """Require the same argv[0] allowlist as ``verify_cmd``.

        The command is LLM-authored and embedded in plan JSON; the
        orchestrator will eventually hand it to ``subprocess.run`` with
        ``shell=False``. We reject here at parse time so a malformed
        plan never reaches the runtime surface.

        The check is lazy-imported to avoid a ``schemas →
        orchestrator`` cycle: parsing a plan must not require the
        orchestrator package to exist.
        """
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError(
                "regression_baseline_cmd must be non-empty when set"
            )
        try:
            # Local import — breaking the cycle, and keeping schemas
            # importable standalone (e.g. for the CLI validator).
            from orchestrator.orchestrator import _parse_verify_cmd

            _parse_verify_cmd(stripped)
        except ModuleNotFoundError:
            # Orchestrator package absent (very rare — only in schema-
            # only test environments). Skip deep parsing; preserve
            # surface-level non-empty check.
            return stripped
        except ValueError as exc:
            raise ValueError(
                f"regression_baseline_cmd rejected by allowlist: {exc}"
            ) from exc
        return stripped

    @field_validator("compliance_flags")
    @classmethod
    def _compliance_flags_shape(cls, v: list[str]) -> list[str]:
        """Normalise to lowercase, trimmed, non-empty tags."""
        out: list[str] = []
        for entry in v:
            if not isinstance(entry, str):
                raise ValueError(
                    "compliance_flags must be a list of strings"
                )
            tag = entry.strip().lower()
            if not tag:
                raise ValueError(
                    "compliance_flags entries must be non-empty"
                )
            if any(ch.isspace() for ch in tag):
                raise ValueError(
                    f"compliance_flags entry {entry!r} must not contain "
                    "whitespace (use hyphens, e.g. 'pci-dss')"
                )
            out.append(tag)
        return out


class ExecutionPlanValidator:
    """Structural validation beyond single-model checks.

    Verifies:
    - every ``depends_on`` reference points at a real step ID,
    - the graph has no cycles,
    - every step's ``agent`` is listed in ``library.yaml`` as type=agent.
    """

    def __init__(self, roster: set[str]) -> None:
        self._roster = roster

    @classmethod
    def from_library(cls, library_path: str | Path) -> ExecutionPlanValidator:
        """Build a validator by loading the agent roster from ``library.yaml``."""
        roster = load_agent_roster(library_path)
        return cls(roster)

    def validate(self, plan: ExecutionPlan) -> None:
        """Raise ``ValueError`` on the first structural problem found."""
        ids = {s.id for s in plan.steps}
        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in ids:
                    raise ValueError(
                        f"step {step.id!r} depends on unknown step {dep!r}"
                    )
            if step.agent not in self._roster:
                raise ValueError(
                    f"step {step.id!r} references agent {step.agent!r} "
                    f"which is not in the roster"
                )
            self._check_context_paths_exist(step)
        self._check_acyclic(plan)

    @staticmethod
    def _check_context_paths_exist(step: TaskStep) -> None:
        """Require every ``context_excerpts`` + ``spec_refs`` path to exist.

        Field-level validation only rejects absolute paths; existence is a
        project-level concern, so the structural validator owns it. Paths
        are resolved from the current working directory — the CLI and the
        orchestrator both cd to the repo root before validating a plan.
        """
        for kind, entries in (
            ("context_excerpts", step.context_excerpts),
            ("spec_refs", step.spec_refs),
        ):
            for entry in entries:
                path_part = entry.split("#", 1)[0]
                m = _LINE_RANGE_TAIL.search(path_part)
                if m is not None:
                    path_part = path_part[: m.start()]
                p = Path(path_part)
                if not p.exists():
                    raise ValueError(
                        f"step {step.id!r} {kind} references missing path "
                        f"{path_part!r}"
                    )

    @staticmethod
    def _check_acyclic(plan: ExecutionPlan) -> None:
        """Kahn's algorithm — raises if a cycle is detected."""
        indeg: dict[str, int] = defaultdict(int)
        graph: dict[str, list[str]] = defaultdict(list)
        for step in plan.steps:
            indeg[step.id]  # touch so nodes with no deps register
            for dep in step.depends_on:
                graph[dep].append(step.id)
                indeg[step.id] += 1
        queue: deque[str] = deque(
            node for node, d in indeg.items() if d == 0
        )
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for nxt in graph[node]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
        if visited != len(plan.steps):
            remaining = [s.id for s in plan.steps if indeg[s.id] > 0]
            raise ValueError(
                f"cycle detected involving steps: {sorted(remaining)}"
            )


def load_agent_roster(library_path: str | Path) -> set[str]:
    """Parse ``library.yaml`` and return the set of agent names."""
    path = Path(library_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "catalog" not in raw:
        raise ValueError(f"library file {path} missing 'catalog' key")
    entries = raw["catalog"]
    if not isinstance(entries, list):
        raise ValueError(f"library file {path} 'catalog' must be a list")
    roster: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict) and entry.get("type") == "agent":
            name = entry.get("name")
            if isinstance(name, str):
                roster.add(name)
    if not roster:
        raise ValueError(f"library file {path} has no agent entries")
    return roster


# Best-effort load at import time so direct ``TaskStep(agent=...)`` calls
# in production code validate against the project's library.
_try_load_default_roster()


__all__ = [
    "DEFAULT_LIBRARY_PATH",
    "ExecutionPlan",
    "ExecutionPlanValidator",
    "ModelTier",
    "TaskStep",
    "get_active_roster",
    "load_agent_roster",
    "set_active_roster",
]
