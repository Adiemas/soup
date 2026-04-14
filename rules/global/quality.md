# Code quality

Project-wide quality invariants. Stack files add specifics; these remain in force.

## 1. Naming

1. Use intention-revealing names. Avoid single letters except for tight loop indices (`i`, `j`) and conventional math (`x`, `y`, `n`).
2. Use domain terms. `invoice.total_cents` beats `invoice.amount`. Match names to the spec glossary.
3. Functions are verbs: `calculate_total`, `fetch_invoices`. Classes are nouns: `InvoiceRepository`.
4. Booleans read like questions: `is_active`, `has_balance`, `can_edit`. Avoid negatives like `is_not_ready`.
5. Abbreviations only when standard (`http`, `url`, `id`). Never invent new acronyms.
6. File/module names mirror the primary export: `invoice_repository.py` exports `InvoiceRepository`.

## 2. Cohesion & coupling

1. One module = one reason to change. If you can't name it in 3 words, split it.
2. Public surface area is minimal. Default to module-private; add public symbols only when another module needs them.
3. Depend on abstractions at seams (ports/adapters). Concrete types within a module are fine.
4. No cycles between packages. Ever. Break cycles with an interface in the consumer's package.
5. Keep functions under ~40 lines where natural. If it grew, it probably has two responsibilities.

## 3. Error handling — boundary validation only

Per CLAUDE.md: **validate at boundaries, trust within the core**. Concretely:

1. **Boundary** (HTTP handler, CLI command, message consumer, external API call) validates all inputs and translates exceptions into stable error types.
2. **Core** (domain logic) assumes inputs are valid. It raises typed domain errors (`InvoiceAlreadyPaidError`) — it does not defensively re-check types.
3. Never swallow exceptions. A bare `except:` / `catch {}` is a defect.
4. Don't log-and-rethrow. Either handle or propagate — not both.
5. Convert third-party exceptions at the adapter boundary into domain errors; the core never imports vendor error types.
6. Resource cleanup uses context managers (`with`, `using`, `try/finally`). No leaked handles.

## 4. Control flow

1. Early return over nested `if`. Reduce indentation.
2. No flag arguments (`def foo(x, format=True)`). Split into two functions.
3. Avoid `else` after `return`, `raise`, or `continue` — it's dead structure.
4. Mutating loops are a code smell when a comprehension / `map` / LINQ works.

## 5. Comments

1. Comments explain **why**, not **what**. The what is visible in the code.
2. Remove stale comments in the same PR that invalidates them.
3. `TODO:` requires an owner and a link to a ticket. `TODO(ethan): ADO-1234` is acceptable; bare `TODO` is not.
4. No commented-out code. Git keeps history.

## 6. Example — boundary vs. core

```python
# adapter/http.py -- BOUNDARY: validates, translates.
@app.post("/invoices/{iid}/pay")
def pay(iid: UUID, body: PayRequest) -> PayResponse:
    try:
        result = pay_invoice(iid, body.amount_cents)      # core call
    except InvoiceAlreadyPaidError:
        raise HTTPException(409, "already paid")
    except InvoiceNotFoundError:
        raise HTTPException(404, "invoice not found")
    return PayResponse.model_validate(result)

# core/invoices.py -- CORE: trusts its inputs, raises typed errors.
def pay_invoice(invoice_id: UUID, amount_cents: int) -> Invoice:
    invoice = repo.get(invoice_id)                        # raises InvoiceNotFoundError
    if invoice.is_paid:
        raise InvoiceAlreadyPaidError(invoice_id)
    return repo.mark_paid(invoice, amount_cents)
```

## 7. Dead code

Delete unused imports, parameters, private helpers, and feature flags in the same PR that makes them unreachable. Dead code compounds — it confuses future readers and accumulates bit-rot.
