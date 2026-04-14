"""Ingester — URI dispatch + boundary-preserving chunking.

The chunker splits markdown by headers and fenced code blocks, and source
code by blank-line-separated top-level blocks. Falls back to a sliding
window (approx. token count via tiktoken if available, otherwise by
characters) sized to 512-2048 tokens.

Also exposes a module-level ``ingest()`` sync-bridge function and a CLI:

    python -m rag.ingest --source <uri> [--dry-run] [--reindex-all]

The CLI emits a JSON report to stdout so agents and shell pipelines can
parse results without touching the Python API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from rag.client import Chunk, IngestReport, LightRagClient, RagUnavailable

if TYPE_CHECKING:
    from rag.sources import Source

logger = logging.getLogger("soup.rag.ingest")

# Token-window bounds from LightRAG guidance (512-2048 tokens).
MIN_TOKENS = 512
MAX_TOKENS = 2048
TARGET_TOKENS = 1024

# Very rough char-per-token fallback. Calibrated for English + code.
_CHARS_PER_TOKEN = 4

_FENCE_RE = re.compile(r"^(```|~~~)")
_MD_HEADER_RE = re.compile(r"^#{1,6}\s")
_PY_TOP_RE = re.compile(r"^(?:class |def |async def )")

# Windows drive-letter prefix at the start of a path (e.g. "C:\", "c:/").
_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _is_bare_fs_path(uri: str) -> bool:
    """True if ``uri`` looks like a bare filesystem path, not a URI.

    Recognises:
      - Windows drive-letter prefix: ``C:\\...`` or ``c:/...``
      - UNC path: ``\\\\server\\share``
      - POSIX rooted path: ``/...``
      - Backslash-rooted path: ``\\...``

    Excludes anything with a ``<scheme>://`` separator (those are URIs).
    """
    if not uri:
        return False
    if "://" in uri:
        return False
    if _WIN_DRIVE_RE.match(uri):
        return True
    if uri.startswith(("\\\\", "//")):
        # UNC path or POSIX double-slash root
        return True
    if uri.startswith(("/", "\\")):
        return True
    return False


def _count_tokens(text: str) -> int:
    """Return a (possibly approximate) token count."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class ChunkerConfig:
    min_tokens: int = MIN_TOKENS
    max_tokens: int = MAX_TOKENS
    target_tokens: int = TARGET_TOKENS


def chunk_text(
    text: str,
    source_path: str,
    *,
    config: ChunkerConfig | None = None,
    metadata: dict[str, str] | None = None,
) -> list[Chunk]:
    """Split text into chunks respecting code-fence and markdown boundaries.

    Invariants:
      - Fenced code blocks are never split across chunks.
      - Markdown headers start new chunks when possible.
      - Each chunk target ~1024 tokens; hard cap MAX_TOKENS.
    """
    cfg = config or ChunkerConfig()
    meta = dict(metadata or {})
    is_md = source_path.endswith((".md", ".markdown"))
    is_code = source_path.endswith(
        (".py", ".cs", ".ts", ".tsx", ".js", ".jsx", ".sql", ".java", ".go")
    )

    blocks = _split_into_blocks(text, is_markdown=is_md, is_code=is_code)
    return _pack_blocks(blocks, source_path, cfg, meta)


def _split_into_blocks(text: str, *, is_markdown: bool, is_code: bool) -> list[tuple[str, int]]:
    """Return (block_text, start_line_index) preserving code fences."""
    lines = text.splitlines(keepends=True)
    out: list[tuple[str, int]] = []
    buf: list[str] = []
    buf_start = 0
    in_fence = False

    def flush(end_marker_start: int) -> None:
        nonlocal buf, buf_start
        if buf:
            joined = "".join(buf)
            if joined.strip():
                out.append((joined, buf_start))
            buf = []
        buf_start = end_marker_start

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if _FENCE_RE.match(stripped):
            if in_fence:
                # Closing fence — include line in current buffer, then flush.
                buf.append(line)
                flush(i + 1)
                in_fence = False
                continue
            # Opening fence — flush any buffered prose first.
            flush(i)
            buf.append(line)
            buf_start = i
            in_fence = True
            continue
        if in_fence:
            buf.append(line)
            continue
        # Section boundary heuristics (not in a code fence)
        if is_markdown and _MD_HEADER_RE.match(stripped) and buf:
            flush(i)
        elif is_code and _PY_TOP_RE.match(stripped) and buf and not stripped.startswith("    "):
            flush(i)
        buf.append(line)

    flush(len(lines))
    return out


def _pack_blocks(
    blocks: list[tuple[str, int]],
    source_path: str,
    cfg: ChunkerConfig,
    metadata: dict[str, str],
) -> list[Chunk]:
    """Greedy-pack consecutive blocks up to the target token count.

    Large single blocks (e.g. huge code fences) are emitted as-is even if
    they exceed MAX_TOKENS, to preserve entity boundaries.
    """
    chunks: list[Chunk] = []
    cur_lines: list[str] = []
    cur_start: int | None = None
    cur_tokens = 0
    cur_end = 0

    def emit() -> None:
        nonlocal cur_lines, cur_start, cur_tokens, cur_end
        if not cur_lines:
            return
        body = "".join(cur_lines)
        span = f"{(cur_start or 0) + 1}-{cur_end}"
        chunks.append(
            Chunk(
                content=body,
                source_path=source_path,
                span=span,
                metadata=dict(metadata),
            )
        )
        cur_lines = []
        cur_start = None
        cur_tokens = 0

    for body, start in blocks:
        btok = _count_tokens(body)
        line_count = body.count("\n") or 1
        if cur_tokens and cur_tokens + btok > cfg.max_tokens:
            emit()
        if cur_start is None:
            cur_start = start
        cur_lines.append(body)
        cur_tokens += btok
        cur_end = start + line_count
        if cur_tokens >= cfg.target_tokens:
            emit()

    emit()
    return chunks


# ---------- Ingester --------------------------------------------------------


@dataclass
class Ingester:
    """High-level ingest orchestrator.

    Picks an adapter based on URI scheme, streams chunks, and delegates to
    ``LightRagClient.ingest``. Safe to re-run on the same URI (dedup via
    the client's hash set and LightRAG's internal content hashing).
    """

    client: LightRagClient
    config: ChunkerConfig = field(default_factory=ChunkerConfig)

    async def ingest_uri(self, uri: str, **source_kwargs: Any) -> IngestReport:
        source = self.build_source(uri, **source_kwargs)
        return await self.client.ingest(source)

    async def ingest_chunks(
        self,
        chunks: Iterable[Chunk],
        *,
        source_uri: str = "inline",
    ) -> IngestReport:
        inline = _InlineSource(uri=source_uri, chunks=list(chunks))
        return await self.client.ingest(inline)

    def build_source(self, uri: str, **kwargs: Any) -> "Source":
        from rag import sources

        # Treat bare filesystem paths (Windows drive-letter prefix like
        # "C:\..." / "c:/...", or rooted POSIX paths "/...", or UNC "\\...")
        # as filesystem sources WITHOUT urlparse — otherwise urlparse sees
        # "C:" as a URI scheme and mangles the path.
        if _is_bare_fs_path(uri):
            return sources.FilesystemSource(root=uri, **kwargs)

        parsed = urlparse(uri)
        scheme = parsed.scheme.lower() or "file"

        if scheme in ("file", "fs", ""):
            root = parsed.path or uri
            if root.startswith("/") and len(root) >= 3 and root[2] == ":":
                # Windows path like /C:/... — strip leading slash
                root = root[1:]
            return sources.FilesystemSource(root=root, **kwargs)
        if scheme in ("github", "gh"):
            # github://owner/repo[@branch]
            host = parsed.netloc
            path = parsed.path.lstrip("/")
            owner, _, repo_branch = (host + "/" + path).partition("/")
            repo, _, branch = repo_branch.partition("@")
            return sources.GithubRepoSource(
                owner=owner, repo=repo, branch=branch or "main", **kwargs
            )
        if scheme in ("ado", "adowiki"):
            # ado://org/project[/wiki]
            org = parsed.netloc
            parts = parsed.path.lstrip("/").split("/")
            project = parts[0] if parts else ""
            wiki = parts[1] if len(parts) > 1 else None
            return sources.AdoWikiSource(
                org=org, project=project, wiki_id=wiki, **kwargs
            )
        if scheme in ("ado-wi", "adowi"):
            # ado-wi://org/project/<id-or-query>
            # ``query`` may be a numeric ID, a URL-encoded WIQL, or a
            # filter clause (see AdoWorkItemsSource._resolve_ids).
            org = parsed.netloc
            path = parsed.path.lstrip("/")
            parts = path.split("/", 1)
            project = parts[0] if parts else ""
            query = parts[1] if len(parts) > 1 else ""
            # ``?wiql=...`` convention also supported.
            if not query and parsed.query:
                # Prefer a ``wiql=`` param if present.
                from urllib.parse import parse_qs

                q = parse_qs(parsed.query).get("wiql")
                if q:
                    query = q[0]
            return sources.AdoWorkItemsSource(
                org=org, project=project, query=query, **kwargs
            )
        if scheme in ("http", "https", "web"):
            return sources.WebDocsSource(url_list=[uri], **kwargs)
        raise ValueError(f"Unknown source URI scheme: {scheme!r}")


@dataclass
class _InlineSource:
    uri: str
    chunks: list[Chunk]

    async def iter_chunks(self) -> AsyncIterator[Chunk]:
        for c in self.chunks:
            yield c


# ---------- module-level bridge functions ---------------------------------


async def _ingest_async(
    source: str,
    *,
    dry_run: bool = False,
    tags: list[str] | None = None,
    client: LightRagClient | None = None,
) -> IngestReport:
    """Async implementation shared by sync bridge and CLI."""
    rag_client = client or LightRagClient.from_env()
    try:
        ingester = Ingester(client=rag_client)
        if dry_run:
            # Build the source, iterate chunks, count — but do not persist.
            src = ingester.build_source(source)
            report = IngestReport(source_uri=getattr(src, "uri", source))
            async for _chunk in src.iter_chunks():
                report.chunks_seen += 1
            return report
        kwargs: dict[str, Any] = {}
        if tags:
            kwargs["tags"] = tags
        return await ingester.ingest_uri(source, **kwargs)
    finally:
        if client is None:
            await rag_client.close()


def ingest(
    source: str,
    *,
    dry_run: bool = False,
    tags: list[str] | None = None,
) -> IngestReport:
    """Sync bridge over ``Ingester.ingest_uri``.

    Constructs a ``LightRagClient`` from env (``POSTGRES_URL`` /
    ``DATABASE_URL``), runs the async ingest on a fresh event loop, and
    returns the resulting ``IngestReport``. Used by ``orchestrator.cli
    ingest`` and by scripts that cannot manage their own loop.

    Raises:
        RagUnavailable: if the LightRAG backend cannot be reached.
    """
    return asyncio.run(_ingest_async(source, dry_run=dry_run, tags=tags))


# ---------- CLI -----------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rag.ingest",
        description=(
            "Ingest a source into the soup RAG pipeline and emit a JSON "
            "report to stdout."
        ),
    )
    parser.add_argument(
        "--source",
        "-s",
        required=False,
        default=None,
        help=(
            "Source URI: github://owner/repo[@branch], ado://org/project, "
            "file://path, https://..."
        ),
    )
    parser.add_argument(
        "--tags",
        default=None,
        help="Comma-separated tags for metadata.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Iterate chunks but do not write to the backend.",
    )
    parser.add_argument(
        "--reindex-all",
        action="store_true",
        help="Re-run ingest against every source currently known to the backend.",
    )
    return parser


async def _reindex_all_async() -> list[IngestReport]:
    client = LightRagClient.from_env()
    reports: list[IngestReport] = []
    try:
        sources = await client.list_sources()
        if not sources:
            return reports
        ingester = Ingester(client=client)
        for uri in sources:
            try:
                reports.append(await ingester.ingest_uri(uri))
            except Exception as exc:  # pragma: no cover — per-source defensive
                reports.append(
                    IngestReport(source_uri=uri, errors=[repr(exc)])
                )
    finally:
        await client.close()
    return reports


def _run_cli(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.reindex_all:
        try:
            reports = asyncio.run(_reindex_all_async())
        except RagUnavailable as exc:
            sys.stdout.write(
                json.dumps(
                    {"status": "unavailable", "error": str(exc), "reports": []},
                    indent=2,
                )
                + "\n"
            )
            return 2
        payload = {
            "status": "ok",
            "mode": "reindex-all",
            "reports": [r.model_dump() for r in reports],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0 if all(not r.errors for r in reports) else 1

    if not args.source:
        sys.stderr.write(
            "error: --source is required (unless --reindex-all)\n"
        )
        return 2

    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    try:
        report = ingest(args.source, dry_run=args.dry_run, tags=tags)
    except RagUnavailable as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "status": "unavailable",
                    "source": args.source,
                    "error": str(exc),
                },
                indent=2,
            )
            + "\n"
        )
        return 2
    except Exception as exc:  # pragma: no cover — defensive
        sys.stdout.write(
            json.dumps(
                {
                    "status": "error",
                    "source": args.source,
                    "error": repr(exc),
                },
                indent=2,
            )
            + "\n"
        )
        return 2

    payload = {
        "status": "ok",
        "mode": "dry-run" if args.dry_run else "ingest",
        "report": report.model_dump(),
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(_run_cli())
