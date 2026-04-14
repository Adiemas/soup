# Python 3.13 — `pkgutil.ImpImporter` removed

## Symptom

```
AttributeError: module 'pkgutil' has no attribute 'ImpImporter'
```

Or, during a fresh install:

```
ModuleNotFoundError: No module named 'distutils'
```

Or (looks different but same root cause):

```
ImportError: cannot import name 'Mapping' from 'collections'
```

Usually appears when running `pip install -e .`, `poetry install`,
`uv pip install`, or importing a package whose wheel was built against
Python 3.11 or older.

## Cause

Python 3.13 removed several long-deprecated compatibility shims:

- `pkgutil.ImpImporter` (gone — deprecated since 3.4).
- `distutils` (gone — deprecated since 3.10, removed in 3.12).
- Several `collections` aliases for `collections.abc` types.

Dependencies that still reference these APIs now crash at import time.
The most common culprits in internal stacks:

- **setuptools < 72** — used `pkgutil.ImpImporter` in its bootstrap.
- **poetry-core < 1.9.1** — imported `distutils` in some build hooks.
- **Ancient wheels** pinned in a `requirements.txt` that were never
  re-released for 3.13 (numpy < 1.26, pandas < 2.1, pydantic < 2.5,
  asyncpg < 0.29, psycopg2-binary < 2.9.9).

The warhammer-40k-calculator dogfood hit this with a committed venv
built against 3.13 plus a `requirements.txt` pinning setuptools 68.
(See `docs/real-world-dogfood/warhammer-40k-calculator.md` §"State of
the multi-agent setup" — the repo had six `requirements*.txt` variants
trying to paper over this.)

## Fix

### Fast path: upgrade setuptools + pip

```bash
python -m pip install --upgrade pip setuptools wheel
# Then retry the original install.
pip install -e .
```

With uv:

```bash
uv pip install --upgrade pip setuptools wheel
uv sync
```

If setuptools is already new but a transitive dep still fails,
identify the offender:

```bash
pip check
pip show <suspected-package> | grep -i python-requires
```

### Slow path: downgrade to Python 3.12

If a transitive dep has no 3.13-compatible release and you cannot
unpin it (common with internal forks of numpy/pandas), pin the
interpreter:

```bash
# uv (recommended)
uv venv --python 3.12 .venv
# or with pyenv
pyenv install 3.12.7
pyenv local 3.12.7
python -m venv .venv
```

Document the pin in the project's `README.md` and `pyproject.toml`:

```toml
[project]
requires-python = ">=3.12,<3.13"
```

Keep the 3.13 venv as a future goal; the first time `pip check` passes
clean with 3.13, flip the requirement.

### What NOT to do

- **Do not commit `python-3.12.x-amd64.exe` into the repo.** That was
  the warhammer anti-pattern — a 30 MB installer in git history. Use
  `uv` or `pyenv` instead.
- **Do not ship parallel `requirements-python312.txt` +
  `requirements-python313.txt`.** A single `pyproject.toml` with a
  `requires-python` pin plus a lockfile is always preferable.

## Related

- `rules/python/coding-standards.md` — pin Python version in
  `pyproject.toml`.
- `rules/global/security.md` — do not commit binaries.
- `.claude/agents/python-dev.md` — invoked when this symptom appears
  during a Python build step.
- `logging/experiments.tsv` — record the interpreter version alongside
  the run so postmortems can correlate.
