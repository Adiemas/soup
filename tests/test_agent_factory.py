"""Tests for ``orchestrator/agent_factory.py`` context-excerpt injection.

These exercise the pure-Python slice of ``_compose_brief`` that reads
``TaskStep.context_excerpts`` and ``TaskStep.spec_refs`` and folds the
resolved text into the subagent prompt. No subprocess spawn is exercised
here — the spawn path is covered by ``test_orchestrator.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from orchestrator.agent_factory import (
    _compose_brief,
    _extract_markdown_section,
    _load_excerpt,
    _resolve_context_excerpts,
)
from schemas.execution_plan import TaskStep, set_active_roster


@pytest.fixture(autouse=True)
def _permissive_roster() -> object:
    prior_roster = frozenset()
    try:
        from schemas.execution_plan import get_active_roster

        prior_roster = frozenset(get_active_roster())
    except Exception:
        pass
    set_active_roster({"implementer", "test-engineer", "verifier"})
    yield
    set_active_roster(set(prior_roster))


def test_load_excerpt_resolves_markdown_heading_anchor(tmp_path: Path) -> None:
    """``path#anchor`` returns the markdown section under the matching heading.

    The section runs from the heading line down to (but excluding) the next
    heading of the same or shallower depth. Slug-style anchors (e.g.
    ``phase-1``) match headings like ``## Phase 1`` via the lowercase slug.
    """
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    spec = spec_dir / "combat.md"
    spec.write_text(
        "# Combat calculator\n"
        "\n"
        "Intro prose.\n"
        "\n"
        "## Phase 1\n"
        "\n"
        "Hit probability formula: WS.\n"
        "\n"
        "## Phase 2\n"
        "\n"
        "Wound probability.\n",
        encoding="utf-8",
    )
    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        text, label = _load_excerpt(
            "specs/combat.md#phase-1", cap_bytes=20_000
        )
        assert text is not None
        assert label == "specs/combat.md#phase-1"
        assert "## Phase 1" in text
        assert "Hit probability formula" in text
        # Section terminates before the next ``##`` sibling heading.
        assert "Wound probability" not in text
    finally:
        os.chdir(original_cwd)


def test_load_excerpt_resolves_line_range(tmp_path: Path) -> None:
    """``path:line_from-line_to`` returns the indicated 1-based line range.

    Lines outside the range are omitted. The form is used for pulling a
    slice of a source file into a subagent brief without shipping the
    whole module.
    """
    src_dir = tmp_path / "src" / "api"
    src_dir.mkdir(parents=True)
    src = src_dir / "auth.py"
    src.write_text(
        "\n".join(f"# line {i}" for i in range(1, 11)) + "\n",
        encoding="utf-8",
    )
    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        text, label = _load_excerpt(
            "src/api/auth.py:3-5", cap_bytes=20_000
        )
        assert text is not None
        assert label == "src/api/auth.py:3-5"
        # Inclusive range on both sides.
        assert text.splitlines() == ["# line 3", "# line 4", "# line 5"]
    finally:
        os.chdir(original_cwd)


def test_load_excerpt_missing_file_soft_fails(tmp_path: Path) -> None:
    """Resolution failures return ``(None, entry)`` rather than raising.

    The contract: ``agent_factory`` never blocks a spawn on a bad
    ``context_excerpts`` entry — it logs a warning and the subagent gets
    no injection for that entry.
    """
    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        text, label = _load_excerpt(
            "specs/does-not-exist.md#anchor", cap_bytes=20_000
        )
        assert text is None
        assert label == "specs/does-not-exist.md#anchor"

        # Line-range form also soft-fails.
        text2, _ = _load_excerpt(
            "src/gone.py:10-20", cap_bytes=20_000
        )
        assert text2 is None

        # Whole-file form also soft-fails.
        text3, _ = _load_excerpt("missing.txt", cap_bytes=20_000)
        assert text3 is None
    finally:
        os.chdir(original_cwd)


def test_compose_brief_injects_context_excerpts_section(tmp_path: Path) -> None:
    """``_compose_brief`` folds resolved excerpts under the ``## Context
    excerpts (verbatim)`` header, leaving the original step prompt intact.
    """
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    spec = spec_dir / "x.md"
    spec.write_text(
        "# top\n## anchor\n\nhello\n", encoding="utf-8"
    )
    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        step = TaskStep(
            id="S1",
            agent="implementer",
            prompt="do the thing",
            verify_cmd="true",
            context_excerpts=["specs/x.md#anchor"],
        )
        brief = _compose_brief(step, plan_context={})
        assert "## Context excerpts (verbatim)" in brief
        assert "specs/x.md#anchor" in brief
        assert "hello" in brief
        # Original prompt still present.
        assert "do the thing" in brief
    finally:
        os.chdir(original_cwd)


def test_resolve_context_excerpts_empty_when_no_entries() -> None:
    """Steps with no excerpts produce an empty injection block."""
    step = TaskStep(
        id="S1",
        agent="implementer",
        prompt="p",
        verify_cmd="true",
    )
    assert _resolve_context_excerpts(step) == ""


def test_extract_markdown_section_slug_and_substring() -> None:
    """Heading matching works for slug-equal and substring-contains."""
    text = "# top\n\n## Phase 1\nA\n\n## Phase 2\nB\n"
    # Slug match.
    sec = _extract_markdown_section(text, "phase-1")
    assert sec is not None and "A" in sec and "B" not in sec
    # Substring match.
    sec2 = _extract_markdown_section(text, "Phase 2")
    assert sec2 is not None and "B" in sec2 and "A" not in sec2
    # No match.
    assert _extract_markdown_section(text, "nope") is None


def test_context_excerpts_accepts_rag_uri() -> None:
    """F5 (iter-3 dogfood): RAG URI schemes are preserved in the brief.

    ``github://``, ``ado://``, ``ado-wi://``, ``file://``, ``http(s)://``,
    and ``web://`` URIs may appear in ``context_excerpts`` as retrieved
    from a rag-researcher pass. ``agent_factory`` must:

      1. Accept them (not reject as absolute paths).
      2. Inject a ``[source:<uri>]`` placeholder into the brief — the
         body is not read off disk.
      3. Otherwise continue to enforce relative-path safety for
         filesystem references.
    """
    from orchestrator.agent_factory import _safe_relative_path

    # 1. URIs survive the safe-path gate (as strings).
    for uri in (
        "github://streck/auth-service/src/lib/jwt.py",
        "ado://streck/Security/Security.wiki/AuthFlow.md",
        "ado-wi://streck/Platform/482",
        "file:///home/foo/spec.md",
        "https://example.com/docs/auth.md",
    ):
        result = _safe_relative_path(uri)
        assert result == uri, (
            f"URI {uri!r} should pass through _safe_relative_path, got {result!r}"
        )

    # 2. Absolute filesystem paths are still rejected.
    #    (Platform-varies: "/etc/passwd" is absolute on POSIX but not
    #    on Windows — Path.is_absolute() wants a drive letter there.
    #    Windows drive letter + UNC are the load-bearing negatives.)
    from pathlib import Path as _PathLib

    if _PathLib("/etc/passwd").is_absolute():
        assert _safe_relative_path("/etc/passwd") is None
    assert _safe_relative_path("C:\\Windows\\notepad.exe") is None
    assert _safe_relative_path("\\\\server\\share\\x.md") is None

    # 3. _load_excerpt emits the [source:<uri>] placeholder tag.
    text, label = _load_excerpt(
        "github://streck/auth/src/lib/jwt.py#42-58", cap_bytes=20_000
    )
    assert text is not None
    assert "[source:github://streck/auth/src/lib/jwt.py#42-58]" in text
    assert label.startswith("source:")

    # 4. ado-wi:// URIs flow through the same path.
    text2, label2 = _load_excerpt(
        "ado-wi://streck/Platform/482", cap_bytes=20_000
    )
    assert text2 is not None
    assert "[source:ado-wi://streck/Platform/482]" in text2
    assert label2 == "source:ado-wi://streck/Platform/482"

    # 5. Relative paths still flow through the normal resolution path
    #    — regression guard: URI acceptance must not break fs refs.
    p_result = _safe_relative_path("specs/auth.md")
    assert p_result is not None and not isinstance(p_result, str)
