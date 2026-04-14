# Anthropic API — 429 rate limit (retry + model downgrade)

## Symptom

```
anthropic.RateLimitError: 429 {"type": "error", "error": {"type": "rate_limit_error", "message": "..."}}
```

Or, equivalently, in the raw HTTP:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 12
```

Usually hits during a plan run with multiple parallel subagents on
`opus`, during an ingest/RAG storm, or when a test suite burns through
the shared org budget right before your run.

## Cause

Anthropic applies **per-workspace** rate limits across three axes:

- Requests per minute (RPM).
- Input tokens per minute.
- Output tokens per minute.

Opus has the tightest per-minute caps; haiku has the loosest. A single
`go` run at Opus that fans out three reviewers + ingests a large spec
can easily hit the RPM ceiling — and a run during peak workspace
activity can hit tokens/minute independently.

429s also fire from Anthropic-side anti-abuse when request bursts
look automated; exponential backoff with jitter is the expected
client response.

## Fix

### 1. Detect 429 in the transport

Wrap the call in a jittered-exponential backoff. For the
Anthropic Python SDK, the client already retries idempotent requests
on 429 — but the default retry count (2) is too low for opus bursts:

```python
from anthropic import AsyncAnthropic

client = AsyncAnthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    max_retries=5,                 # default is 2
    timeout=60.0,
)
```

The SDK honors the `Retry-After` header when present. No extra
plumbing needed.

If you are on the raw HTTP client:

```python
import random
import time

def backoff(attempt: int, *, base: float = 1.0, cap: float = 60.0) -> float:
    """Jittered exponential: min(cap, base * 2**attempt) + uniform noise."""
    return min(cap, base * (2 ** attempt)) + random.uniform(0, 1)
```

Retry on HTTP 429 and HTTP 5xx; do not retry on 4xx other than 429.

### 2. Downgrade to haiku when opus is saturated

If retries keep bouncing off 429 and the work is **not** opus-critical
(architecture, SQL migration review, plan synthesis), downgrade the
tier:

```python
# inside the orchestrator retry loop, or in meta_prompter.py
if isinstance(err, RateLimitError) and attempt >= 3 and step.model == "opus":
    step.model = "sonnet"
    # or "haiku" for plain drafting work
    _LOGGER.warning("rate-limit downgrade S=%s opus->%s", step.id, step.model)
```

Guardrails:

- **Never auto-downgrade `sql-specialist` or `architect` steps.** Their
  model tier is a correctness requirement, not a cost knob. Let them
  block on rate limit and surface the error.
- Log every downgrade to `logging/experiments.tsv` so postmortems can
  spot runs where quality regressed silently.
- Sonnet is the safe default downgrade; haiku is only correct for
  low-stakes drafting (doc-writer, simple extraction).

### 3. Throttle concurrency at the orchestrator level

If you hit RPM even with retries, the fix is fewer parallel subagents,
not bigger backoffs. Cap `orchestrator` wave width — see
`orchestrator/orchestrator.py` for the `max_parallel_per_wave` knob.

## What NOT to do

- **Do not disable retries.** Anthropic's rate limiter is a
  fairness mechanism; hammering it makes latency worse for everyone on
  your workspace.
- **Do not silently swallow 429** and continue with cached results —
  you will end up shipping stale plans into production runs.

## Related

- `orchestrator/meta_prompter.py` — retry loop that this runbook
  informs.
- `rules/global/security.md` — API key handling; the key itself
  never leaves the orchestrator process.
- `logging/experiments.tsv` — where rate-limit downgrades should be
  surfaced post-run.
- Anthropic docs: https://docs.anthropic.com/en/api/rate-limits
