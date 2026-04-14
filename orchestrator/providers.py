"""Provider adapter seam.

The framework's default provider is the Claude Code CLI wrapped by
``orchestrator.agent_factory.spawn`` and the Anthropic-backed
``MetaPrompter`` in ``orchestrator.meta_prompter``. Both are hardcoded
today; this module formalises the *seam* — a :class:`ProviderAdapter`
Protocol and a concrete :class:`ClaudeCodeAdapter` default — so a
future provider (OpenAI, Azure OpenAI, a local Ollama model, a custom
MCP-backed server, etc.) can drop in without rewriting the
orchestrator.

Extension recipe (see `docs/ARCHITECTURE.md §8.5`):

1. Implement :class:`ProviderAdapter` for your provider.
2. Register it in :class:`orchestrator.orchestrator.Orchestrator` at
   init time (pass via ``OrchestratorConfig`` once that knob is wired;
   today the orchestrator is hardcoded to :class:`ClaudeCodeAdapter`
   and the next commit that needs it will widen the config).
3. Update the pricing table in ``orchestrator.orchestrator`` so
   ``experiments.tsv.cost_usd`` stays comparable.

This module deliberately does *not* change the orchestrator's runtime
path. The orchestrator still calls ``agent_factory.spawn`` directly.
The Protocol exists to give future providers a clear insertion point
and to document the contract that ``agent_factory.spawn`` +
``meta_prompter.plan_for`` jointly implement.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from orchestrator.agent_factory import StepResult
    from schemas.execution_plan import ExecutionPlan, TaskStep


@runtime_checkable
class ProviderAdapter(Protocol):
    """Abstract the two places a model provider is invoked.

    Any class implementing both methods can drop in as the underlying
    model surface. The orchestrator never reaches past these two
    methods to reach a specific CLI binary or SDK.
    """

    async def spawn_agent(
        self,
        step: TaskStep,
        plan_context: Mapping[str, Any] | None = None,
        *,
        env: Mapping[str, str] | None = None,
        timeout_sec: float | None = None,
    ) -> StepResult:
        """Execute one TaskStep as a fresh subagent.

        Mirrors :func:`orchestrator.agent_factory.spawn` exactly —
        returns a :class:`StepResult` with status / exit_code / stdout
        / stderr / duration_ms / log_path / session_id. Implementations
        are expected to honour the step's ``files_allowed``,
        ``max_turns``, ``rag_queries``, and ``env`` fields via the
        provider's own mechanism; callers treat the StepResult as the
        sole wire contract.
        """
        ...

    async def plan_with_goal(
        self,
        goal: str,
        context: Mapping[str, Any] | None = None,
    ) -> ExecutionPlan:
        """Decompose a natural-language goal into a validated
        :class:`ExecutionPlan`.

        Mirrors :meth:`orchestrator.meta_prompter.MetaPrompter.plan_for`.
        Implementations must return a plan that passes both the
        Pydantic schema and the roster/DAG validator; on malformed
        provider output, they should retry internally (the default
        adapter retries up to 3 times) before raising.
        """
        ...


class ClaudeCodeAdapter:
    """Default provider — wraps ``agent_factory.spawn`` and
    ``meta_prompter.plan_for`` so they satisfy :class:`ProviderAdapter`.

    Using this adapter explicitly is optional today; the orchestrator
    will continue to call ``agent_factory.spawn`` / ``MetaPrompter``
    directly until a non-Anthropic provider ships. The adapter exists
    so that:

    - The Protocol has a reference implementation to typecheck
      against.
    - Future providers have a stable shape to mirror.
    - Integration tests can swap providers with a single constructor
      argument.
    """

    def __init__(
        self,
        *,
        meta_prompter: Any | None = None,
        spawn_fn: Any | None = None,
    ) -> None:
        # Lazy imports so constructing an adapter does not pull in the
        # anthropic SDK (meta_prompter does) unless actually used.
        if meta_prompter is None:
            from orchestrator.meta_prompter import (
                MetaPrompter,
                MetaPrompterConfig,
            )

            meta_prompter = MetaPrompter(MetaPrompterConfig())
        if spawn_fn is None:
            from orchestrator.agent_factory import spawn as _spawn

            spawn_fn = _spawn
        self._meta = meta_prompter
        self._spawn = spawn_fn

    async def spawn_agent(
        self,
        step: TaskStep,
        plan_context: Mapping[str, Any] | None = None,
        *,
        env: Mapping[str, str] | None = None,
        timeout_sec: float | None = None,
    ) -> StepResult:
        return await self._spawn(
            step,
            plan_context=plan_context,
            env=env,
            timeout_sec=timeout_sec,
        )

    async def plan_with_goal(
        self,
        goal: str,
        context: Mapping[str, Any] | None = None,
    ) -> ExecutionPlan:
        return await self._meta.plan_for(goal)


__all__ = ["ClaudeCodeAdapter", "ProviderAdapter"]
