# Python — coding standards

Target: Python 3.12+. Preferred stack: FastAPI + Pydantic v2, Typer for CLIs, `uv` for env, `ruff` for lint/format, `mypy --strict`, `pytest`.

## 1. Typing

1. **Every function and method has type hints.** `mypy --strict` clean — no implicit `Any`.
2. Use PEP 604 unions: `int | None`, never `Optional[int]` except on Python 3.9 fallbacks.
3. Use `list[str]`, `dict[str, int]`, `tuple[int, ...]` — not `List`, `Dict`, `Tuple`.
4. Prefer `Protocol` / structural typing for seams over ABCs.
5. Never use `Any` in new code. If a library returns `Any`, narrow it at the boundary with a cast + docstring rationale.
6. Use `TypedDict` or a Pydantic model for structured dicts. Never pass raw dicts across public boundaries.

```python
from pydantic import BaseModel

class InvoiceRef(BaseModel):
    id: str
    total_cents: int

def total_of(invoices: list[InvoiceRef]) -> int:
    return sum(i.total_cents for i in invoices)
```

## 2. Docstrings

1. Every public module, class, and function gets a docstring.
2. Single-line for trivial; multi-line for anything with args/returns/raises.
3. Use Google style:

```python
def pay_invoice(invoice_id: UUID, amount_cents: int) -> Invoice:
    """Record a payment against an invoice.

    Args:
        invoice_id: The target invoice.
        amount_cents: Positive integer, ≤ outstanding balance.

    Returns:
        The updated invoice with the payment applied.

    Raises:
        InvoiceNotFoundError: If no invoice has `invoice_id`.
        InvoiceAlreadyPaidError: If the invoice has a zero balance.
    """
```

## 3. Ruff & formatting

1. `ruff check` + `ruff format` are the source of truth. No black, no isort — ruff does both.
2. Line length: 100. Strings longer than that → concatenate implicit strings or use `textwrap.dedent`.
3. Enabled rule groups (baseline): `E,F,W,I,UP,B,SIM,RUF,ARG,PL,TID,PTH,RET,ASYNC`.
4. Commits must pass `ruff check --fix` with zero remaining diagnostics (or explicit per-line `# noqa: CODE — reason`).

## 4. Project layout

```
src/<package>/
  __init__.py
  core/            # pure domain logic (no I/O)
  adapters/        # HTTP, DB, external services
  app/             # FastAPI app + composition root
  cli/             # Typer CLI(s)
tests/
  unit/
  integration/
pyproject.toml
```

`src/` layout is mandatory — prevents accidental imports of test-time shims.

## 5. Error handling

1. Define a module-local base exception (`class InvoicesError(Exception): ...`) and raise subclasses.
2. Never `except Exception:` without re-raising or converting. Never `except:` at all.
3. In adapters, wrap third-party errors into domain errors:

```python
try:
    row = await conn.fetchrow(...)
except asyncpg.PostgresError as e:
    raise InvoiceRepositoryError("fetch failed") from e
```

## 6. FastAPI patterns

1. Use `APIRouter` per feature; compose in `app/main.py`.
2. Dependencies via `Depends(...)`. No module-level global state.
3. Request/response models are Pydantic, `model_config = ConfigDict(extra="forbid", frozen=True)`.
4. All handlers `async def` unless they are truly synchronous.
5. Error envelopes are consistent: `{"error": {"code": "...", "message": "..."}}`. Map domain errors in an exception handler, not in routes.
6. Health endpoints: `/healthz` (liveness, no deps) and `/readyz` (readiness, checks DB).
7. OpenAPI tags match routers; every route has a `summary` and `response_model`.

## 7. Async

1. Don't block the event loop. No `time.sleep`, no sync `requests` — use `httpx.AsyncClient`.
2. Share an `httpx.AsyncClient` per-app (lifespan) — don't create one per request.
3. Use `anyio` for structured concurrency when composing tasks. Avoid raw `asyncio.create_task` without a cancel scope.

## 8. Dependencies

1. Manage with `uv`. `pyproject.toml` is the source of truth; `uv.lock` is committed.
2. Pin major versions (`fastapi>=0.115,<0.116`), let minor/patch float within.
3. No dev deps in the runtime group.

## 9. Checklist before commit

- [ ] `ruff check` clean
- [ ] `ruff format` applied
- [ ] `mypy --strict` clean
- [ ] `pytest -q` green
- [ ] New public symbols have docstrings
- [ ] No `Any`, no bare `except`, no `print` (use logging)
