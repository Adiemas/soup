"""Soup orchestrator package.

The orchestrator executes ``ExecutionPlan``s (validated DAGs of TaskSteps)
by computing waves, spawning fresh Claude Code subagents per step, running
their declared ``verify_cmd``, and committing atomically on success.

Public entry points:

* :class:`orchestrator.orchestrator.Orchestrator` — DAG executor.
* :class:`orchestrator.meta_prompter.MetaPrompter` — goal → plan (opus).
* :func:`orchestrator.agent_factory.spawn` — launch one subagent step.
* :func:`orchestrator.waves.compute_waves` — pure topological grouping.
* :class:`orchestrator.state.RunState` — JSON-backed run persistence.
* :mod:`orchestrator.cli` — ``soup`` Typer entry point.
"""

from __future__ import annotations

__all__ = [
    "agent_factory",
    "cli",
    "meta_prompter",
    "orchestrator",
    "state",
    "waves",
]
