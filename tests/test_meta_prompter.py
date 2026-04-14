"""Unit tests for :mod:`orchestrator.meta_prompter`.

The Anthropic SDK is never actually called — we monkeypatch ``_client_call``
to return canned JSON.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestrator.meta_prompter import MetaPrompter, MetaPrompterConfig

_ROSTER = {
    "orchestrator",
    "meta-prompter",
    "implementer",
    "test-engineer",
    "verifier",
}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    library = tmp_path / "library.yaml"
    library.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "catalog": [
                    {"name": n, "type": "agent", "source": f"local:{n}.md"}
                    for n in _ROSTER
                ],
            }
        ),
        encoding="utf-8",
    )
    constitution = tmp_path / "CONSTITUTION.md"
    constitution.write_text("# Constitution\nBe good.\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return {"library": library, "constitution": constitution}


def _good_plan_json() -> str:
    return """\
{
  "goal": "Add /ping endpoint",
  "constitution_ref": "CONSTITUTION.md",
  "steps": [
    {
      "id": "S1",
      "agent": "test-engineer",
      "prompt": "Write a failing test for the /ping endpoint to return 200.",
      "depends_on": [],
      "parallel": false,
      "model": "sonnet",
      "verify_cmd": "pytest tests/test_ping.py",
      "files_allowed": ["tests/**"],
      "max_turns": 8,
      "rag_queries": []
    },
    {
      "id": "S2",
      "agent": "implementer",
      "prompt": "Make the failing /ping test pass by implementing the endpoint.",
      "depends_on": ["S1"],
      "parallel": false,
      "model": "sonnet",
      "verify_cmd": "pytest tests/test_ping.py",
      "files_allowed": ["app/**"],
      "max_turns": 10,
      "rag_queries": []
    }
  ],
  "budget_sec": 1800,
  "worktree": true
}
"""


async def test_plan_for_happy_path(
    env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    mp = MetaPrompter(
        MetaPrompterConfig(
            library_path=env["library"],
            constitution_path=env["constitution"],
        )
    )

    async def fake_call(self: MetaPrompter, **kwargs: str) -> str:
        return _good_plan_json()

    monkeypatch.setattr(MetaPrompter, "_client_call", fake_call)
    plan = await mp.plan_for("Add /ping endpoint")
    assert plan.goal == "Add /ping endpoint"
    assert [s.id for s in plan.steps] == ["S1", "S2"]
    assert plan.steps[1].depends_on == ["S1"]


async def test_plan_for_retries_on_invalid_then_succeeds(
    env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    mp = MetaPrompter(
        MetaPrompterConfig(
            library_path=env["library"],
            constitution_path=env["constitution"],
            max_retries=3,
        )
    )
    calls: list[int] = []

    async def fake_call(self: MetaPrompter, **kwargs: int) -> str:
        calls.append(kwargs["attempt"])
        if kwargs["attempt"] == 1:
            return "not json at all"
        if kwargs["attempt"] == 2:
            # references an unknown agent to trigger validator
            return _good_plan_json().replace(
                '"test-engineer"', '"ghost-agent"'
            )
        return _good_plan_json()

    monkeypatch.setattr(MetaPrompter, "_client_call", fake_call)
    plan = await mp.plan_for("Add /ping endpoint")
    assert calls == [1, 2, 3]
    assert plan.goal == "Add /ping endpoint"


async def test_plan_for_raises_after_max_retries(
    env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    mp = MetaPrompter(
        MetaPrompterConfig(
            library_path=env["library"],
            constitution_path=env["constitution"],
            max_retries=2,
        )
    )

    async def fake_call(self: MetaPrompter, **kwargs: str) -> str:
        return "definitely not json"

    monkeypatch.setattr(MetaPrompter, "_client_call", fake_call)
    with pytest.raises(RuntimeError, match="failed after 2 attempts"):
        await mp.plan_for("Goal")


def test_system_prompt_embeds_roster_and_constitution(
    env: dict[str, Path],
) -> None:
    mp = MetaPrompter(
        MetaPrompterConfig(
            library_path=env["library"],
            constitution_path=env["constitution"],
        )
    )
    sp = mp._build_system_prompt()
    assert "# Constitution" in sp
    for agent in _ROSTER:
        assert agent in sp
