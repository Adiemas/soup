"""Goal → ExecutionPlan JSON via Anthropic opus.

The meta-prompter is the *only* agentic component in the planning loop; the
orchestrator itself is deterministic. We:

1. Compose a system prompt containing the constitution snapshot and the
   available agent roster (both are cache-friendly).
2. Send the user's goal + any caller context.
3. Parse the returned JSON, ``ExecutionPlan.model_validate()`` it, then
   run ``ExecutionPlanValidator`` for structural checks.
4. On validation failure, loop up to ``max_retries`` times, feeding the
   error back into the prompt.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schemas.execution_plan import (
    ExecutionPlan,
    ExecutionPlanValidator,
    load_agent_roster,
)

_DEFAULT_MODEL = "claude-opus-4-5"
_DEFAULT_MAX_TOKENS = 8192
_DEFAULT_MAX_RETRIES = 3


@dataclass(slots=True)
class MetaPrompterConfig:
    """Runtime configuration for the meta-prompter."""

    library_path: Path = Path("library.yaml")
    constitution_path: Path = Path("CONSTITUTION.md")
    model: str = _DEFAULT_MODEL
    max_tokens: int = _DEFAULT_MAX_TOKENS
    max_retries: int = _DEFAULT_MAX_RETRIES
    api_key: str | None = None  # None → read ANTHROPIC_API_KEY at call time


_SYSTEM_TMPL = """\
You are the Soup meta-prompter. Given a goal, produce a JSON ExecutionPlan.

## Constitution (frozen)
{constitution}

## Agent roster (ONLY these values may appear in ``step.agent``)
{roster}

## Schema (ExecutionPlan)
{{
  "goal": "<copy of user goal>",
  "constitution_ref": "CONSTITUTION.md",
  "steps": [
    {{
      "id": "S1",
      "agent": "<roster name>",
      "prompt": "<full brief, >= 80 chars>",
      "depends_on": [],
      "parallel": false,
      "model": "haiku|sonnet|opus",
      "verify_cmd": "<bash command, exit 0 = pass>",
      "files_allowed": ["glob", ...],
      "max_turns": 10,
      "rag_queries": []
    }}
  ],
  "budget_sec": 3600,
  "worktree": true
}}

Rules:
- Output ONLY the JSON object — no prose, no markdown fences.
- Every ``depends_on`` entry must reference an existing ``id``.
- No cycles.
- Every ``agent`` must be in the roster.
- Prefer cheap models (haiku/sonnet); reserve opus for architecture/SQL.
- Split anything that would exceed 10 turns into multiple steps.
"""


_INGEST_SYSTEM_TMPL = """\
You are the Soup meta-prompter in INGEST mode. Your job is to read a prose
document describing existing work (an AGENT_*_SPEC.md, *_PLAN.md, or
*_HANDOFF.md from a brownfield repo) and emit a skeleton ExecutionPlan
JSON that mirrors the work items it already describes.

## Constitution (frozen)
{constitution}

## Agent roster (ONLY these values may appear in ``step.agent``)
{roster}

## Behaviour
- Extract work items, do not invent them. If a phase is vague, the step's
  prompt MUST include a literal `TODO: clarify` marker rather than
  inventing missing requirements.
- For fields you cannot infer from the prose:
    - ``verify_cmd`` -> default ``"true"`` and add a `TODO: define verify_cmd`
      line at the end of the step's ``prompt``.
    - ``files_allowed`` -> leave empty ``[]`` and add `TODO: scope files_allowed`.
    - ``model`` -> default ``"sonnet"``.
    - ``max_turns`` -> default ``8``.
    - ``agent`` -> pick the closest match from the roster; if unclear,
      default to ``implementer`` and add `TODO: pick specialist agent`.
- Preserve the prose's implicit DAG: if the doc says "Phase 2 depends on
  Phase 1" or "after X, do Y", reflect it in ``depends_on``.
- Map one prose work-item to one TaskStep (approximately one per numbered
  phase or section — do not explode sub-bullets into separate steps).
- Honor the schema exactly; the skeleton must validate against
  ``ExecutionPlan`` with no post-processing.

## Output (ExecutionPlan schema)
{{
  "goal": "<one-line summary of what this prose describes>",
  "constitution_ref": "CONSTITUTION.md",
  "steps": [
    {{
      "id": "S1",
      "agent": "<roster name>",
      "prompt": "<extract + TODO markers as needed, >= 80 chars>",
      "depends_on": [],
      "parallel": false,
      "model": "sonnet",
      "verify_cmd": "true",
      "files_allowed": [],
      "max_turns": 8,
      "rag_queries": []
    }}
  ],
  "budget_sec": 3600,
  "worktree": true
}}

Rules:
- Output ONLY the JSON object — no prose, no markdown fences.
- Every ``depends_on`` entry must reference an existing ``id``.
- No cycles.
- Every ``agent`` must be in the roster.
- Do not hallucinate. When the prose is silent, use the defaults above
  and mark the gap in the step's ``prompt`` as `TODO:`.
"""


class MetaPrompter:
    """Plan synthesizer backed by the Anthropic messages API.

    The ``anthropic`` SDK is imported lazily so tests can monkeypatch the
    ``_client_call`` hook without the dependency being available at import
    time.
    """

    def __init__(self, config: MetaPrompterConfig | None = None) -> None:
        self.config = config or MetaPrompterConfig()
        self._roster = load_agent_roster(self.config.library_path)
        self._validator = ExecutionPlanValidator(self._roster)

    async def plan_for(
        self, goal: str, context: Mapping[str, Any] | None = None
    ) -> ExecutionPlan:
        """Produce a validated ExecutionPlan for ``goal``.

        Args:
            goal: Natural-language user intent.
            context: Optional extra context (spec excerpt, prior
                failures). If ``context`` contains a ``findings`` key
                whose value is a path to a researcher findings
                markdown report, iter-3 F4 auto-hydration runs: after
                the plan parses + validates, each implementing step's
                ``context_excerpts`` is populated by matching
                findings to ``files_allowed`` globs (see
                ``scripts.hydrate_context_excerpts.hydrate``).
                Re-validation is NOT run — hydration only adds
                relative paths, which pass the field validator by
                construction.

        Returns:
            A structurally valid ExecutionPlan.

        Raises:
            RuntimeError: If retries are exhausted without a valid plan.
        """
        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message(goal, context)
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            raw = await self._client_call(
                system_prompt=system_prompt,
                user_message=user_message,
                attempt=attempt,
            )
            try:
                plan = self._parse_and_validate(raw, goal)
                plan = self._maybe_hydrate(plan, context)
                return plan
            except Exception as e:
                last_error = e
                user_message = self._append_error(user_message, raw, str(e))
        raise RuntimeError(
            f"meta-prompter failed after {self.config.max_retries} attempts: "
            f"{last_error}"
        )

    def _maybe_hydrate(
        self,
        plan: ExecutionPlan,
        context: Mapping[str, Any] | None,
    ) -> ExecutionPlan:
        """F4 plumbing hook: auto-hydrate context_excerpts from findings.

        No-op when ``context`` is ``None`` / empty / has no ``findings``
        key. The ``findings`` value must be a path (str or Path) to a
        researcher findings markdown report. Failures (missing file,
        unparsable JSON on re-serialise) are logged and the original
        plan is returned unchanged — hydration is strictly additive.
        """
        if not context:
            return plan
        findings_ref = context.get("findings") if isinstance(context, Mapping) else None
        if not findings_ref:
            return plan
        try:
            from pathlib import Path as _P

            from scripts.hydrate_context_excerpts import (
                hydrate as _hydrate,
                parse_findings as _parse_findings,
            )
        except Exception:
            return plan
        findings_path = _P(str(findings_ref))
        if not findings_path.exists():
            return plan
        try:
            findings = _parse_findings(
                findings_path.read_text(encoding="utf-8")
            )
            if not findings:
                return plan
            plan_dict = plan.model_dump()
            _hydrate(findings, plan_dict)
            return ExecutionPlan.model_validate(plan_dict)
        except Exception:
            # Never fail the whole plan_for() over a hydration error.
            return plan

    async def ingest_prose(
        self, source_path: Path, prose: str
    ) -> ExecutionPlan:
        """Convert a brownfield prose doc into a skeleton ExecutionPlan.

        Called by ``soup ingest-plans`` to onboard repos that already have
        ``AGENT_*_SPEC.md`` / ``*_PLAN.md`` / ``*_HANDOFF.md`` files. The
        prompt differs from :meth:`plan_for` — it asks the model to extract
        *existing* work items (don't hallucinate new ones) and emit a
        skeleton the human will review before running.
        """
        system_prompt = self._build_ingest_system_prompt()
        user_message = (
            "Extract work items described in the prose document below "
            f"(source: `{source_path.as_posix()}`). Output a skeleton "
            "ExecutionPlan JSON object only — no prose, no fences.\n\n"
            "## Prose document\n"
            f"```\n{prose}\n```\n"
        )
        goal = f"Ingested from {source_path.as_posix()}"
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            raw = await self._client_call(
                system_prompt=system_prompt,
                user_message=user_message,
                attempt=attempt,
            )
            try:
                plan = self._parse_and_validate(raw, goal)
                return plan
            except Exception as e:
                last_error = e
                user_message = self._append_error(user_message, raw, str(e))
        raise RuntimeError(
            "meta-prompter ingest failed after "
            f"{self.config.max_retries} attempts: {last_error}"
        )

    # --- parts we expose for testing ------------------------------------
    def _build_system_prompt(self) -> str:
        constitution = self._load_constitution()
        roster_lines = "\n".join(f"- {name}" for name in sorted(self._roster))
        return _SYSTEM_TMPL.format(
            constitution=constitution, roster=roster_lines
        )

    def _build_ingest_system_prompt(self) -> str:
        """System prompt dedicated to ingesting brownfield prose docs.

        Differs from the planning prompt in three ways:
          1. The model is told the input is an existing description of
             work — it extracts, it does not invent.
          2. Fields the prose cannot fill must be given reasonable defaults
             *and* mentioned in the step's ``prompt`` under a ``Notes:``
             line so the human review can see the gaps.
          3. Explicit anti-hallucination language — if a phase is vague,
             the step's prompt must say "TODO: clarify" rather than
             fabricate requirements.
        """
        roster_lines = "\n".join(f"- {name}" for name in sorted(self._roster))
        return _INGEST_SYSTEM_TMPL.format(
            constitution=self._load_constitution(), roster=roster_lines
        )

    def _load_constitution(self) -> str:
        path = self.config.constitution_path
        if not path.exists():
            return "(constitution file missing)"
        return path.read_text(encoding="utf-8")

    def _build_user_message(
        self, goal: str, context: Mapping[str, Any] | None
    ) -> str:
        body = {"goal": goal, "context": dict(context or {})}
        return (
            "Produce an ExecutionPlan JSON object for the following request. "
            "Output JSON only.\n\n"
            f"{json.dumps(body, indent=2)}"
        )

    def _parse_and_validate(
        self, raw: str, goal: str
    ) -> ExecutionPlan:
        text = _strip_code_fence(raw).strip()
        data = json.loads(text)
        if isinstance(data, dict):
            data.setdefault("goal", goal)
        plan = ExecutionPlan.model_validate(data)
        self._validator.validate(plan)
        return plan

    @staticmethod
    def _append_error(
        user_message: str, raw: str, error: str
    ) -> str:
        """Extend the user message with the previous attempt and its error."""
        return (
            f"{user_message}\n\n"
            f"Previous attempt failed validation:\n{error}\n\n"
            f"Previous output:\n{raw[:2000]}\n\n"
            "Fix the problem and return a corrected JSON object only."
        )

    # --- transport (monkey-patchable in tests) --------------------------
    async def _client_call(
        self,
        *,
        system_prompt: str,
        user_message: str,
        attempt: int,
    ) -> str:
        """Invoke Anthropic messages API; returns the raw text content.

        Uses ephemeral prompt caching on the system block so the
        constitution + roster stay hot across retries and sibling runs.
        """
        api_key = self.config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        # Lazy import — keeps test rigs simple.
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        # Concatenate text blocks.
        parts: list[str] = []
        for block in response.content:
            text_attr = getattr(block, "text", None)
            if isinstance(text_attr, str):
                parts.append(text_attr)
        return "".join(parts)


def _strip_code_fence(raw: str) -> str:
    """Remove ```json ... ``` fences if the model ignored the "no prose" rule."""
    s = raw.strip()
    if s.startswith("```"):
        # drop first line (```json or similar)
        lines = s.splitlines()
        if lines:
            lines = lines[1:]
        # drop trailing ``` if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return s


__all__ = ["MetaPrompter", "MetaPrompterConfig"]
