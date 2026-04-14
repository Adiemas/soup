"""Source adapters — each yields ``Chunk`` objects for the ingester."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from rag.client import Chunk
from rag.sources.ado_wiki import AdoWikiSource
from rag.sources.ado_work_items import AdoWorkItemsSource
from rag.sources.filesystem import FilesystemSource
from rag.sources.github import GithubRepoSource
from rag.sources.web_docs import WebDocsSource


@runtime_checkable
class Source(Protocol):
    """Protocol every source adapter must satisfy."""

    uri: str

    def iter_chunks(self) -> AsyncIterator[Chunk]:  # pragma: no cover - protocol
        ...


__all__ = [
    "AdoWikiSource",
    "AdoWorkItemsSource",
    "Chunk",
    "FilesystemSource",
    "GithubRepoSource",
    "Source",
    "WebDocsSource",
]
