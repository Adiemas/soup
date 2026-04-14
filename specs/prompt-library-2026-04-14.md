# Streck Prompt Library

_Drafted by `spec-writer` (sonnet) under `/specify` on 2026-04-14. EARS format per Constitution Article I._

## Summary

An internal web application that lets Streck AI engineers author, tag, search, and version prompt templates. Replaces the current Confluence page + shared Google Doc workflow where prompts go to die. Engineers can paste a template, attach tags, see who changed what, and reuse approved prompts across projects.

## Stakeholders & personas

- **AI engineer (primary)** — writes and consumes prompt templates every day; wants low-friction add + search.
- **Tech lead (secondary)** — approves promotion of a prompt from "draft" to "approved"; wants an audit trail.
- **Platform admin** — operates the deployment; wants health endpoints and logs.

## User outcomes

- Engineers can add a prompt template in under 30 seconds (paste, title, save).
- Engineers can search prompts by free-text title/body or by tag in <200ms P50.
- Engineers see every historical version of a prompt and can diff adjacent versions.
- Promotion state (`draft` vs `approved`) is visible in the list view.
- Audit of who changed what is queryable for the last 180 days.

## Functional requirements

1. REQ-1: The system shall accept a new prompt submission containing a title (≤200 chars), a body (≤32 KB UTF-8), and zero or more tags (each ≤40 chars, kebab-case).
2. REQ-2: When an engineer saves edits to an existing prompt, the system shall create a new version record rather than overwriting the prior version.
3. REQ-3: The system shall return search results by full-text match against title + body and by exact tag match, within 200ms P50 on a corpus of up to 10,000 prompts.
4. REQ-4: When a tech lead marks a prompt version as `approved`, the system shall record the approver's identity and timestamp and surface the badge in list and detail views.
5. REQ-5: The system shall expose a version history view per prompt, listing each version's author, timestamp, and a unified diff against the immediately prior version.
6. REQ-6: Where a prompt has no approved version, the system shall display the latest draft in list views with a clear "draft" indicator.
7. REQ-7: If an engineer attempts to delete a prompt, the system shall soft-delete (retain the row + versions with a `deleted_at` timestamp) and hide it from default list queries.
8. REQ-8: The system shall authenticate callers via the Streck SSO header and reject unauthenticated requests with HTTP 401.
9. REQ-9: When the system starts, the system shall run all pending database migrations before accepting traffic.
10. REQ-10: The system shall expose `/healthz` (liveness) and `/readyz` (readiness, checks Postgres connectivity) per `rules/python/coding-standards.md §6.6`.

## Non-functional requirements

- NFR-1: Search P50 <200ms, P95 <500ms on 10k prompts.
- NFR-2: 99.5% monthly availability during business hours (internal SLA).
- NFR-3: Secrets read from env only (Constitution Article VI); no hard-coded credentials.
- NFR-4: Backend ≥80% line coverage, ≥90% on `core/` (per `rules/python/testing.md §8`).
- NFR-5: Structured JSON logs with request ID propagation.

## Acceptance criteria

- AC-1: `pytest -q` in `backend/` is green and `pytest-cov` reports ≥80% line coverage on `src/prompt_library/`.
- AC-2: `vitest run` in `frontend/` is green for the list view and search box components.
- AC-3: `curl -X POST /prompts -d '{...}'` followed by `curl /prompts?q=...` returns the created row in <200ms on an empty local Postgres.
- AC-4: Editing a prompt via `PUT /prompts/{id}` creates a new row in `prompt_versions` with `version = prev + 1`; the prior row is unchanged.
- AC-5: A deleted prompt (`DELETE /prompts/{id}`) sets `deleted_at` and stops appearing in default `GET /prompts` results; it remains retrievable via `GET /prompts/{id}?include_deleted=1`.
- AC-6: `docker-compose up` from repo root brings backend + Postgres + frontend up; hitting `http://localhost:5173` shows the list view and allows adding a prompt end-to-end.

## Out of scope

- External (non-Streck) user sharing. Internal only.
- Rich-text / WYSIWYG prompt editing. Plaintext body only for v1.
- AI-assisted prompt suggestions. Humans write; the app stores.
- Prompt execution / evaluation. Storage + discovery only.
- Non-Postgres storage backends.
- Migration of historical prompts from Confluence; one-shot import is a separate spec.

## Open questions

1. Should tags be free-form per-author, or drawn from a curated taxonomy gated by admins? (Tradeoff: discoverability vs. cognitive cost at add time.)
2. What is the deletion policy — soft-delete forever, or hard-delete after N days?
3. Do we need per-prompt ACLs (team visibility), or is "everyone at Streck can read everything" acceptable for v1?

## Clarifications

_Resolved under `/clarify` on 2026-04-14. Answered 2 of 3; Q3 deferred per user._

- **Q1 — Tag taxonomy?** Answer: **Free-form** for v1. Added as REQ-11. Rationale: lowest friction at add-time; we'll curate later with a taxonomy migration if cardinality explodes.
  - REQ-11: The system shall accept any kebab-case tag (regex `^[a-z0-9][a-z0-9-]{0,39}$`) without requiring pre-registration.
- **Q2 — Deletion policy?** Answer: **Soft-delete forever** for v1. Moved into REQ-7 (already soft-delete); added NFR-6. Rationale: audit trail > storage savings at this scale.
  - NFR-6: The system shall retain soft-deleted prompt rows and their versions indefinitely; purge policy is out-of-scope until volume warrants.
- **Q3 — Per-team ACLs?** Deferred. Open Question stays on the spec; will re-raise after v1 ships. Short-term stance: "Streck-wide readable" for v1, explicit in `## Out of scope`.
