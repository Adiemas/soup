"""Tests for the RAG subsystem.

Focus areas:
  - Chunker preserves fenced code blocks
  - Searcher renders citations
  - FilesystemSource walks a tmp dir
  - GithubRepoSource warns but doesn't crash without GITHUB_TOKEN
  - LightRagClient degrades gracefully when Postgres/lightrag unavailable
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rag.client import (
    Chunk,
    IngestReport,
    LightRagClient,
    RagUnavailable,
    Retrieval,
)
from rag.ingest import Ingester, chunk_text
from rag.search import Searcher
from rag.sources.filesystem import FilesystemSource
from rag.sources.github import GithubRepoSource

pytestmark = pytest.mark.asyncio


# ---------- chunker --------------------------------------------------------


def test_chunker_preserves_code_fences() -> None:
    text = (
        "# Heading\n"
        "\n"
        "Prose before.\n"
        "\n"
        "```python\n"
        "def long_func():\n"
        "    return 'code block'\n"
        "```\n"
        "\n"
        "Prose after.\n"
    )
    chunks = chunk_text(text, "example.md")
    assert chunks, "chunker produced zero chunks"
    # Every fence that opens in a chunk must also close in the same chunk.
    for c in chunks:
        opens = c.content.count("```")
        assert opens % 2 == 0, (
            f"chunk split a code fence ({opens} backtick runs):\n{c.content}"
        )
    joined = "".join(c.content for c in chunks)
    assert "def long_func()" in joined


def test_chunker_emits_spans_and_source_path() -> None:
    chunks = chunk_text("hello\nworld\n", "docs/intro.md")
    assert all(c.source_path == "docs/intro.md" for c in chunks)
    assert all("-" in c.span for c in chunks)


def test_chunk_hash_is_stable_and_unique() -> None:
    a = Chunk(content="abc", source_path="f.md", span="1-2")
    b = Chunk(content="abc", source_path="f.md", span="1-2")
    c = Chunk(content="abd", source_path="f.md", span="1-2")
    assert a.hash() == b.hash()
    assert a.hash() != c.hash()


# ---------- retrieval / searcher ------------------------------------------


class _StubClient:
    """Enough of LightRagClient's surface for the searcher tests."""

    def __init__(self, results: list[Retrieval]) -> None:
        self._results = results

    async def search(
        self, query: str, *, mode: str = "hybrid", top_k: int = 8
    ) -> list[Retrieval]:
        return self._results


async def test_searcher_ensures_citation() -> None:
    raw = Retrieval(
        content="The API deploys via pipeline X.",
        source_path="wiki/deploy.md",
        span="10-20",
        score=0.87,
        citation="",  # deliberately blank
    )
    searcher = Searcher(client=_StubClient([raw]))  # type: ignore[arg-type]
    out = await searcher.search("how do we deploy?")
    assert out[0].citation == "[source:wiki/deploy.md#10-20]"


async def test_searcher_renders_markdown_with_citations() -> None:
    r = Retrieval.build(
        content="Alpha",
        source_path="x.md",
        span="1-3",
        score=0.9,
    )
    searcher = Searcher(client=_StubClient([r]))  # type: ignore[arg-type]
    md = await searcher.search_markdown("alpha?")
    assert "# RAG: alpha?" in md
    assert "[source:x.md#1-3]" in md
    assert "Alpha" in md


def test_citation_format_canonical() -> None:
    """Canonical citation format is ``[source:<path>#<span>]``.

    iter-3 P12/L2 canonicalisation: every ``Retrieval`` emitted via
    ``Retrieval.build`` (and backfilled via ``Searcher._ensure_citation``)
    must carry the ``source:`` prefix. Downstream validators (CLAUDE.md
    iron law 6, the ``agentic-rag-research`` skill) grep for the exact
    prefix — dropping it is a breaking change.
    """
    # 1. Retrieval.build() stamps the canonical shape.
    r = Retrieval.build(content="hi", source_path="a/b.md", span="1-2")
    assert r.citation == "[source:a/b.md#1-2]"
    assert r.citation.startswith("[source:")

    # 2. The build fallback preserves special prefixes (github://, etc.)
    gh = Retrieval.build(
        content="x",
        source_path="github://streck/auth/src/lib/jwt.py",
        span="42-58",
    )
    assert gh.citation == "[source:github://streck/auth/src/lib/jwt.py#42-58]"

    # 3. ``Searcher._ensure_citation`` fills a blank citation with the
    #    canonical form — not the legacy ``[path#span]``.
    blank = Retrieval(
        content="x",
        source_path="specs/auth.md",
        span="0-0",
        citation="",
    )
    filled = Searcher._ensure_citation(blank)
    assert filled.citation == "[source:specs/auth.md#0-0]"

    # 4. Normalised response from a LightRAG dict payload also uses
    #    the canonical prefix.
    norm = LightRagClient._normalize_response(
        {
            "response": "ok",
            "references": [
                {
                    "file_path": "wiki/deploy.md",
                    "span": "10-20",
                    "score": 0.5,
                    "content": "body",
                }
            ],
        }
    )
    assert norm[0].citation == "[source:wiki/deploy.md#10-20]"


async def test_searcher_no_results_markdown() -> None:
    searcher = Searcher(client=_StubClient([]))  # type: ignore[arg-type]
    md = await searcher.search_markdown("nothing?")
    assert "_No results._" in md


def test_normalize_response_from_dict_with_references() -> None:
    raw = {
        "response": "answer",
        "references": [
            {
                "file_path": "docs/a.md",
                "span": "5-10",
                "score": 0.75,
                "content": ["First chunk.", "Second chunk."],
            }
        ],
    }
    out = LightRagClient._normalize_response(raw)
    assert len(out) == 1
    assert out[0].citation == "[source:docs/a.md#5-10]"
    assert "First chunk." in out[0].content
    assert "Second chunk." in out[0].content


def test_normalize_response_from_plain_string() -> None:
    out = LightRagClient._normalize_response("just text")
    assert out and out[0].content == "just text"
    assert out[0].source_path == "<llm-answer>"


# ---------- FilesystemSource ----------------------------------------------


async def test_filesystem_source_yields_chunks(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text(
        "# Hi\n\n```python\nx = 1\n```\n", encoding="utf-8"
    )
    (tmp_path / "mod.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02")  # ignored (not matched)

    source = FilesystemSource(root=tmp_path)
    chunks = [c async for c in source.iter_chunks()]

    paths = {c.source_path for c in chunks}
    assert "doc.md" in paths
    assert "mod.py" in paths
    # Source uri uses posix form of the resolved path
    assert source.uri.startswith("file://")


async def test_filesystem_source_respects_ignore_globs(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (tmp_path / "keep.md").write_text("# keep\n", encoding="utf-8")
    source = FilesystemSource(root=tmp_path)
    paths = {c.source_path async for c in source.iter_chunks()}
    assert "keep.md" in paths
    assert not any(".git" in p for p in paths)


# ---------- GithubRepoSource ----------------------------------------------


async def test_github_source_missing_token_logs_warning(caplog) -> None:
    """No token + no network: still constructs headers and logs a warning."""
    caplog.set_level("WARNING")
    prior = os.environ.pop("GITHUB_TOKEN", None)
    try:
        source = GithubRepoSource(owner="streck", repo="test")
        headers = source._headers()
        assert "Authorization" not in headers
        assert any("GITHUB_TOKEN" in rec.message for rec in caplog.records)
    finally:
        if prior is not None:
            os.environ["GITHUB_TOKEN"] = prior


def test_github_source_uri_form() -> None:
    source = GithubRepoSource(owner="o", repo="r", branch="feat")
    assert source.uri == "github://o/r@feat"
    assert source._is_text("docs/intro.md")
    assert not source._is_text("assets/logo.png")


# ---------- LightRagClient graceful degradation ---------------------------


async def test_client_search_raises_when_backend_unavailable(tmp_path: Path) -> None:
    client = LightRagClient(
        working_dir=str(tmp_path / "rag"),
        postgres_url=None,
        llm_provider="anthropic",
    )
    # Force the 'LightRAG unavailable' path without touching the real library.
    client._initialized = True
    client._rag = None
    with pytest.raises(RagUnavailable):
        await client.search("anything")


async def test_client_ingest_reports_unavailable(tmp_path: Path) -> None:
    client = LightRagClient(working_dir=str(tmp_path / "rag"))
    client._initialized = True
    client._rag = None

    class _Src:
        uri = "inline://test"

        async def iter_chunks(self):
            yield Chunk(content="hello world", source_path="t.md", span="1-1")

    report = await client.ingest(_Src())
    assert isinstance(report, IngestReport)
    assert report.chunks_seen == 1
    assert report.chunks_inserted == 0
    assert any("rag-unavailable" in e for e in report.errors)


async def test_ingester_inline_chunks(tmp_path: Path) -> None:
    client = LightRagClient(working_dir=str(tmp_path / "rag"))
    client._initialized = True
    client._rag = None  # force unavailable path
    ingester = Ingester(client=client)
    chunks = [
        Chunk(content="one", source_path="x.md", span="1-1"),
        Chunk(content="two", source_path="x.md", span="2-2"),
    ]
    report = await ingester.ingest_chunks(chunks, source_uri="inline://test")
    assert report.chunks_seen == 2


def test_build_source_dispatch(tmp_path: Path) -> None:
    client = LightRagClient(working_dir=str(tmp_path / "rag"))
    ingester = Ingester(client=client)
    from rag.sources import (
        AdoWikiSource,
        AdoWorkItemsSource,
        FilesystemSource,
        GithubRepoSource,
        WebDocsSource,
    )

    assert isinstance(ingester.build_source(str(tmp_path)), FilesystemSource)
    assert isinstance(
        ingester.build_source("github://o/r@main"), GithubRepoSource
    )
    assert isinstance(
        ingester.build_source("ado://org/project/wikiId"), AdoWikiSource
    )
    assert isinstance(
        ingester.build_source("ado-wi://streck/Platform/482"),
        AdoWorkItemsSource,
    )
    assert isinstance(
        ingester.build_source("https://example.com/docs"), WebDocsSource
    )
    with pytest.raises(ValueError):
        ingester.build_source("weird-scheme://foo")


# ---------- AdoWorkItemsSource --------------------------------------------


async def test_ado_work_items_missing_pat_warns_returns_empty(caplog) -> None:
    """F6: stub-safe — no PAT, no crash. Returns zero chunks + a warning."""
    from rag.sources.ado_work_items import AdoWorkItemsSource

    caplog.set_level("WARNING")
    # Ensure no ADO_PAT / AZURE_DEVOPS_PAT env leaks into the test.
    prior = {
        k: os.environ.pop(k, None)
        for k in ("ADO_PAT", "AZURE_DEVOPS_PAT", "AZURE_DEVOPS_EXT_PAT")
    }
    try:
        source = AdoWorkItemsSource(
            org="streck", project="Platform", query="482"
        )
        chunks = [c async for c in source.iter_chunks()]
        assert chunks == []
        assert any("ADO_PAT" in rec.message for rec in caplog.records)
    finally:
        for k, v in prior.items():
            if v is not None:
                os.environ[k] = v


def test_ado_work_items_uri_shape() -> None:
    from rag.sources.ado_work_items import AdoWorkItemsSource

    src = AdoWorkItemsSource(org="streck", project="Platform", query="482")
    assert src.uri == "ado-wi://streck/Platform/482"


def test_ado_work_items_wiql_wrapper() -> None:
    """A bare filter clause is wrapped as a minimal WIQL statement."""
    from rag.sources.ado_work_items import AdoWorkItemsSource

    wrapped = AdoWorkItemsSource._wrap_as_wiql(
        "[System.State] = 'Active'"
    )
    assert wrapped.startswith("SELECT [System.Id] FROM WorkItems WHERE")
    assert "[System.State] = 'Active'" in wrapped
    # Empty filter → bare SELECT.
    assert AdoWorkItemsSource._wrap_as_wiql("").upper().startswith(
        "SELECT"
    )


async def test_ado_work_items_single_id_fetch(monkeypatch) -> None:
    """Single-ID URI goes through the direct work-item endpoint.

    Mocks ``httpx.AsyncClient`` so the adapter exercises its render
    path end-to-end without network.
    """
    from rag.sources import ado_work_items as aw_mod

    monkeypatch.setenv("ADO_PAT", "test-pat")

    class _FakeResp:
        def __init__(self, payload: dict):
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class _FakeClient:
        def __init__(self, *a, **kw):
            self._gets: list[str] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url: str, **kwargs):
            self._gets.append(url)
            lower = url.lower()
            if "/comments" in lower:
                return _FakeResp(
                    {
                        "comments": [
                            {
                                "text": "Looks good",
                                "createdBy": {"displayName": "alice"},
                                "createdDate": "2026-04-14T10:00:00Z",
                            }
                        ]
                    }
                )
            if "/workitems/482" in lower:
                return _FakeResp(
                    {
                        "id": 482,
                        "fields": {
                            "System.Title": "Test WI",
                            "System.State": "Active",
                            "System.WorkItemType": "Task",
                            "System.Description": "Do the thing",
                            "Microsoft.VSTS.Common.AcceptanceCriteria": "Works",
                        },
                    }
                )
            return _FakeResp({})

        async def post(self, url: str, **kwargs):
            # Not used on single-id path but kept for completeness.
            return _FakeResp({"workItems": []})

    monkeypatch.setattr(aw_mod.httpx, "AsyncClient", _FakeClient)

    source = aw_mod.AdoWorkItemsSource(
        org="streck", project="Platform", query="482"
    )
    chunks = [c async for c in source.iter_chunks()]
    assert chunks, "single-id fetch produced zero chunks"
    blob = "\n".join(c.content for c in chunks)
    assert "Test WI" in blob
    assert "Do the thing" in blob
    assert "Works" in blob
    assert "alice" in blob
    # Each chunk has the ado-wi source path.
    assert all(
        c.source_path.startswith("ado-wi://streck/Platform/482")
        for c in chunks
    )


async def test_ado_work_items_wiql_parses_ids(monkeypatch) -> None:
    """WIQL mode: POST wiql endpoint and fan out to work-item fetches."""
    from rag.sources import ado_work_items as aw_mod

    monkeypatch.setenv("ADO_PAT", "test-pat")

    class _FakeResp:
        def __init__(self, payload: dict):
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    fetched: list[int] = []

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url: str, **kwargs):
            assert "/wiql" in url
            return _FakeResp({"workItems": [{"id": 1}, {"id": 2}]})

        async def get(self, url: str, **kwargs):
            if "/workitems/" in url.lower() and "/comments" not in url.lower():
                wi_id = int(url.rsplit("/workitems/", 1)[1].split("?", 1)[0])
                fetched.append(wi_id)
                return _FakeResp(
                    {
                        "id": wi_id,
                        "fields": {
                            "System.Title": f"wi-{wi_id}",
                            "System.State": "Active",
                            "System.WorkItemType": "Task",
                        },
                    }
                )
            return _FakeResp({"comments": []})

    monkeypatch.setattr(aw_mod.httpx, "AsyncClient", _FakeClient)

    src = aw_mod.AdoWorkItemsSource(
        org="streck",
        project="Platform",
        query="SELECT [System.Id] FROM WorkItems WHERE [System.State] = 'Active'",
    )
    chunks = [c async for c in src.iter_chunks()]
    # Both IDs fetched.
    assert sorted(fetched) == [1, 2]
    assert chunks


def test_ado_work_items_exported_from_sources() -> None:
    """F6: the new class is re-exported so agents can import symmetrically."""
    from rag.sources import AdoWorkItemsSource as ReExported
    from rag.sources.ado_work_items import AdoWorkItemsSource

    assert ReExported is AdoWorkItemsSource
