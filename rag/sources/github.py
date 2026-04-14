"""GitHub repo source — stream text files via GitHub REST API.

iter-2 dogfood TODOs (scoping; not yet implemented):
    TODO(iter-3): respect ``.gitignore``. Today we filter only by
        extension allow-list; an ``.env``, ``secrets/`` dir, or
        ``node_modules`` checked into a private repo would still be
        ingested if its extension matched. We rely on the ext list as
        a proxy but should layer in a gitignore-aware skip pass for
        defense-in-depth (a private repo with checked-in ``.env`` is
        a real exfiltration vector via RAG hits).
    TODO(iter-3): ingest issues + PRs as separate chunks. A spec that
        references "the discussion in PR #482" can't be retrieved if we
        only see the merged tree. ``GET /repos/{owner}/{repo}/issues``
        + per-issue comment threads → one chunk per comment with
        ``source_path`` of ``github://owner/repo/issues/482``.
    TODO(iter-3): repo topology weighting. Today every blob is yielded
        in tree order. Onboarding LLM benefits if README.md, docs/**,
        and root-level ``ARCHITECTURE.md`` are emitted *first* — they
        give the index richer entity edges before code chunks arrive.
        Add a sort step before ``for entry in tree``.
    TODO(iter-3): incremental re-ingest. ``Chunk.hash()`` dedups
        in-memory but does not persist across sessions, so a re-ingest
        re-fetches every blob and re-emits every chunk. The GitHub API
        returns blob ``sha`` per tree entry; storing
        ``(repo, branch, path) → sha`` in the LightRAG ``doc_status``
        store would let us skip blob fetches for unchanged paths.
    TODO(iter-3): pagination. ``GET /git/trees/{branch}?recursive=1``
        returns ``truncated: true`` for repos with >100k entries; today
        we just log a warning and lose the tail. Need to fall back to
        per-subdir fetches when truncated.
    TODO(iter-3): handle GitHub Enterprise. ``api_base`` is parameterised
        but URI scheme ``ghe://`` is not wired through ``Ingester.build_source``;
        a Streck-internal Enterprise host can't be ingested via URI today.
"""

from __future__ import annotations

import base64
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from rag.client import Chunk
from rag.ingest import ChunkerConfig, chunk_text

logger = logging.getLogger("soup.rag.sources.github")

# Conservative list of extensions we consider text and worth indexing.
_TEXT_EXTS: frozenset[str] = frozenset(
    {
        ".md",
        ".markdown",
        ".rst",
        ".txt",
        ".py",
        ".cs",
        ".csproj",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".sql",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".json",
        ".sh",
        ".bash",
        ".go",
        ".java",
        ".kt",
        ".rb",
        ".rs",
        ".scala",
        ".swift",
        ".proto",
        ".graphql",
    }
)

_MAX_FILE_BYTES = 1_500_000


@dataclass
class GithubRepoSource:
    """Stream a GitHub repo's text files.

    Uses the GitHub REST API: ``/repos/{owner}/{repo}/git/trees/{branch}?recursive=1``
    for listing, then per-blob fetches. ``token`` falls back to ``GITHUB_TOKEN``;
    if unset, we still try (public repos work, rate limits are tiny).
    """

    owner: str
    repo: str
    branch: str = "main"
    token: str | None = None
    include_exts: frozenset[str] = field(default_factory=lambda: _TEXT_EXTS)
    max_bytes: int = _MAX_FILE_BYTES
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    api_base: str = "https://api.github.com"

    @property
    def uri(self) -> str:
        return f"github://{self.owner}/{self.repo}@{self.branch}"

    def _headers(self) -> dict[str, str]:
        token = self.token or os.environ.get("GITHUB_TOKEN")
        if not token:
            logger.warning(
                "GITHUB_TOKEN not set — GithubRepoSource subject to low rate limits"
            )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "soup-rag/0.1",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def iter_chunks(self) -> AsyncIterator[Chunk]:
        headers = self._headers()
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            tree = await self._fetch_tree(client)
            for entry in tree:
                if entry.get("type") != "blob":
                    continue
                path: str = entry["path"]
                size: int = int(entry.get("size", 0))
                if size > self.max_bytes:
                    continue
                if not self._is_text(path):
                    continue
                content = await self._fetch_blob(client, entry["sha"])
                if content is None:
                    continue
                for chunk in chunk_text(
                    content,
                    path,
                    config=self.chunker,
                    metadata={"repo": f"{self.owner}/{self.repo}", "branch": self.branch},
                ):
                    yield chunk

    async def _fetch_tree(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        url = f"{self.api_base}/repos/{self.owner}/{self.repo}/git/trees/{self.branch}"
        try:
            resp = await client.get(url, params={"recursive": "1"})
            if resp.status_code == 404:
                logger.warning("github repo or branch not found: %s", self.uri)
                return []
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("failed to fetch github tree %s: %s", self.uri, exc)
            return []
        data = resp.json()
        if data.get("truncated"):
            logger.warning(
                "github tree truncated for %s — consider splitting by subdir", self.uri
            )
        tree = data.get("tree")
        return tree if isinstance(tree, list) else []

    async def _fetch_blob(
        self, client: httpx.AsyncClient, sha: str
    ) -> str | None:
        url = f"{self.api_base}/repos/{self.owner}/{self.repo}/git/blobs/{sha}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("blob fetch failed %s: %s", sha, exc)
            return None
        payload = resp.json()
        encoding = payload.get("encoding")
        raw = payload.get("content", "")
        try:
            if encoding == "base64":
                data = base64.b64decode(raw)
                return data.decode("utf-8", errors="replace")
            return str(raw)
        except Exception as exc:
            logger.debug("blob decode failed %s: %s", sha, exc)
            return None

    def _is_text(self, path: str) -> bool:
        lower = path.lower()
        for ext in self.include_exts:
            if lower.endswith(ext):
                return True
        return False
