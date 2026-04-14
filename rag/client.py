"""LightRAG client wrapper.

Thin, typed async facade over the ``lightrag-hku`` Python library so the
rest of the framework can talk to a single object. Graceful-degrades when
LightRAG or Postgres are unavailable (logs warning, raises ``RagUnavailable``
on call) so tests can still import the module.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger("soup.rag.client")

SearchMode = Literal["hybrid", "vector", "graph"]
"""Soup-level mode; translated to LightRAG's richer mode set internally."""

_MODE_MAP: dict[SearchMode, str] = {
    # hybrid → LightRAG "mix" blends KG + vector; closest to our intent
    "hybrid": "mix",
    # vector-only ≈ LightRAG "naive" (pure similarity search)
    "vector": "naive",
    # graph traversal ≈ LightRAG "global"
    "graph": "global",
}


class RagUnavailable(RuntimeError):
    """Raised when a LightRAG call is attempted but the backend isn't usable."""


# ---------- data models -----------------------------------------------------


class Chunk(BaseModel):
    """A single normalized chunk ready for ingestion."""

    content: str
    source_path: str
    span: str = "0-0"  # "line_start-line_end" or "byte_start-byte_end"
    metadata: dict[str, str] = Field(default_factory=dict)

    def hash(self) -> str:
        """Stable sha1 of (source_path, span, content) — used for dedup."""
        h = hashlib.sha1()  # noqa: S324 — not security-critical
        h.update(self.source_path.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.span.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.content.encode("utf-8"))
        return h.hexdigest()


class Retrieval(BaseModel):
    """A single retrieval hit, with a pre-rendered citation tag.

    Citation format is canonical ``[source:<path>#<span>]`` (iter-2
    dogfood P12 / L2 canonicalisation). This matches DESIGN §1 tenet
    10, CLAUDE.md iron law 6, CONSTITUTION.md VII.3, and the
    ``agentic-rag-research`` skill rule. Downstream citation-required
    validators should check the ``[source:`` prefix.
    """

    content: str
    source_path: str
    span: str = "0-0"
    score: float = 0.0
    citation: str = ""  # "[source:path#span]" — canonical format

    @classmethod
    def build(
        cls,
        *,
        content: str,
        source_path: str,
        span: str = "0-0",
        score: float = 0.0,
    ) -> "Retrieval":
        cite = f"[source:{source_path}#{span}]"
        return cls(
            content=content,
            source_path=source_path,
            span=span,
            score=score,
            citation=cite,
        )


class IngestReport(BaseModel):
    """Summary of a single ingest() call."""

    source_uri: str
    chunks_seen: int = 0
    chunks_inserted: int = 0
    chunks_skipped_duplicate: int = 0
    errors: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.source_uri}: {self.chunks_inserted}/{self.chunks_seen} "
            f"inserted, {self.chunks_skipped_duplicate} dupes, "
            f"{len(self.errors)} errors"
        )


@runtime_checkable
class _SourceLike(Protocol):
    """Structural interface matched by ``rag.sources.Source``."""

    uri: str

    def iter_chunks(self) -> AsyncIterator[Chunk]: ...


# ---------- client ----------------------------------------------------------


@dataclass
class LightRagClient:
    """Async facade around ``LightRAG`` with Postgres-backed storage.

    The real LightRAG instance is lazily created on first ``ingest``/``search``
    call so tests can construct clients without a live Postgres.
    """

    working_dir: str
    postgres_url: str | None = None
    llm_provider: str = "anthropic"
    workspace: str = "soup"
    _rag: Any = field(default=None, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)
    _seen_hashes: set[str] = field(default_factory=set, init=False, repr=False)

    @classmethod
    def from_env(
        cls,
        working_dir: str | os.PathLike[str] = "./.soup/rag_storage",
        *,
        llm_provider: str = "anthropic",
    ) -> "LightRagClient":
        """Construct using ``POSTGRES_URL`` / ``DATABASE_URL`` env vars."""
        url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL")
        return cls(
            working_dir=str(working_dir),
            postgres_url=url,
            llm_provider=llm_provider,
        )

    # ---- lifecycle --------------------------------------------------------

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        Path(self.working_dir).mkdir(parents=True, exist_ok=True)
        self._apply_postgres_env()
        try:
            self._rag = await self._build_lightrag()
        except Exception as exc:  # pragma: no cover — exercised via tests
            logger.warning(
                "LightRAG unavailable (%s); client will raise on use", exc
            )
            self._rag = None
        self._initialized = True

    async def close(self) -> None:
        if self._rag is not None:
            finalize = getattr(self._rag, "finalize_storages", None)
            if finalize is not None:
                try:
                    await finalize()
                except Exception as exc:  # pragma: no cover
                    logger.warning("finalize_storages failed: %s", exc)
        self._rag = None
        self._initialized = False

    def _apply_postgres_env(self) -> None:
        """Translate ``postgres_url`` → LightRAG env-var expectations."""
        if not self.postgres_url:
            return
        m = re.match(
            r"postgres(?:ql)?://(?P<user>[^:]+):(?P<pw>[^@]+)@"
            r"(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<db>[^?]+)",
            self.postgres_url,
        )
        if not m:
            logger.warning("POSTGRES_URL not recognized: %s", self.postgres_url)
            return
        os.environ.setdefault("POSTGRES_HOST", m.group("host"))
        os.environ.setdefault("POSTGRES_PORT", m.group("port") or "5432")
        os.environ.setdefault("POSTGRES_USER", m.group("user"))
        os.environ.setdefault("POSTGRES_PASSWORD", m.group("pw"))
        os.environ.setdefault("POSTGRES_DATABASE", m.group("db"))
        os.environ.setdefault("POSTGRES_WORKSPACE", self.workspace)

    async def _build_lightrag(self) -> Any:
        """Construct the underlying LightRAG instance."""
        # Local import so module loads even if lightrag-hku isn't installed.
        from lightrag import LightRAG  # type: ignore[import-not-found]

        llm_func = self._pick_llm_func()
        embed_func = self._pick_embedding_func()

        kwargs: dict[str, Any] = {
            "working_dir": self.working_dir,
            "workspace": self.workspace,
            "llm_model_func": llm_func,
            "embedding_func": embed_func,
        }
        if self.postgres_url:
            kwargs.update(
                kv_storage="PGKVStorage",
                vector_storage="PGVectorStorage",
                doc_status_storage="PGDocStatusStorage",
                graph_storage="PGGraphStorage",
            )
        rag = LightRAG(**kwargs)
        await rag.initialize_storages()
        return rag

    def _pick_llm_func(self) -> Any:
        """Return a LightRAG-compatible ``llm_model_func`` callable."""
        if self.llm_provider == "anthropic":
            return _anthropic_complete
        # Fallback: openai (lightrag ships with a ready-made helper)
        from lightrag.llm.openai import gpt_4o_mini_complete  # type: ignore[import-not-found]

        return gpt_4o_mini_complete

    def _pick_embedding_func(self) -> Any:
        """Return a LightRAG embedding func. OpenAI by default."""
        try:
            from lightrag.llm.openai import openai_embed  # type: ignore[import-not-found]
            from lightrag.utils import EmbeddingFunc  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover
            raise RagUnavailable(f"lightrag-hku not installed: {exc}") from exc

        return EmbeddingFunc(
            embedding_dim=1536,
            max_token_size=8192,
            func=openai_embed,
        )

    # ---- public API -------------------------------------------------------

    async def ingest(
        self,
        source: _SourceLike,
        chunks: Iterable[Chunk] | None = None,
    ) -> IngestReport:
        """Ingest a source (or a pre-materialized chunk iterable).

        Dedup is by ``Chunk.hash()``; duplicates within this client lifetime
        are skipped. For cross-session dedup LightRAG itself deduplicates
        on doc content hash.
        """
        await self._ensure_initialized()
        report = IngestReport(source_uri=getattr(source, "uri", "unknown"))

        async def _iterator() -> AsyncIterator[Chunk]:
            if chunks is not None:
                for c in chunks:
                    yield c
                return
            async for c in source.iter_chunks():
                yield c

        batch: list[str] = []
        batch_meta: list[dict[str, str]] = []
        async for chunk in _iterator():
            report.chunks_seen += 1
            digest = chunk.hash()
            if digest in self._seen_hashes:
                report.chunks_skipped_duplicate += 1
                continue
            self._seen_hashes.add(digest)
            batch.append(chunk.content)
            batch_meta.append(
                {
                    "file_path": chunk.source_path,
                    "span": chunk.span,
                    **chunk.metadata,
                }
            )

        if not batch:
            return report

        if self._rag is None:
            report.errors.append("rag-unavailable: lightrag not initialized")
            return report

        try:
            await self._rag.ainsert(batch, file_paths=[m["file_path"] for m in batch_meta])
            report.chunks_inserted = len(batch)
        except TypeError:
            # Older API signatures — fall back without kwargs.
            try:
                await self._rag.ainsert(batch)
                report.chunks_inserted = len(batch)
            except Exception as exc:  # pragma: no cover
                report.errors.append(f"ainsert failed: {exc}")
        except Exception as exc:  # pragma: no cover
            report.errors.append(f"ainsert failed: {exc}")
        return report

    async def search(
        self,
        query: str,
        *,
        mode: SearchMode = "hybrid",
        top_k: int = 8,
    ) -> list[Retrieval]:
        """Run a query and return normalized ``Retrieval`` rows."""
        await self._ensure_initialized()
        if self._rag is None:
            raise RagUnavailable("LightRAG backend not initialized")

        lightrag_mode = _MODE_MAP[mode]
        from lightrag import QueryParam  # type: ignore[import-not-found]

        param = QueryParam(
            mode=lightrag_mode,
            top_k=top_k,
            include_references=True,
        )
        raw = await self._rag.aquery(query, param=param)
        return self._normalize_response(raw)

    async def list_sources(self) -> list[str]:
        """Return the distinct file_paths LightRAG currently knows about."""
        await self._ensure_initialized()
        if self._rag is None:
            return []
        doc_status = getattr(self._rag, "doc_status", None)
        if doc_status is None:
            return []
        try:
            docs = await doc_status.get_all()
            paths: set[str] = set()
            for rec in docs.values() if isinstance(docs, dict) else docs:
                fp = rec.get("file_path") if isinstance(rec, dict) else None
                if fp:
                    paths.add(fp)
            return sorted(paths)
        except Exception as exc:  # pragma: no cover
            logger.warning("list_sources failed: %s", exc)
            return []

    # ---- response normalization ------------------------------------------

    @staticmethod
    def _normalize_response(raw: Any) -> list[Retrieval]:
        """Coerce LightRAG's response (str, dict, or list) to Retrievals."""
        if raw is None:
            return []

        # Common LightRAG shapes: {"response": str, "references": [...]}
        if isinstance(raw, dict):
            refs = raw.get("references") or raw.get("sources") or []
            out: list[Retrieval] = []
            for i, ref in enumerate(refs):
                if not isinstance(ref, dict):
                    continue
                path = str(ref.get("file_path") or ref.get("source") or f"ref-{i}")
                span = str(ref.get("span") or ref.get("chunk_id") or "0-0")
                score = float(ref.get("score") or ref.get("distance") or 0.0)
                content_raw = ref.get("content", "")
                if isinstance(content_raw, list):
                    content = "\n\n".join(str(c) for c in content_raw)
                else:
                    content = str(content_raw)
                out.append(
                    Retrieval.build(
                        content=content,
                        source_path=path,
                        span=span,
                        score=score,
                    )
                )
            if out:
                return out
            # Fallthrough — no refs? synthesize a single answer-only retrieval
            text = str(raw.get("response") or "")
            if text:
                return [Retrieval.build(content=text, source_path="<llm-answer>")]
            return []

        if isinstance(raw, list):
            out = []
            for i, item in enumerate(raw):
                if isinstance(item, Retrieval):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(
                        Retrieval.build(
                            content=str(item.get("content", "")),
                            source_path=str(item.get("file_path", f"ref-{i}")),
                            span=str(item.get("span", "0-0")),
                            score=float(item.get("score", 0.0)),
                        )
                    )
                else:
                    out.append(Retrieval.build(content=str(item), source_path=f"ref-{i}"))
            return out

        # Plain string — LightRAG's default aquery return
        return [Retrieval.build(content=str(raw), source_path="<llm-answer>")]


# ---------- anthropic bridge ------------------------------------------------


async def _anthropic_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    keyword_extraction: bool = False,  # noqa: ARG001
    **kwargs: Any,
) -> str:
    """LightRAG-compatible ``llm_model_func`` backed by Anthropic's SDK."""
    try:
        from anthropic import AsyncAnthropic
    except Exception as exc:  # pragma: no cover
        raise RagUnavailable(f"anthropic SDK missing: {exc}") from exc

    client = AsyncAnthropic()
    model = kwargs.get("model") or os.environ.get(
        "ANTHROPIC_MODEL", "claude-sonnet-4-5"
    )
    max_tokens = int(kwargs.get("max_tokens", 2048))
    messages: list[dict[str, Any]] = []
    for h in history_messages or []:
        messages.append(
            {"role": h.get("role", "user"), "content": h.get("content", "")}
        )
    messages.append({"role": "user", "content": prompt})
    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt or "You are a helpful RAG assistant.",
        messages=messages,
    )
    parts: list[str] = []
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)
