"""Compute topological execution waves for an ExecutionPlan.

A wave is a set of TaskSteps whose dependencies are all satisfied by earlier
waves. Steps inside a wave may run concurrently iff every step in the wave
sets ``parallel=True``; otherwise the orchestrator runs them sequentially
but still in a single wave (for logging/reporting clarity).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Sequence

from schemas.execution_plan import TaskStep


def compute_waves(steps: Sequence[TaskStep]) -> list[list[TaskStep]]:
    """Group steps into dependency-respecting waves.

    Kahn's algorithm: at each level, pick every step whose indegree is zero,
    emit them as a wave, decrement successors, repeat.

    Args:
        steps: All steps in the plan.

    Returns:
        List of waves; each wave is a list of TaskSteps ready to run in parallel
        (subject to their individual ``parallel`` flag).

    Raises:
        ValueError: If the DAG has a cycle or references an unknown ID.
    """
    by_id: dict[str, TaskStep] = {s.id: s for s in steps}
    if len(by_id) != len(steps):
        dupes = _find_duplicates(s.id for s in steps)
        raise ValueError(f"duplicate step ids: {sorted(dupes)}")

    indeg: dict[str, int] = {sid: 0 for sid in by_id}
    successors: dict[str, list[str]] = defaultdict(list)
    for step in steps:
        for dep in step.depends_on:
            if dep not in by_id:
                raise ValueError(
                    f"step {step.id!r} depends on unknown step {dep!r}"
                )
            successors[dep].append(step.id)
            indeg[step.id] += 1

    ready: deque[str] = deque(
        sorted(sid for sid, d in indeg.items() if d == 0)
    )
    waves: list[list[TaskStep]] = []
    emitted: set[str] = set()
    while ready:
        this_wave_ids = list(ready)
        ready.clear()
        wave = [by_id[sid] for sid in this_wave_ids]
        waves.append(wave)
        emitted.update(this_wave_ids)
        next_ready: list[str] = []
        for sid in this_wave_ids:
            for succ in successors[sid]:
                indeg[succ] -= 1
                if indeg[succ] == 0:
                    next_ready.append(succ)
        ready.extend(sorted(next_ready))

    if len(emitted) != len(by_id):
        remaining = sorted(set(by_id) - emitted)
        raise ValueError(f"cycle detected involving steps: {remaining}")
    return waves


def _find_duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for v in values:
        if v in seen:
            dupes.add(v)
        seen.add(v)
    return dupes


__all__ = ["compute_waves"]
