"""Structured log event for every subagent tool call.

Emitted by the PostToolUse hook (see DESIGN §8). One JSON object per line in
``logging/agent-runs/session-{session_id}.jsonl``. Append-only; never rewritten.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LogStatus = Literal["started", "success", "error", "timeout", "blocked"]


class AgentLogEntry(BaseModel):
    """One tool-call event from a subagent session.

    Attributes:
        ts: ISO-8601 timestamp, UTC.
        session_id: Session this event belongs to; shape ``<agent>-<ts>``.
        agent: Agent role name (e.g. ``"implementer"``).
        action: Tool name (e.g. ``"Bash"``, ``"Edit"``, ``"Read"``).
        input_summary: First ~200 chars of tool input; secrets redacted.
        output_summary: First ~500 chars of tool output; secrets redacted.
        duration_ms: Wall-clock duration of the tool call.
        status: Outcome bucket.
        cost_estimate: Dollar estimate (input + output tokens x tier rate).
        parent_session_id: When set, the parent agent's ``session_id``
            that spawned this subagent. Forms a tree edge so
            ``soup logs tree`` can reconstruct the wave hierarchy from
            JSONL files alone (iter-3 ε1).
        root_run_id: Top-level orchestrator run id this event belongs
            to; equal across every subagent dispatched by the same plan.
        wave_idx: 0-based wave index within the orchestrator run.
        step_id: Originating ``TaskStep.id`` (e.g. ``"S3"``).
    """

    model_config = ConfigDict(extra="forbid")

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str = Field(..., min_length=1)
    agent: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    input_summary: str = ""
    output_summary: str = ""
    duration_ms: int = Field(default=0, ge=0)
    status: LogStatus = "started"
    cost_estimate: float = Field(default=0.0, ge=0.0)
    # iter-3 ε1: wave-tree threading. None on legacy entries; populated
    # by the orchestrator + post_tool_use hook for new spawns. Read by
    # ``soup logs tree`` to render the dispatch tree.
    parent_session_id: str | None = None
    root_run_id: str | None = None
    wave_idx: int | None = Field(default=None, ge=0)
    step_id: str | None = None

    def to_jsonl(self) -> str:
        """Serialize to one JSON line with a trailing newline."""
        return self.model_dump_json() + "\n"


__all__ = ["AgentLogEntry", "LogStatus"]
