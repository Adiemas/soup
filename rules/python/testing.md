# Python — testing

Tool: `pytest`, `pytest-asyncio` for async, `hypothesis` for property tests, `pytest-cov` for coverage.

## 1. TDD discipline

Red → Green → Refactor. **Write the failing test first.** Pre-test production code is deleted, not kept.

- RED: add the minimal failing test. Run it. See it fail for the right reason.
- GREEN: simplest implementation that passes. No extra features.
- REFACTOR: tighten the design with tests still green.

## 2. Layout

```
tests/
  unit/                 # fast, isolated, <100ms each
    test_<module>.py
  integration/          # touch external process (Postgres, Redis)
    test_<feature>.py
  e2e/                  # full stack via httpx AsyncClient
    test_<flow>.py
  conftest.py
  fixtures/
    factories.py
```

1. Test files mirror source: `src/invoices/core.py` → `tests/unit/invoices/test_core.py`.
2. One class/function per test module. Split when a file exceeds ~300 lines.
3. Test names describe behavior: `test_pay_invoice_rejects_amount_above_balance`.

## 3. Fixtures

1. Prefer function-scoped fixtures. Use `session` scope only for expensive resources (DB container).
2. Async fixtures use `pytest_asyncio.fixture`.
3. Factories over raw literals — keep tests readable:

```python
@pytest.fixture
def make_invoice():
    def _build(**overrides) -> Invoice:
        defaults = dict(id=uuid4(), total_cents=1000, status="open")
        return Invoice(**{**defaults, **overrides})
    return _build

def test_partial_payment_reduces_balance(make_invoice):
    inv = make_invoice(total_cents=1000)
    inv.apply_payment(400)
    assert inv.balance_cents == 600
```

4. No global mutable state. If a test needs a DB, use a transaction that rolls back (`pytest-postgresql` pattern).

## 4. Parametrize

1. Use `@pytest.mark.parametrize` for tabular input/output. Each case gets a descriptive `id`:

```python
@pytest.mark.parametrize(
    ("amount", "expected_balance"),
    [
        pytest.param(0,    1000, id="zero-payment-is-rejected-but-leaves-balance"),
        pytest.param(400,   600, id="partial-payment-reduces-balance"),
        pytest.param(1000,    0, id="exact-payment-settles"),
    ],
)
def test_apply_payment(amount, expected_balance): ...
```

2. Don't hide assertions inside helper functions — `pytest` loses rich diff output.

## 5. Hypothesis

Use `hypothesis` for functions with a clear invariant (parsers, math, serializers):

```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=0, max_value=10**9))
def test_cents_round_trip(n):
    assert parse_cents(format_cents(n)) == n
```

Use `@settings(max_examples=200)` in CI; keep the default locally.

## 6. Assertions

1. One logical assertion per test — split if you need `and`. (Related assertions on the same object are fine.)
2. Use `pytest.approx` for floats.
3. For exceptions: `with pytest.raises(SomeError, match="expected regex"):`.
4. For logs: `caplog.at_level(logging.WARNING)` then assert on `caplog.records`.

## 7. Async

```python
@pytest.mark.asyncio
async def test_httpx_adapter_raises_on_5xx(httpx_mock):
    httpx_mock.add_response(status_code=500)
    with pytest.raises(UpstreamError):
        await client.fetch_invoice("abc")
```

## 8. Coverage

1. Target ≥80% line coverage on `src/`, ≥90% on `src/<pkg>/core`.
2. Coverage <70% → Stop-hook QA verdict `NEEDS_ATTENTION`.
3. Don't chase 100% by testing trivial getters. Test behavior, not lines.

## 9. Slow tests

Mark with `@pytest.mark.slow`. Default `pytest` runs exclude them; CI runs `pytest -m "slow or not slow"`.

## 10. Do / don't

- DO assert on observable behavior. DON'T assert on internal state if a public method can be used.
- DO use `tmp_path` / `monkeypatch`. DON'T touch `os.environ` without `monkeypatch.setenv`.
- DO mock at the adapter seam. DON'T mock inside pure functions.
- DO keep tests independent. DON'T rely on test ordering.
