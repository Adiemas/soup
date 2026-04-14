"""Azure DevOps Wiki source — stream pages via the ADO REST API.

iter-2 dogfood TODOs (scoping; not yet implemented):
    TODO(iter-3): distinguish project wikis vs code wikis. The current
        list endpoint returns both kinds, but ``type`` field on each Wiki
        entry (``projectWiki`` vs ``codeWiki``) selects different page
        retrieval semantics: code wikis are git-backed and need a
        ``versionDescriptor`` (branch/commit) on every page request.
        Today we silently pick ``values[0]`` and assume it works for
        either. Streck has both kinds in their primary org.
    TODO(iter-3): handle attachments. ADO wiki pages can embed images
        and PDFs via ``/attachments/{name}``. We currently drop the
        markdown image links and never fetch the binary, so retrieved
        chunks lose the visual context (e.g. architecture diagrams).
    TODO(iter-3): wiki-identifier discovery should be exposed as a
        standalone CLI (``python -m rag.sources.ado_wiki list-wikis
        --org streck``) so onboarding engineers can choose a wiki ID
        instead of trusting our ``values[0]`` heuristic.
    TODO(iter-3): ingest ADO **work items** as chunks, not just wiki
        pages. A separate ``AdoWorkItemsSource`` keyed by WIQL query
        (``ado-wi://org/project?wiql=...``) is the right shape; the
        ado-agent can then auto-fetch ``STRECK-482``-style references
        into ``context_excerpts`` per the iter-2 brief.
    TODO(iter-3): incremental updates. The pages endpoint exposes a
        ``version`` field per page; storing the latest seen version per
        ``(wiki, path)`` and skipping unchanged pages would cut re-ingest
        cost dramatically. Today we re-stream every page on every run
        and lean on ``Chunk.hash()`` dedup, which is wasteful (full text
        round-trip per page).
    TODO(iter-3): pagination. The ``recursionLevel=full`` flag returns
        the whole tree in one request, but very large wikis (~5k pages)
        will time out. Need a ``continuationToken`` loop.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from rag.client import Chunk
from rag.ingest import ChunkerConfig, chunk_text

logger = logging.getLogger("soup.rag.sources.ado_wiki")

_API_VERSION = "7.1"


@dataclass
class AdoWikiSource:
    """Azure DevOps Wiki adapter.

    Auth: Basic with empty username + PAT (``pat`` or ``ADO_PAT`` env var).
    URL shape:
        https://dev.azure.com/{org}/{project}/_apis/wiki/wikis/{wikiId}/pages

    Known gaps (see module-level TODOs):
      - No code-wiki vs project-wiki distinction (assumes ``values[0]``).
      - No attachment fetching (markdown image refs are lost).
      - No incremental update path; relies on hash-based dedup.
      - No pagination on very large wiki trees.
    """

    org: str
    project: str
    wiki_id: str | None = None
    pat: str | None = None
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    api_base: str = "https://dev.azure.com"

    @property
    def uri(self) -> str:
        wiki = self.wiki_id or "default"
        return f"ado://{self.org}/{self.project}/{wiki}"

    def _auth(self) -> httpx.BasicAuth | None:
        pat = self.pat or os.environ.get("ADO_PAT") or os.environ.get("AZURE_DEVOPS_PAT")
        if not pat:
            logger.warning("ADO_PAT not set — AdoWikiSource will only see public wikis")
            return None
        return httpx.BasicAuth(username="", password=pat)

    async def iter_chunks(self) -> AsyncIterator[Chunk]:
        auth = self._auth()
        async with httpx.AsyncClient(timeout=30.0, auth=auth) as client:
            wiki_id = await self._resolve_wiki_id(client)
            if not wiki_id:
                return
            pages = await self._list_pages(client, wiki_id)
            for page in pages:
                path: str = page.get("path") or "/"
                content = await self._fetch_page(client, wiki_id, path)
                if not content:
                    continue
                for chunk in chunk_text(
                    content,
                    f"{self.uri}{path}.md",
                    config=self.chunker,
                    metadata={
                        "org": self.org,
                        "project": self.project,
                        "wiki": wiki_id,
                    },
                ):
                    yield chunk

    async def _resolve_wiki_id(self, client: httpx.AsyncClient) -> str | None:
        if self.wiki_id:
            return self.wiki_id
        url = (
            f"{self.api_base}/{self.org}/{self.project}"
            f"/_apis/wiki/wikis?api-version={_API_VERSION}"
        )
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("ado wiki list failed: %s", exc)
            return None
        data: dict[str, Any] = resp.json()
        values = data.get("value") or []
        if not values:
            return None
        return str(values[0].get("id") or values[0].get("name"))

    async def _list_pages(
        self, client: httpx.AsyncClient, wiki_id: str
    ) -> list[dict[str, Any]]:
        url = (
            f"{self.api_base}/{self.org}/{self.project}/_apis/wiki/wikis/"
            f"{wiki_id}/pages?recursionLevel=full&api-version={_API_VERSION}"
        )
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("ado wiki pages failed: %s", exc)
            return []
        data = resp.json()
        return self._flatten_pages(data)

    def _flatten_pages(self, node: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(node, dict):
            return out
        if node.get("path"):
            out.append(node)
        for child in node.get("subPages") or []:
            out.extend(self._flatten_pages(child))
        return out

    async def _fetch_page(
        self, client: httpx.AsyncClient, wiki_id: str, path: str
    ) -> str | None:
        url = (
            f"{self.api_base}/{self.org}/{self.project}/_apis/wiki/wikis/"
            f"{wiki_id}/pages?path={path}&includeContent=true"
            f"&api-version={_API_VERSION}"
        )
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("ado page %s fetch failed: %s", path, exc)
            return None
        data = resp.json()
        content = data.get("content")
        return str(content) if content else None
