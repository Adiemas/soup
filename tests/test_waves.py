"""Unit tests for :mod:`orchestrator.waves`."""

from __future__ import annotations

import pytest

from orchestrator.waves import compute_waves
from schemas.execution_plan import TaskStep


def _step(id_: str, deps: list[str] | None = None, *, parallel: bool = False) -> TaskStep:
    return TaskStep(
        id=id_,
        agent="implementer",
        prompt="p",
        verify_cmd="true",
        depends_on=deps or [],
        parallel=parallel,
    )


def test_single_step_single_wave() -> None:
    waves = compute_waves([_step("A")])
    assert [[s.id for s in w] for w in waves] == [["A"]]


def test_diamond_dag_four_waves() -> None:
    steps = [
        _step("A"),
        _step("B", ["A"]),
        _step("C", ["A"]),
        _step("D", ["B", "C"]),
    ]
    waves = compute_waves(steps)
    assert [sorted(s.id for s in w) for w in waves] == [
        ["A"],
        ["B", "C"],
        ["D"],
    ]


def test_parallel_sibling_wave_size_two() -> None:
    steps = [
        _step("root"),
        _step("a", ["root"], parallel=True),
        _step("b", ["root"], parallel=True),
    ]
    waves = compute_waves(steps)
    assert len(waves) == 2
    assert sorted(s.id for s in waves[1]) == ["a", "b"]


def test_cycle_detected() -> None:
    steps = [
        _step("A", ["B"]),
        _step("B", ["A"]),
    ]
    with pytest.raises(ValueError, match="cycle"):
        compute_waves(steps)


def test_unknown_dependency_raises() -> None:
    steps = [_step("A", ["ghost"])]
    with pytest.raises(ValueError, match="unknown step"):
        compute_waves(steps)


def test_waves_preserve_every_step() -> None:
    steps = [
        _step("S1"),
        _step("S2", ["S1"]),
        _step("S3", ["S1"]),
        _step("S4", ["S2"]),
        _step("S5", ["S2", "S3"]),
    ]
    waves = compute_waves(steps)
    flat = {s.id for w in waves for s in w}
    assert flat == {"S1", "S2", "S3", "S4", "S5"}
    # ordering invariant — every dep is in an earlier wave than its dependent.
    index = {s.id: i for i, w in enumerate(waves) for s in w}
    for s in steps:
        for dep in s.depends_on:
            assert index[dep] < index[s.id]
