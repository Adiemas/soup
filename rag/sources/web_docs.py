"""Web docs source — fetch URLs, strip HTML with a regex fallback."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from rag.client import Chunk
from rag.ingest import ChunkerConfig, chunk_text

logger = logging.getLogger("soup.rag.sources.web_docs")

_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|svg)[^>]*>.*?</\1\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n\s*\n\s*\n+")
_LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', flags=re.IGNORECASE)


def _html_to_text(html: str) -> str:
    """Best-effort HTML → text, mildly markdown-flavoured."""
    stripped = _SCRIPT_STYLE_RE.sub("", html)
    # Preserve common block boundaries as newlines before tag stripping.
    stripped = re.sub(
        r"<(/?)(p|div|section|article|br|li|h[1-6]|pre|tr)(\s[^>]*)?>",
        "\n",
        stripped,
        flags=re.IGNORECASE,
    )
    text = _TAG_RE.sub("", stripped)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


@dataclass
class WebDocsSource:
    """Fetch a set of URLs (plus same-host links, to ``crawl_depth``)."""

    url_list: Sequence[str]
    crawl_depth: int = 1
    max_pages: int = 50
    timeout: float = 20.0
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)

    @property
    def uri(self) -> str:
        return f"web://{','.join(self.url_list)}"

    async def iter_chunks(self) -> AsyncIterator[Chunk]:
        seen: set[str] = set()
        queue: list[tuple[str, int]] = [(u, 0) for u in self.url_list]
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, headers={"User-Agent": "soup-rag/0.1"}
        ) as client:
            while queue and len(seen) < self.max_pages:
                url, depth = queue.pop(0)
                url, _ = urldefrag(url)
                if url in seen:
                    continue
                seen.add(url)
                html = await self._fetch(client, url)
                if not html:
                    continue
                text = _html_to_text(html)
                if text:
                    for chunk in chunk_text(
                        text,
                        url,
                        config=self.chunker,
                        metadata={"url": url},
                    ):
                        yield chunk
                if depth < self.crawl_depth:
                    base_host = urlparse(url).netloc
                    for href in _LINK_RE.findall(html):
                        nxt = urljoin(url, href)
                        if urlparse(nxt).netloc == base_host and nxt not in seen:
                            queue.append((nxt, depth + 1))

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("web fetch failed %s: %s", url, exc)
            return None
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return None
        return resp.text
