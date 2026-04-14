"""Hydrate ``TaskStep.context_excerpts`` from a researcher findings report.

Iter-3 dogfood F4 plumbing: after the `researcher` agent emits a
findings table (see
``mock-apps/brownfield-damage-sim/.soup/research/*-findings.md`` for
the canonical shape), this script walks each step in a plan JSON file
and auto-populates ``context_excerpts`` by matching findings to
``files_allowed`` globs.

Usage:

    python -m scripts.hydrate_context_excerpts \\
        --findings .soup/research/<slug>-findings.md \\
        --plan .soup/plans/<slug>.json \\
        [--output .soup/plans/<slug>-hydrated.json]

The findings table format (markdown, one row per finding):

    | File | Line | Relevance | Excerpt |
    |---|---|---|---|
    | `backend/app/api/calc.py` | 35-45 | primary — ... | `@router.post(...)` |

Target-step heuristic: a step's ``files_allowed`` globs are matched
against each finding's ``file`` column (fnmatch-style). Only steps
whose agent is in the implementing-agent set
(``python-dev``, ``dotnet-dev``, ``implementer``, ``test-engineer``,
``full-stack-integrator``, ``react-dev``, ``ts-dev``) receive
injections — research/plan agents are skipped so the researcher's
own findings don't get threaded back into itself.

Unmatched findings are preserved in a top-level ``notes`` array on
the plan — never silently discarded (per the F4 brief).

The script is also importable via
``scripts.hydrate_context_excerpts.hydrate(...)`` so
``orchestrator.meta_prompter`` can call it in-process after
``plan_for()``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("soup.scripts.hydrate_context_excerpts")

# Agents that receive hydrated excerpts. Everything else is skipped —
# research/plan/QA agents don't want their OWN findings threaded back in.
_IMPLEMENTING_AGENTS: frozenset[str] = frozenset(
    {
        "python-dev",
        "dotnet-dev",
        "ts-dev",
        "react-dev",
        "implementer",
        "test-engineer",
        "full-stack-integrator",
        "sql-specialist",
    }
)

# Accept both ASCII "-" and unicode em/en dash in the relevance column.
_RELEVANCE_PRIMARY_RE = re.compile(
    r"^\s*primary(?:\s*[\u2014\u2013-].*)?$",
    flags=re.IGNORECASE,
)


@dataclass
class Finding:
    """One row from the researcher findings table."""

    file: str
    line: str
    relevance: str
    excerpt: str = ""

    @property
    def is_primary(self) -> bool:
        """True if the row's relevance column starts with 'primary'."""
        return bool(_RELEVANCE_PRIMARY_RE.match(self.relevance.strip()))

    def as_context_entry(self) -> str:
        """Render as a single ``context_excerpts`` string.

        Uses the ``path:line_from-line_to`` form when ``line`` parses
        as a range, else falls back to the bare path.
        """
        line = self.line.strip().strip("`")
        if re.match(r"^\d+\s*-\s*\d+$", line):
            # normalise any spaces around the dash
            compact = re.sub(r"\s+", "", line)
            return f"{self.file}:{compact}"
        if line.isdigit():
            return f"{self.file}:{line}-{line}"
        return self.file


@dataclass
class HydrationResult:
    """Return value from :func:`hydrate`."""

    plan: dict[str, Any]
    steps_hydrated: int = 0
    excerpts_added: int = 0
    unmatched: list[Finding] = field(default_factory=list)


# ---------- parsing --------------------------------------------------------


def parse_findings(text: str) -> list[Finding]:
    """Parse a researcher findings markdown table into a list of Findings.

    The parser finds the first 4-column pipe-separated markdown table
    whose header row matches ``| File | Line | Relevance | Excerpt |``
    (case-insensitive), then reads every subsequent row until the
    first blank line or non-pipe line.

    Rows with only dashes (the markdown separator row) are skipped.
    """
    lines = text.splitlines()
    in_table = False
    findings: list[Finding] = []
    header_cols = ("file", "line", "relevance", "excerpt")

    for raw_line in lines:
        line = raw_line.strip()
        if not line or not line.startswith("|"):
            if in_table:
                # Blank or non-pipe line → table ended
                in_table = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not in_table:
            # Looking for a header row.
            lower = [c.lower().strip(" `") for c in cells]
            if len(lower) >= 4 and all(col in " ".join(lower) for col in header_cols):
                in_table = True
            continue
        # We're inside a table.
        if all(set(c) <= {"-", ":", " "} for c in cells):
            # markdown separator
            continue
        if len(cells) < 3:
            continue
        file_col = cells[0].strip().strip("`")
        if not file_col or file_col in ("—", "-"):
            continue
        line_col = cells[1].strip().strip("`") if len(cells) > 1 else ""
        relevance = cells[2].strip() if len(cells) > 2 else ""
        excerpt = cells[3].strip().strip("`") if len(cells) > 3 else ""
        findings.append(
            Finding(
                file=file_col,
                line=line_col,
                relevance=relevance,
                excerpt=excerpt,
            )
        )
    return findings


# ---------- matching -------------------------------------------------------


def _finding_matches_step(finding: Finding, step: dict[str, Any]) -> bool:
    """Return True if ``finding.file`` matches any of ``step.files_allowed``.

    Fallbacks:
      - if ``files_allowed`` is empty, we DO NOT hydrate (it would be
        unbounded; the step explicitly declined scope).
      - if the finding's file column is missing, no match.
    """
    globs = step.get("files_allowed") or []
    if not globs:
        return False
    path = finding.file.strip()
    if not path:
        return False
    for glob in globs:
        # Accept both exact match and fnmatch glob.
        if path == glob:
            return True
        if fnmatch.fnmatch(path, glob):
            return True
        # Also match when a glob is ``dir/**`` and the file is under dir.
        if glob.endswith("/**") and path.startswith(glob[:-3]):
            return True
    return False


# ---------- core -----------------------------------------------------------


def hydrate(
    findings: list[Finding],
    plan: dict[str, Any],
    *,
    primary_only: bool = True,
) -> HydrationResult:
    """Populate ``context_excerpts`` on each implementing step.

    Args:
        findings: Parsed findings from the researcher report.
        plan: The plan dict (loaded via ``json.loads``) — mutated
            in-place AND returned via ``HydrationResult.plan``.
        primary_only: If True (default), only rows whose relevance
            starts with ``primary`` are injected. Secondary rows still
            appear as ``notes`` if they match a step's scope — they
            just don't inflate every step's prompt.

    Returns:
        HydrationResult summarising counts + any unmatched findings.
    """
    unmatched_set: set[tuple[str, str]] = {
        (f.file, f.line) for f in findings
    }
    excerpts_added = 0
    steps_hydrated_ids: set[str] = set()
    steps = plan.get("steps") or []

    for step in steps:
        if not isinstance(step, dict):
            continue
        agent = step.get("agent", "")
        if agent not in _IMPLEMENTING_AGENTS:
            continue
        existing = list(step.get("context_excerpts") or [])
        existing_lookup = set(existing)
        step_added = 0
        for f in findings:
            if primary_only and not f.is_primary:
                continue
            if not _finding_matches_step(f, step):
                continue
            entry = f.as_context_entry()
            if entry in existing_lookup:
                # Already threaded by a prior hydration pass; still counts
                # as matched so we don't drop it into notes.
                unmatched_set.discard((f.file, f.line))
                continue
            existing.append(entry)
            existing_lookup.add(entry)
            step_added += 1
            unmatched_set.discard((f.file, f.line))
        if step_added:
            step["context_excerpts"] = existing
            excerpts_added += step_added
            steps_hydrated_ids.add(str(step.get("id", "?")))

    # Carry unmatched findings forward as notes so they aren't lost.
    unmatched_findings = [
        f for f in findings if (f.file, f.line) in unmatched_set
    ]
    if unmatched_findings:
        notes = list(plan.get("notes") or [])
        for f in unmatched_findings:
            notes.append(
                f"unmatched finding: {f.file}:{f.line} "
                f"({f.relevance}) — no step's files_allowed matched"
            )
        plan["notes"] = notes

    return HydrationResult(
        plan=plan,
        steps_hydrated=len(steps_hydrated_ids),
        excerpts_added=excerpts_added,
        unmatched=unmatched_findings,
    )


def hydrate_files(
    findings_path: Path,
    plan_path: Path,
    *,
    output_path: Path | None = None,
    primary_only: bool = True,
) -> HydrationResult:
    """File-based wrapper around :func:`hydrate`.

    Reads the findings markdown + plan JSON, runs hydrate, and writes
    the hydrated plan JSON (by default to ``<plan>-hydrated.json``,
    overridden by ``output_path``).
    """
    findings_text = Path(findings_path).read_text(encoding="utf-8")
    findings = parse_findings(findings_text)
    plan_text = Path(plan_path).read_text(encoding="utf-8")
    plan = json.loads(plan_text)
    result = hydrate(findings, plan, primary_only=primary_only)
    target = output_path or plan_path.with_name(
        plan_path.stem + "-hydrated.json"
    )
    Path(target).write_text(
        json.dumps(result.plan, indent=2) + "\n", encoding="utf-8"
    )
    return result


# ---------- CLI ------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.hydrate_context_excerpts",
        description=(
            "Auto-populate TaskStep.context_excerpts from a researcher "
            "findings report. Unmatched findings become plan notes."
        ),
    )
    p.add_argument(
        "--findings",
        required=True,
        help="Path to the researcher findings markdown report.",
    )
    p.add_argument(
        "--plan",
        required=True,
        help="Path to the plan JSON (ExecutionPlan-shaped).",
    )
    p.add_argument(
        "--output",
        default=None,
        help=(
            "Optional output path (default: <plan>-hydrated.json). "
            "Writes JSON + a trailing newline."
        ),
    )
    p.add_argument(
        "--include-secondary",
        action="store_true",
        help=(
            "Also inject findings with relevance != 'primary'. Default "
            "is primary-only to keep step prompts focused."
        ),
    )
    return p


def _run_cli(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    findings_path = Path(args.findings)
    plan_path = Path(args.plan)
    if not findings_path.exists():
        sys.stderr.write(f"error: findings file not found: {findings_path}\n")
        return 2
    if not plan_path.exists():
        sys.stderr.write(f"error: plan file not found: {plan_path}\n")
        return 2
    try:
        result = hydrate_files(
            findings_path,
            plan_path,
            output_path=Path(args.output) if args.output else None,
            primary_only=not args.include_secondary,
        )
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"error: plan JSON is invalid: {exc}\n")
        return 2

    report = {
        "status": "ok",
        "steps_hydrated": result.steps_hydrated,
        "excerpts_added": result.excerpts_added,
        "unmatched_count": len(result.unmatched),
        "unmatched": [
            {
                "file": f.file,
                "line": f.line,
                "relevance": f.relevance,
            }
            for f in result.unmatched
        ],
    }
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(_run_cli())


__all__ = [
    "Finding",
    "HydrationResult",
    "hydrate",
    "hydrate_files",
    "parse_findings",
]
