"""Top-level DAG executor.

The Orchestrator takes a validated :class:`ExecutionPlan`, computes waves,
spawns subagents wave-by-wave (parallel where allowed), runs each step's
``verify_cmd`` after the subagent returns, commits atomically on pass, and
auto-injects a debug cycle on fail.

Design points (DESIGN §4):
- Fresh subagent per step (``agent_factory.spawn``).
- Verify command runs in a subprocess — no LLM judgment.
- Atomic git commit per passing step; message = "<id> <agent>: <prompt[:60]>".
- On failure, spawn a one-off fix-cycle step using the ``verifier`` agent
  with the failure context attached.
- ``budget_sec`` is a hard cap; orchestrator aborts if exceeded.
- State persisted under ``.soup/runs/<run_id>.json`` after every step.
- Experiment summary appended to ``logging/experiments.tsv`` on exit.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import shlex
import subprocess
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from orchestrator.agent_factory import StepResult, spawn
from orchestrator.state import RunState, StepRecord
from orchestrator.waves import compute_waves
from schemas.execution_plan import ExecutionPlan, TaskStep

RunStatus = Literal["passed", "failed", "aborted", "regression"]

_DEFAULT_RUNS_DIR = Path(".soup/runs")
_DEFAULT_EXPERIMENTS_TSV = Path("logging/experiments.tsv")

# Allowlist of executables that ``verify_cmd`` may invoke. Keep narrow —
# anything outside this set is rejected before ``subprocess.run``. The
# list covers every test runner, linter, type-checker, task runner, and
# scaffolder the 20-agent roster would plausibly invoke from a step's
# verify command. Cycle-1 prod critic #6 + final security audit C-A:
# ``verify_cmd`` is LLM-generated from the meta-prompter, so the
# orchestrator cannot trust it with ``shell=True``.
_VERIFY_CMD_ALLOWLIST: frozenset[str] = frozenset(
    {
        # test runners
        "pytest",
        "vitest",
        "jest",
        "playwright",
        "dotnet",
        "go",
        "cargo",
        # linters / type checkers
        "ruff",
        "mypy",
        "eslint",
        "tsc",
        # task runners / package managers
        "just",
        "make",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        # direct language runtimes
        "python",
        "python3",
        "node",
        # scaffolding / infra
        "docker",
        "gh",
        "az",
        # POSIX trivial utilities (used by e.g. ``test -f path.md``)
        "test",
        "true",
        "false",
        "echo",
        "ls",
        "cat",
    }
)

# Pattern used to detect the TDD RED-phase ``!`` prefix. See PATTERNS
# §0b — a leading ``! `` means "invert the exit code," used when a step
# is authored to *expect* failure (e.g. a failing test landing before
# the GREEN-phase implementer runs). The bang is stripped before
# ``shlex.split`` so the first token remains allowlist-checkable.
_VERIFY_CMD_NEGATE_RE = re.compile(r"^\s*!\s+")


def _parse_verify_cmd(
    cmd: str, allowlist: Iterable[str] | None = None
) -> tuple[list[str], bool]:
    """Split ``cmd`` safely into argv, honouring the ``!`` RED-phase prefix.

    Returns ``(argv, negate)``. ``negate`` is True when the original
    command started with ``! `` (bash-style negation used for RED-phase
    test gates). The caller is responsible for inverting the exit code
    when ``negate`` is True.

    Raises ``ValueError`` if the command cannot be split (unbalanced
    quotes) or if the first non-bang token is not in the effective
    allowlist (default :data:`_VERIFY_CMD_ALLOWLIST`; callers may pass
    a widened set to include per-project extras).
    """
    stripped = cmd.strip()
    negate = False
    m = _VERIFY_CMD_NEGATE_RE.match(stripped)
    if m:
        negate = True
        stripped = stripped[m.end():]
    try:
        argv = shlex.split(stripped)
    except ValueError as exc:
        raise ValueError(
            f"verify_cmd cannot be tokenised (unbalanced quotes?): {exc}"
        ) from exc
    if not argv:
        raise ValueError("verify_cmd is empty")
    exe = Path(argv[0]).name  # strip any path prefix
    # Windows ``foo.exe`` → compare against the bare executable name.
    exe_key = exe[:-4] if exe.lower().endswith(".exe") else exe
    effective = (
        set(allowlist) if allowlist is not None else set(_VERIFY_CMD_ALLOWLIST)
    )
    if exe_key not in effective:
        raise ValueError(
            f"verify_cmd executable {exe_key!r} not on allowlist; "
            "add it via --extra-verify-bin or to the allowlist config "
            f"(allowed: {sorted(effective)})"
        )
    return argv, negate

# Approximate Anthropic list-price USD per 1M tokens at framework v1.
# Used for cost_usd estimates only (DESIGN §3). Treat the numbers in
# experiments.tsv as an estimate: the Anthropic SDK exposes input /
# output token counts, and we multiply by these rates. Update in
# lockstep with published list prices.
_MODEL_PRICING_USD_PER_MTOKEN: dict[str, tuple[float, float]] = {
    # model id → (input $/MTok, output $/MTok)
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
}


def _estimate_cost_usd(
    model: str, input_tokens: int, output_tokens: int
) -> float:
    """Return an estimated USD cost for a single agent call.

    Maps the plan's ``model`` tier (``haiku``/``sonnet``/``opus``) or a
    dotted model id to the closest pricing row. Returns 0.0 if the
    model is unknown — better to log zero than crash the experiments
    sink.
    """
    key = model.lower()
    if key not in _MODEL_PRICING_USD_PER_MTOKEN:
        for tier in _MODEL_PRICING_USD_PER_MTOKEN:
            if tier in key:
                key = tier
                break
    rates = _MODEL_PRICING_USD_PER_MTOKEN.get(key)
    if rates is None:
        return 0.0
    inp_rate, out_rate = rates
    return (input_tokens / 1_000_000.0) * inp_rate + (
        output_tokens / 1_000_000.0
    ) * out_rate


@dataclass(slots=True)
class RunResult:
    """Aggregate result of an orchestrator run."""

    run_id: str
    status: RunStatus
    duration_sec: float
    step_results: dict[str, StepResult] = field(default_factory=dict)
    state_path: Path | None = None
    aborted_reason: str | None = None
    regression_baseline_diff_path: Path | None = None


@dataclass(slots=True)
class OrchestratorConfig:
    """Runtime knobs, mostly for testing."""

    runs_dir: Path = _DEFAULT_RUNS_DIR
    experiments_tsv: Path = _DEFAULT_EXPERIMENTS_TSV
    verify_timeout_sec: float = 900.0
    spawn_timeout_sec: float | None = None
    max_fix_cycles_per_step: int = 2
    enable_git_commits: bool = True
    git_cwd: Path = Path(".")
    # Root for pre/post baseline artefacts. Per-run subdirectory
    # ``<baseline_root>/<run_id>/`` holds ``pre.txt``, ``post.txt``,
    # and ``diff.txt``. See :meth:`Orchestrator._run_baseline`.
    baseline_root: Path = Path(".soup/baseline")
    # Extra executables operators can permit on top of the default
    # :data:`_VERIFY_CMD_ALLOWLIST`. Useful for per-project tools
    # (e.g. ``hatch``, ``poetry``). Keep surface narrow — this is an
    # audit-worthy lever.
    extra_verify_bins: tuple[str, ...] = ()


class Orchestrator:
    """Execute an ``ExecutionPlan`` as a sequence of parallel waves.

    The default model provider is the Claude Code CLI, invoked by
    :func:`orchestrator.agent_factory.spawn`. To drop in a different
    provider (OpenAI, a local OSS model, a custom MCP server), pass an
    object implementing :class:`orchestrator.providers.ProviderAdapter`
    as the future ``provider`` knob — today the orchestrator calls
    ``agent_factory.spawn`` directly, but the Protocol formalises the
    seam so providers can plug in without touching wave/state/verify
    logic. See :mod:`orchestrator.providers` and
    ``docs/ARCHITECTURE.md §8.5`` for the extension recipe.
    """

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        self.config = config or OrchestratorConfig()

    # -------------------------------------------------------------------
    async def run(self, plan: ExecutionPlan) -> RunResult:
        """Entry point: run the whole plan to completion."""
        state = RunState.new(
            goal=plan.goal,
            budget_sec=plan.budget_sec,
            runs_dir=self.config.runs_dir,
        )
        # Pre-register every step as pending.
        waves = compute_waves(plan.steps)
        for wave_idx, wave in enumerate(waves):
            for step in wave:
                state.upsert_step(
                    StepRecord(id=step.id, agent=step.agent, wave=wave_idx)
                )
        state.save()

        # Pre-wave baseline capture (brownfield-baseline-capture skill).
        # Fails here are logged but non-fatal; the QA gate sees the
        # missing pre-file and surfaces it.
        baseline_dir: Path | None = None
        pre_path: Path | None = None
        if plan.regression_baseline_cmd:
            baseline_dir = (
                self.config.baseline_root / state.run_id
            )
            baseline_dir.mkdir(parents=True, exist_ok=True)
            pre_path = baseline_dir / "pre.txt"
            self._run_baseline(
                cmd=plan.regression_baseline_cmd,
                out_path=pre_path,
                phase="pre",
                timeout_sec=float(plan.regression_baseline_timeout_sec),
                run_id=state.run_id,
            )

        plan_ctx: dict[str, Any] = {
            "goal": plan.goal,
            "constitution_ref": plan.constitution_ref,
        }
        t0 = time.monotonic()
        deadline = t0 + plan.budget_sec
        run_status: RunStatus = "passed"
        aborted_reason: str | None = None
        step_results: dict[str, StepResult] = {}
        fix_cycles: dict[str, int] = {}

        for wave_idx, wave in enumerate(waves):
            # Hard wall-clock abort: the budget is a *hard* cap, not a
            # suggestion. Check before every wave; individual steps
            # also check inside ``_run_step`` via the remaining
            # deadline-derived timeout. (Constitution Art. II.4,
            # Art. VIII.4.)
            if time.monotonic() >= deadline:
                run_status = "aborted"
                aborted_reason = (
                    f"budget_sec={plan.budget_sec} exceeded before wave "
                    f"{wave_idx}"
                )
                break

            wave_results = await self._run_wave(
                wave=wave,
                plan_ctx=plan_ctx,
                state=state,
                deadline=deadline,
                fix_cycles=fix_cycles,
                wave_idx=wave_idx,
                root_run_id=state.run_id,
            )
            step_results.update(wave_results)
            state.save()

            # Budget may have been exhausted *during* the wave — treat
            # that as an abort too, so downstream waves are not
            # attempted even if this wave happened to finish.
            if time.monotonic() >= deadline:
                run_status = "aborted"
                aborted_reason = (
                    f"budget_sec={plan.budget_sec} exceeded during wave "
                    f"{wave_idx}"
                )
                break

            # If any step in the wave failed and could not be recovered,
            # abort further waves (dependents would be unreachable anyway).
            if any(r.status != "passed" for r in wave_results.values()):
                run_status = "failed"
                break

        elapsed = time.monotonic() - t0

        # Post-wave baseline capture + diff. Skipped on orchestrator
        # abort so the pre-file remains pristine for post-mortem.
        diff_path: Path | None = None
        if (
            plan.regression_baseline_cmd
            and baseline_dir is not None
            and pre_path is not None
            and run_status == "passed"
        ):
            post_path = baseline_dir / "post.txt"
            self._run_baseline(
                cmd=plan.regression_baseline_cmd,
                out_path=post_path,
                phase="post",
                timeout_sec=float(plan.regression_baseline_timeout_sec),
                run_id=state.run_id,
            )
            diff_path = baseline_dir / "diff.txt"
            has_regression = self._write_baseline_diff(
                pre_path=pre_path,
                post_path=post_path,
                diff_path=diff_path,
            )
            state.regression_baseline_diff_path = str(diff_path)
            if has_regression:
                run_status = "regression"
                # Aborted-reason-ish surface so the experiment row
                # carries the hint. QA gate does the real triage.
                aborted_reason = (
                    "regression_baseline_diff flagged a previously-"
                    "passing test as failing or missing post-run; "
                    f"see {diff_path}"
                )

        state.status = run_status
        state.finished_at = datetime.now(UTC)
        state.save()
        total_cost = sum(
            (getattr(r, "cost_estimate", 0.0) or 0.0)
            for r in step_results.values()
        )
        self._append_experiment(
            plan=plan,
            run_id=state.run_id,
            status=run_status,
            duration_sec=elapsed,
            cost_usd=total_cost,
            aborted_reason=aborted_reason,
        )
        return RunResult(
            run_id=state.run_id,
            status=run_status,
            duration_sec=elapsed,
            step_results=step_results,
            state_path=state.path,
            aborted_reason=aborted_reason,
            regression_baseline_diff_path=diff_path,
        )

    # -------------------------------------------------------------------
    async def _run_wave(
        self,
        *,
        wave: list[TaskStep],
        plan_ctx: Mapping[str, Any],
        state: RunState,
        deadline: float,
        fix_cycles: dict[str, int],
        wave_idx: int = 0,
        root_run_id: str | None = None,
    ) -> dict[str, StepResult]:
        """Run one wave. Steps flagged ``parallel=True`` race concurrently."""
        all_parallel = all(s.parallel for s in wave) and len(wave) > 1
        if all_parallel:
            coros = [
                self._run_step(
                    step,
                    plan_ctx,
                    state,
                    deadline,
                    fix_cycles,
                    wave_idx=wave_idx,
                    root_run_id=root_run_id,
                )
                for step in wave
            ]
            gathered = await asyncio.gather(*coros, return_exceptions=False)
            return {
                step.id: res
                for step, res in zip(wave, gathered, strict=True)
            }
        results: dict[str, StepResult] = {}
        for step in wave:
            if time.monotonic() > deadline:
                break
            results[step.id] = await self._run_step(
                step,
                plan_ctx,
                state,
                deadline,
                fix_cycles,
                wave_idx=wave_idx,
                root_run_id=root_run_id,
            )
            if results[step.id].status != "passed":
                break  # short-circuit — downstream deps can't run
        return results

    # -------------------------------------------------------------------
    async def _run_step(
        self,
        step: TaskStep,
        plan_ctx: Mapping[str, Any],
        state: RunState,
        deadline: float,
        fix_cycles: dict[str, int],
        *,
        wave_idx: int = 0,
        root_run_id: str | None = None,
    ) -> StepResult:
        """Spawn the subagent, verify, commit (or enter debug cycle)."""
        rec = state.steps.get(step.id) or StepRecord(
            id=step.id, agent=step.agent
        )
        rec.status = "running"
        rec.started_at = datetime.now(UTC)
        state.upsert_step(rec)
        state.save()

        remaining = max(1.0, deadline - time.monotonic())
        spawn_timeout = (
            min(self.config.spawn_timeout_sec, remaining)
            if self.config.spawn_timeout_sec is not None
            else remaining
        )
        # iter-3 ε1: pass wave-tree identifiers down so post_tool_use can
        # stamp every JSONL line and ``soup logs tree`` can reconstruct.
        spawn_res = await spawn(
            step,
            plan_context=plan_ctx,
            timeout_sec=spawn_timeout,
            root_run_id=root_run_id or state.run_id,
            wave_idx=wave_idx,
        )

        verify_exit: int | None = None
        if spawn_res.status == "passed":
            verify_exit = self._run_verify(step)
            if verify_exit != 0:
                spawn_res.status = "failed"
                spawn_res.extra["verify_stderr"] = (
                    f"verify_cmd exit {verify_exit}"
                )

        # Failure? Try a bounded fix cycle via the verifier agent.
        if spawn_res.status != "passed":
            cycles = fix_cycles.get(step.id, 0)
            if cycles < self.config.max_fix_cycles_per_step:
                fix_cycles[step.id] = cycles + 1
                rec.status = "debugging"
                state.upsert_step(rec)
                state.save()
                fix_res = await self._run_fix_cycle(
                    step,
                    failure=spawn_res,
                    plan_ctx=plan_ctx,
                    deadline=deadline,
                    wave_idx=wave_idx,
                    root_run_id=root_run_id or state.run_id,
                    parent_session_id=spawn_res.session_id,
                )
                if fix_res.status == "passed":
                    # Re-run verify on the post-fix state.
                    verify_exit = self._run_verify(step)
                    if verify_exit == 0:
                        spawn_res = fix_res
                        spawn_res.status = "passed"
                    else:
                        spawn_res = fix_res
                        spawn_res.status = "failed"
                        spawn_res.extra["verify_stderr"] = (
                            f"post-fix verify exit {verify_exit}"
                        )

        # Commit on pass (if enabled).
        if spawn_res.status == "passed" and self.config.enable_git_commits:
            self._atomic_commit(step, spawn_res)

        rec.status = "passed" if spawn_res.status == "passed" else "failed"
        rec.finished_at = datetime.now(UTC)
        rec.duration_ms = spawn_res.duration_ms
        rec.verify_exit = verify_exit
        rec.output_path = (
            str(spawn_res.log_path) if spawn_res.log_path else None
        )
        state.upsert_step(rec)
        state.save()
        return spawn_res

    # -------------------------------------------------------------------
    def _run_verify(self, step_or_cmd: TaskStep | str) -> int:
        """Execute ``verify_cmd`` in a subprocess; return exit code.

        **Safety invariant:** ``verify_cmd`` is authored by an LLM
        (meta-prompter) and embedded in the plan JSON. The orchestrator
        does **not** invoke it with ``shell=True``. It tokenises the
        string via :func:`shlex.split`, checks the first token against
        :data:`_VERIFY_CMD_ALLOWLIST` (+ optional per-project additions
        declared in :attr:`OrchestratorConfig.extra_verify_bins`), then
        runs the argv directly. A leading ``! `` prefix (TDD RED-phase
        negation, see PATTERNS §0b) is honoured by inverting the exit
        code after the subprocess returns.

        Accepts either a :class:`TaskStep` (to pick up the step's
        ``verify_timeout_sec``) or a bare string (legacy path). Returns
        the exit code, with a few special values:

        - ``124`` → timeout
        - ``125`` → verify_cmd rejected by allowlist / parse error
        """
        if isinstance(step_or_cmd, TaskStep):
            verify_cmd = step_or_cmd.verify_cmd
            timeout = float(
                min(
                    step_or_cmd.verify_timeout_sec,
                    self.config.verify_timeout_sec,
                )
            )
        else:
            verify_cmd = step_or_cmd
            timeout = self.config.verify_timeout_sec

        allowed = set(_VERIFY_CMD_ALLOWLIST) | set(
            self.config.extra_verify_bins
        )
        try:
            argv, negate = _parse_verify_cmd(verify_cmd, allowlist=allowed)
        except ValueError:
            return 125

        try:
            completed = subprocess.run(
                argv,
                shell=False,
                cwd=str(self.config.git_cwd),
                timeout=timeout,
                capture_output=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return 124  # conventional timeout exit code
        except (FileNotFoundError, OSError):
            return 127  # shell-style "command not found"
        rc = completed.returncode
        if negate:
            # Bash-style negation: 0 ↔ non-zero. Preserve specific exit
            # codes when they carry meaning (124 timeout, 125 rejected).
            return 1 if rc == 0 else 0
        return rc

    # -------------------------------------------------------------------
    async def _run_fix_cycle(
        self,
        step: TaskStep,
        *,
        failure: StepResult,
        plan_ctx: Mapping[str, Any],
        deadline: float,
        wave_idx: int = 0,
        root_run_id: str | None = None,
        parent_session_id: str | None = None,
    ) -> StepResult:
        """Spawn a verifier-agent subagent seeded with failure context."""
        fix_step = step.model_copy(
            update={
                "id": f"{step.id}-fix",
                "agent": "verifier",
                "prompt": (
                    f"Original task {step.id} failed. Apply the "
                    "`systematic-debugging` skill (4-phase root cause). "
                    f"Failure summary:\n\n"
                    f"Status: {failure.status}\n"
                    f"Exit: {failure.exit_code}\n"
                    f"Stderr tail: {failure.stderr[-1200:]}\n"
                    f"Verify cmd: {step.verify_cmd}\n\n"
                    "Goal: make the verify_cmd pass with minimal diff. "
                    "Do not broaden the file scope beyond the original "
                    "files_allowed."
                ),
                "max_turns": max(step.max_turns, 12),
            }
        )
        remaining = max(1.0, deadline - time.monotonic())
        return await spawn(
            fix_step,
            plan_context=plan_ctx,
            timeout_sec=remaining,
            root_run_id=root_run_id,
            wave_idx=wave_idx,
            parent_session_id=parent_session_id,
        )

    # -------------------------------------------------------------------
    def _atomic_commit(self, step: TaskStep, result: StepResult) -> None:
        """Stage & commit the subagent's changes. Errors are swallowed w/ a log.

        We shell out to ``git`` so this works in worktrees without extra deps.
        """
        title = step.prompt.splitlines()[0][:60] if step.prompt else step.id
        msg = f"{step.agent}({step.id}): {title}\n\nStep: {step.id}\n"
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(self.config.git_cwd),
                check=False,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", msg, "--allow-empty"],
                cwd=str(self.config.git_cwd),
                check=False,
                capture_output=True,
            )
        except (FileNotFoundError, OSError) as e:
            result.extra["commit_error"] = repr(e)

    # -------------------------------------------------------------------
    def _append_experiment(
        self,
        *,
        plan: ExecutionPlan,
        run_id: str,
        status: RunStatus,
        duration_sec: float,
        cost_usd: float = 0.0,
        aborted_reason: str | None = None,
    ) -> None:
        """Append one row to ``logging/experiments.tsv`` (autoresearch-style).

        Columns:
            ts             ISO-8601 UTC timestamp.
            run_id         Orchestrator run identifier.
            status         passed / failed / aborted.
            duration_sec   Wall-clock seconds (formatted to 2 dp).
            n_steps        Number of steps in the plan.
            budget_sec     Declared wall-clock budget.
            cost_usd       Estimated USD cost across all step results.
                           See :func:`_estimate_cost_usd` — this is an
                           estimate based on Anthropic list pricing,
                           marked as such by the ``~`` prefix.
            aborted_reason Empty unless status == aborted.
            goal           The plan goal, shlex-quoted and truncated.
        """
        tsv = self.config.experiments_tsv
        tsv.parent.mkdir(parents=True, exist_ok=True)
        new_file = not tsv.exists()
        headers = [
            "ts",
            "run_id",
            "status",
            "duration_sec",
            "n_steps",
            "budget_sec",
            "cost_usd",
            "aborted_reason",
            "goal",
        ]
        row = [
            datetime.now(UTC).isoformat(timespec="seconds"),
            run_id,
            status,
            f"{duration_sec:.2f}",
            str(len(plan.steps)),
            str(plan.budget_sec),
            f"~{cost_usd:.4f}",
            (aborted_reason or "").replace("\t", " ").replace("\n", " ")[:120],
            shlex.quote(plan.goal)[:120],
        ]
        with tsv.open("a", encoding="utf-8") as fh:
            if new_file:
                # iter-3 ε2: schema version comment so consumers can
                # detect drift across soup releases. The stop hook owns
                # ``sessions.tsv`` (4 cols); this file is orchestrator-
                # only (9 cols). See docs/ARCHITECTURE.md §7.
                fh.write("# soup-schema:experiments-v1\n")
                fh.write("\t".join(headers) + "\n")
            fh.write("\t".join(row) + "\n")


    # -------------------------------------------------------------------
    def _run_baseline(
        self,
        *,
        cmd: str,
        out_path: Path,
        phase: Literal["pre", "post"],
        timeout_sec: float,
        run_id: str,
    ) -> int:
        """Execute ``cmd`` once; stream stdout into ``out_path``.

        Used by the brownfield-baseline-capture integration. The command
        passes through the same argv[0] allowlist as ``verify_cmd``
        (because a plan's ``regression_baseline_cmd`` field-validator
        already checked it at parse time — but we re-check here to
        preserve the defence-in-depth property that the runtime never
        trusts the plan JSON alone).

        Non-zero exit codes are **not** fatal: the orchestrator records
        them to ``logging/agent-runs/baseline-<run_id>-<phase>.log`` and
        writes the (possibly empty) stdout to ``out_path``. Callers
        inspect the artefact rather than the return code — a broken
        test harness in pre-run is itself evidence for the QA gate.

        Returns the subprocess exit code (124 on timeout, 125 on
        allowlist reject, 127 on missing executable).
        """
        allowed = set(_VERIFY_CMD_ALLOWLIST) | set(
            self.config.extra_verify_bins
        )
        try:
            argv, negate = _parse_verify_cmd(cmd, allowlist=allowed)
        except ValueError:
            out_path.write_text(
                f"[baseline-reject] {phase}: argv[0] not on allowlist\n",
                encoding="utf-8",
            )
            return 125
        if negate:
            # A ``!``-prefixed baseline cmd makes no semantic sense
            # (you want to capture *what passes*, not invert it). Log
            # and drop the negation.
            pass

        try:
            completed = subprocess.run(
                argv,
                shell=False,
                cwd=str(self.config.git_cwd),
                timeout=timeout_sec,
                capture_output=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            out_path.write_text(
                f"[baseline-timeout] {phase}: {timeout_sec}s\n",
                encoding="utf-8",
            )
            self._log_baseline_event(
                run_id=run_id,
                phase=phase,
                exit_code=124,
                out_path=out_path,
            )
            return 124
        except (FileNotFoundError, OSError) as exc:
            out_path.write_text(
                f"[baseline-missing-exe] {phase}: {exc}\n",
                encoding="utf-8",
            )
            return 127

        # Capture stdout primarily; fall back to stderr if stdout is
        # empty (some runners emit list-output on stderr).
        body = completed.stdout.decode("utf-8", errors="replace")
        if not body.strip() and completed.stderr:
            body = completed.stderr.decode("utf-8", errors="replace")
        out_path.write_text(body, encoding="utf-8")
        self._log_baseline_event(
            run_id=run_id,
            phase=phase,
            exit_code=completed.returncode,
            out_path=out_path,
        )
        return completed.returncode

    # -------------------------------------------------------------------
    @staticmethod
    def _log_baseline_event(
        *,
        run_id: str,
        phase: Literal["pre", "post"],
        exit_code: int,
        out_path: Path,
    ) -> None:
        """Append a single-line JSON event to ``logging/agent-runs/``."""
        log_dir = Path("logging") / "agent-runs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return  # logging is best-effort
        log_path = log_dir / f"baseline-{run_id}.jsonl"
        entry = (
            '{"ts":"%s","run_id":"%s","phase":"%s",'
            '"exit_code":%d,"out":"%s"}\n'
            % (
                datetime.now(UTC).isoformat(timespec="seconds"),
                run_id,
                phase,
                exit_code,
                str(out_path).replace("\\", "/"),
            )
        )
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(entry)
        except OSError:
            return

    # -------------------------------------------------------------------
    @staticmethod
    def _write_baseline_diff(
        *,
        pre_path: Path,
        post_path: Path,
        diff_path: Path,
    ) -> bool:
        """Compare pre/post baseline artefacts; return True on regression.

        "Regression" means: a line that appears in ``pre.txt`` (i.e. a
        test-identifier that passed before the run) is missing from
        ``post.txt`` OR its status changed from passing to failing.

        The conservative interpretation: we treat every pre-line as a
        potential test identifier; any pre-line not present in
        post-lines is a regression signal. The unified diff is written
        to ``diff_path`` regardless.

        If either file is unreadable, we write an explanatory diff and
        return False — the QA gate will see the artefact and decide.
        """
        try:
            pre_lines = pre_path.read_text(
                encoding="utf-8"
            ).splitlines(keepends=True)
            post_lines = post_path.read_text(
                encoding="utf-8"
            ).splitlines(keepends=True)
        except OSError as exc:
            diff_path.write_text(
                f"[baseline-diff-error] {exc}\n", encoding="utf-8"
            )
            return False
        diff = difflib.unified_diff(
            pre_lines,
            post_lines,
            fromfile=str(pre_path),
            tofile=str(post_path),
            n=2,
        )
        diff_text = "".join(diff)
        diff_path.write_text(diff_text, encoding="utf-8")
        pre_set = {ln.strip() for ln in pre_lines if ln.strip()}
        post_set = {ln.strip() for ln in post_lines if ln.strip()}
        missing = pre_set - post_set
        # Heuristic: we flag regression when any pre-line is absent
        # post-run. Plans can tighten this with a tailored baseline_cmd
        # (e.g. ``pytest --co -q`` gives deterministic test-id lines).
        return bool(missing)


__all__ = [
    "_VERIFY_CMD_ALLOWLIST",
    "Orchestrator",
    "OrchestratorConfig",
    "RunResult",
    "_estimate_cost_usd",
    "_parse_verify_cmd",
]
