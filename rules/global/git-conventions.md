# Git conventions

## 1. Conventional Commits

Every commit subject uses the Conventional Commits format:

```
<type>(<scope>): <imperative summary in ≤72 chars>
```

Allowed types:

| Type     | Meaning                                                      |
|----------|--------------------------------------------------------------|
| `feat`   | User-visible new capability                                  |
| `fix`    | Bug fix                                                      |
| `refactor` | Behavior-preserving change                                 |
| `perf`   | Performance improvement (with measurement)                   |
| `test`   | Tests only (no production change)                            |
| `docs`   | Documentation only                                           |
| `build`  | Build system, dependencies, tooling                          |
| `ci`     | CI config / pipelines                                        |
| `chore`  | Housekeeping (no src change)                                 |
| `style`  | Formatting, whitespace (prefer a formatter; rarely needed)   |
| `revert` | Revert of a prior commit (`revert: <subject>`)               |

Scope is the module/package/feature, lowercase: `feat(invoices): ...`, `fix(auth): ...`.

Breaking changes: append `!` after the type/scope AND include a `BREAKING CHANGE:` footer.

## 2. Atomic commits

1. **One TaskStep = one commit.** If you can't describe the diff in one sentence, split it.
2. A commit should build, lint, and pass tests on its own. `git bisect` must remain useful.
3. Never mix refactor + feature in one commit. Refactor first (green), then add the feature.
4. Never mix formatting churn with logic changes. If a formatter ran, commit that separately as `style(scope): ...`.

## 3. Commit body

The body (optional, but preferred for non-trivial changes):

- Explains **why** the change is being made, not what (the diff shows what).
- Wraps at ~72 chars.
- References the spec/task: `Spec: specs/023-invoices.md`.
- Mentions ticket IDs: `Refs: ADO-1234, #456`.

Example:

```
feat(invoices): add partial-payment support

Previously `pay_invoice` required amount == invoice.total_cents. The
business now accepts partial payments; remaining balance is tracked
on the invoice and settled on subsequent calls.

Spec: specs/023-partial-payments.md
Refs: ADO-4821
```

## 4. Branch naming

```
<type>/<scope>-<short-kebab-description>
```

Examples:

- `feat/invoices-partial-payments`
- `fix/auth-token-refresh-race`
- `refactor/orchestrator-worktree-cleanup`

Long-lived branches: `main` (protected). No `develop` — trunk-based.

## 5. Rebase vs. merge

1. Feature branches rebase onto `main` before PR merge (linear history).
2. `main` never gets a merge commit from a feature branch unless the PR carries >1 meaningful commit (release train case).
3. Never force-push to `main`. Force-pushes to feature branches are fine **before** review starts; after, use `--force-with-lease`.

## 6. Hooks & signing

1. Never use `--no-verify` — pre-commit hooks are part of the contract. If a hook fails, fix the cause.
2. Commits should be signed (`user.signingkey` configured); CI verifies on merge to `main`.
3. The Stop hook's QA gate runs **before** the PR is opened, not after. Don't open a PR on a BLOCK verdict.

## 7. PRs

1. Title = commit subject.
2. Description links the spec (`specs/`), the plan (`plans/`), and the QA report.
3. Small PRs merge faster; target <400 lines changed when feasible.
4. Squash-merge from GitHub/ADO **only** if the branch has junk commits; otherwise preserve history as is.
