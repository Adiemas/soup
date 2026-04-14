"""Azure DevOps Work Items source — stream WI titles, descriptions, comments.

Companion to :mod:`rag.sources.ado_wiki`. Where that adapter ingests ADO
wiki pages, this one ingests **work items** (bugs, tasks, features,
user stories) so that spec-writer / architect agents can pull the body
of ``STRECK-482`` into ``TaskStep.context_excerpts`` without asking
the user to paste it.

URI scheme: ``ado-wi://<org>/<project>/<query-or-id>``.

Two materialisation modes:

  - ``ado-wi://org/project/<id>`` — single work item by numeric ID.
  - ``ado-wi://org/project/<wiql-or-name>`` — WIQL query (URL-encoded)
    OR a saved-query name; runs the wiql endpoint and fans out.

Stub-friendly: if ``ADO_PAT`` is missing we warn and return an empty
iterator rather than raising — matches the ``.env.example`` "stub-safe"
contract and the iter-2 dogfood audit note.

Wire-up:
  - ``rag/ingest.py::Ingester.build_source`` routes ``ado-wi://`` here.
  - ``rag/sources/__init__.py`` exports the class.
  - ``ado-agent`` (``.claude/agents/ado-agent.md``) documents the flow.

iter-3 scope (not yet implemented):
    TODO(iter-3): respect each work item's permissions. An engineer
        with restricted access may see redacted fields; chunk the
        returned body as-is but flag dropped fields.
    TODO(iter-3): honour WIQL paging. ``wiql`` caps at 20k IDs;
        larger queries need iteration via ``continuationToken`` on
        the work-items batch endpoint.
    TODO(iter-3): ingest linked artifacts (PRs, commits) as separate
        chunks with cross-references — today we stop at the work-item
        body + comments.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

import httpx

from rag.client import Chunk
from rag.ingest import ChunkerConfig, chunk_text

logger = logging.getLogger("soup.rag.sources.ado_work_items")

_API_VERSION = "7.1"


@dataclass
class AdoWorkItemsSource:
    """Azure DevOps work-items adapter.

    Auth: Basic with empty username + PAT (``pat`` or ``ADO_PAT`` env var).

    Attributes:
        org: ADO organisation name (from ``https://dev.azure.com/<org>``).
        project: Project name.
        query: Either a numeric work-item ID, a URL-encoded WIQL
            string (``SELECT [System.Id] FROM WorkItems WHERE ...``),
            or a simple filter dict serialised to WIQL by the adapter.
        pat: Optional PAT override; else ``ADO_PAT`` / ``AZURE_DEVOPS_PAT``.
        chunker: chunker config.
        api_base: override for Azure DevOps Server / on-prem installs.
    """

    org: str
    project: str
    query: str
    pat: str | None = None
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    api_base: str = "https://dev.azure.com"

    @property
    def uri(self) -> str:
        return f"ado-wi://{self.org}/{self.project}/{self.query}"

    def _auth(self) -> httpx.BasicAuth | None:
        pat = (
            self.pat
            or os.environ.get("ADO_PAT")
            or os.environ.get("AZURE_DEVOPS_PAT")
            or os.environ.get("AZURE_DEVOPS_EXT_PAT")
        )
        if not pat:
            logger.warning(
                "ADO_PAT not set — AdoWorkItemsSource will not fetch any "
                "work items (stub-safe: returning empty iterator)"
            )
            return None
        return httpx.BasicAuth(username="", password=pat)

    async def iter_chunks(self) -> AsyncIterator[Chunk]:
        auth = self._auth()
        if auth is None:
            # Stub-safe path: no PAT, no work items. Caller sees an
            # IngestReport with chunks_seen == 0 and no errors.
            return
        async with httpx.AsyncClient(timeout=30.0, auth=auth) as client:
            ids = await self._resolve_ids(client)
            if not ids:
                return
            for wi_id in ids:
                chunks = await self._fetch_work_item(client, wi_id)
                for c in chunks:
                    yield c

    # ---- resolution -------------------------------------------------------

    async def _resolve_ids(self, client: httpx.AsyncClient) -> list[int]:
        """Return the list of work-item IDs for this source.

        Dispatch:
          - If ``self.query`` is a plain integer, return ``[int]``.
          - Else treat it as WIQL and POST to the wiql endpoint.
        """
        q = unquote(self.query).strip()
        if q.isdigit():
            return [int(q)]
        wiql = q if q.upper().startswith("SELECT") else self._wrap_as_wiql(q)
        return await self._run_wiql(client, wiql)

    @staticmethod
    def _wrap_as_wiql(filter_text: str) -> str:
        """Wrap a simple filter clause as a minimal WIQL statement.

        Accepts things like ``[System.State] = 'Active'`` and returns
        ``SELECT [System.Id] FROM WorkItems WHERE ...``. Callers that
        pass a full WIQL statement skip this wrapper (see
        ``_resolve_ids``).
        """
        if not filter_text:
            return "SELECT [System.Id] FROM WorkItems"
        return (
            "SELECT [System.Id] FROM WorkItems WHERE " + filter_text
        )

    async def _run_wiql(
        self, client: httpx.AsyncClient, wiql: str
    ) -> list[int]:
        url = (
            f"{self.api_base}/{self.org}/{self.project}"
            f"/_apis/wit/wiql?api-version={_API_VERSION}"
        )
        try:
            resp = await client.post(url, json={"query": wiql})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("ado-wi wiql failed: %s", exc)
            return []
        data: dict[str, Any] = resp.json()
        items = data.get("workItems") or []
        ids: list[int] = []
        for row in items:
            try:
                ids.append(int(row["id"]))
            except (KeyError, TypeError, ValueError):
                continue
        return ids

    # ---- per-WI fetch -----------------------------------------------------

    async def _fetch_work_item(
        self, client: httpx.AsyncClient, wi_id: int
    ) -> list[Chunk]:
        """Fetch one work item plus its comments; return Chunks."""
        wi = await self._get_wi(client, wi_id)
        if not wi:
            return []
        comments = await self._get_comments(client, wi_id)
        body = self._render_markdown(wi, comments, wi_id)
        if not body.strip():
            return []
        source_path = f"{self.uri}#wi-{wi_id}"
        metadata: dict[str, str] = {
            "org": self.org,
            "project": self.project,
            "work_item_id": str(wi_id),
        }
        fields = wi.get("fields") or {}
        for key in (
            "System.WorkItemType",
            "System.State",
            "System.AssignedTo",
            "System.Title",
        ):
            val = fields.get(key)
            if val is None:
                continue
            if isinstance(val, dict):
                val = val.get("displayName") or val.get("uniqueName") or ""
            metadata[key.replace(".", "_")] = str(val)
        return list(
            chunk_text(
                body,
                source_path,
                config=self.chunker,
                metadata=metadata,
            )
        )

    async def _get_wi(
        self, client: httpx.AsyncClient, wi_id: int
    ) -> dict[str, Any] | None:
        url = (
            f"{self.api_base}/{self.org}/{self.project}"
            f"/_apis/wit/workitems/{wi_id}?$expand=all&api-version={_API_VERSION}"
        )
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("ado-wi fetch failed %s: %s", wi_id, exc)
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None

    async def _get_comments(
        self, client: httpx.AsyncClient, wi_id: int
    ) -> list[dict[str, Any]]:
        url = (
            f"{self.api_base}/{self.org}/{self.project}"
            f"/_apis/wit/workItems/{wi_id}/comments"
            f"?api-version={_API_VERSION}-preview.3"
        )
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("ado-wi comments failed %s: %s", wi_id, exc)
            return []
        data = resp.json()
        if not isinstance(data, dict):
            return []
        comments = data.get("comments") or []
        return [c for c in comments if isinstance(c, dict)]

    # ---- render -----------------------------------------------------------

    @staticmethod
    def _render_markdown(
        wi: dict[str, Any],
        comments: list[dict[str, Any]],
        wi_id: int,
    ) -> str:
        fields = wi.get("fields") or {}
        title = fields.get("System.Title") or f"Work Item {wi_id}"
        state = fields.get("System.State") or "(unknown)"
        wi_type = fields.get("System.WorkItemType") or "WorkItem"
        description = fields.get("System.Description") or ""
        acceptance = fields.get(
            "Microsoft.VSTS.Common.AcceptanceCriteria"
        ) or ""
        assigned_to = fields.get("System.AssignedTo")
        if isinstance(assigned_to, dict):
            assigned_to = assigned_to.get("displayName") or ""

        lines: list[str] = [
            f"# {wi_type} {wi_id}: {title}",
            "",
            f"- **State:** {state}",
            f"- **Type:** {wi_type}",
        ]
        if assigned_to:
            lines.append(f"- **Assigned to:** {assigned_to}")
        lines.append("")
        if description:
            lines.extend(["## Description", "", str(description), ""])
        if acceptance:
            lines.extend(["## Acceptance criteria", "", str(acceptance), ""])
        if comments:
            lines.extend(["## Comments", ""])
            for c in comments:
                author = c.get("createdBy") or {}
                who = (
                    author.get("displayName")
                    if isinstance(author, dict)
                    else ""
                ) or "(unknown)"
                when = c.get("createdDate") or ""
                text = c.get("text") or ""
                lines.append(f"### {who} — {when}")
                lines.append("")
                lines.append(str(text))
                lines.append("")
        return "\n".join(lines)


__all__ = ["AdoWorkItemsSource"]
