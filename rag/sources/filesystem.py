"""Filesystem source — glob a local directory and yield chunks."""

from __future__ import annotations

import fnmatch
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rag.client import Chunk
from rag.ingest import ChunkerConfig, chunk_text

logger = logging.getLogger("soup.rag.sources.filesystem")

_DEFAULT_GLOBS: tuple[str, ...] = (
    "**/*.md",
    "**/*.py",
    "**/*.cs",
    "**/*.ts",
    "**/*.tsx",
    "**/*.sql",
)

_DEFAULT_IGNORES: tuple[str, ...] = (
    "**/.git/**",
    "**/node_modules/**",
    "**/.venv/**",
    "**/venv/**",
    "**/__pycache__/**",
    "**/dist/**",
    "**/build/**",
    "**/.soup/rag_storage/**",
)


@dataclass
class FilesystemSource:
    """Iterate over files under ``root`` matching ``globs``."""

    root: str | Path
    globs: Sequence[str] = field(default_factory=lambda: list(_DEFAULT_GLOBS))
    ignores: Sequence[str] = field(default_factory=lambda: list(_DEFAULT_IGNORES))
    max_bytes: int = 1_500_000  # skip files bigger than ~1.5 MB
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)

    @property
    def uri(self) -> str:
        return f"file://{Path(self.root).resolve().as_posix()}"

    async def iter_chunks(self) -> AsyncIterator[Chunk]:
        root = Path(self.root)
        if not root.exists():
            logger.warning("FilesystemSource root does not exist: %s", root)
            return
        seen: set[Path] = set()
        for pattern in self.globs:
            for path in root.glob(pattern):
                if not path.is_file() or path in seen:
                    continue
                if self._ignored(path, root):
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size > self.max_bytes:
                    logger.debug("skipping oversized file %s (%d bytes)", path, size)
                    continue
                seen.add(path)
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except Exception as exc:
                    logger.debug("unreadable %s: %s", path, exc)
                    continue
                rel = path.relative_to(root).as_posix()
                for chunk in chunk_text(text, rel, config=self.chunker):
                    yield chunk

    def _ignored(self, path: Path, root: Path) -> bool:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        return any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.as_posix(), pat)
                   for pat in self.ignores)
