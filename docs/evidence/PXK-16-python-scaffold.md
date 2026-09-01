# PXK-16 — Python Modular-Monolith Scaffold (Slice A3)

**Jira key:** PXK-16 (PXAPI A3 — Scaffold Python modular monolith baseline)
**Parent:** PXK-8 — PXAPI Foundation & Boilerplate
**UTC verification timestamp:** 2026-09-01T22:35:39Z
**Status:** implementation complete and locally verified — **not merged, not accepted**. Every
result below is agent-reported until the orchestrator independently re-derives it at the exact head.

This document separates three claims that are easy to conflate: the canonical source baseline (A),
what Git reports about the project source (B), and the boundary around local agent-runtime state (C).

---

## A. Source baseline

| Property | Verified value |
| --- | --- |
| Repository identity | `DYAI2025/PXAPI-Analyse-API` |
| Origin remote form | `https://github.com/DYAI2025/PXAPI-Analyse-API.git` (approved, credential-free) |
| Local path check | PASS — expected repository path verified; absolute workstation path intentionally omitted |
| Base commit (fetched `origin/main`) | `f2d2a79c6e4be22e18360e3a4a03e1dfbba28ba1` |
| Base drift at branch time | none — fetched `origin/main` equalled the authority SHA exactly |
| Branch | `feat/pxk-16-python-scaffold`, created from that exact SHA |
| Head at time of writing | `004e67b6b9fe0e105946f5a681e678a5805ff0c2` |

### Commits

| SHA | Subject |
| --- | --- |
| `b40a2a1` | chore: add uv project baseline for Python 3.13 primary / 3.14 compatible |
| `3b30e4e` | docs: add bootstrap and architecture README |
| `bb0499e` | feat: add empty five-layer pxapi package skeleton |
| `25629ac` | test: add stdlib AST import-boundary checker and green proof |
| `65fb2f2` | test: prove the import-boundary guard turns RED on every forbidden edge |
| `bd028a4` | test: assert the scaffold is importable, documented and behavior-free |
| `81c88e0` | ci: add narrow Python 3.13/3.14 compatibility job |
| `914e066` | docs: correct README accuracy against the shipped configuration |
| `a884922` | fix: govern the pxapi root package and undeclared sibling packages |
| `004e67b` | fix: pin a resolvable setup-uv ref and anchor the oracle lint exclusion |

The last three commits are remediation of defects found by review after the initial implementation
was believed complete. They are listed rather than squashed because the defects they fix are the
most instructive part of this slice — see section G.

## B. Project-source cleanliness

`git status --porcelain` returned **no lines** at the time of writing, and
`git diff --name-status f2d2a79c..HEAD` is **20 lines, every one status `A`** — the 19 scaffold
files listed in section D plus this evidence document — with zero modifications and zero deletions.

This is a statement about **project source as Git reports it**. It is deliberately *not* a claim
that the physical directory contains nothing else — see section C.

## C. Local agent-runtime boundary

The verifying workstation runs a local agent whose hook regenerates
`.claude/homunculus/observations.jsonl` inside the work tree on essentially every tool call. It
remains excluded through the workstation-local `.git/info/exclude` rule established by PXK-14. A3
deliberately did **not** move that rule into the committed `.gitignore`: the repository commits no
policy about anyone's local tooling. `__pycache__/` and `.venv/` also exist physically and are
covered by the committed `.gitignore`.

---

## D. What A3 delivers

19 scaffold files, plus this evidence document (20 added paths in total). No modifications to
anything pre-existing.

```
.gitignore                                          .github/workflows/python-compat.yml
.python-version                                     README.md
pyproject.toml                                      uv.lock
src/pxapi/__init__.py                               src/pxapi/py.typed
src/pxapi/{domain,ports,application,adapters,config}/__init__.py
tests/__init__.py                                   tests/architecture/__init__.py
tests/architecture/boundaries.py                    tests/architecture/test_boundaries.py
tests/architecture/test_boundaries_detect_violations.py
tests/test_package_scaffold.py
```

### Direct dependencies — three, each justified

| Dependency | Kind | Why |
| --- | --- | --- |
| `pytest` 9.1.1 | dev | AC2 test runner; also executes the architecture guard |
| `ruff` 0.16.5 | dev | AC2 lint **and** format — one tool, so no second formatter dependency |
| `hatchling>=1.27` | build | so `uv sync` installs `pxapi` as a real package. The `>=1.27` floor is load-bearing: older hatchling silently degrades the PEP 639 `License-Expression` to the legacy field instead of erroring |

Runtime `dependencies` is **empty**, which is the honest state of a scaffold. No framework, database
or cloud SDK was added in anticipation of later slices.

### Supported Python range

`requires-python = ">=3.13,<3.15"`. 3.13 is primary (pinned in `.python-version`, selected by a bare
`uv run`); 3.14 is supported and exercised. A **single** `uv.lock` serves both — no fork, no
version-gated markers.

### Architecture boundary mechanism

`tests/architecture/boundaries.py` — standard library only, no architecture framework. It parses
each module with `ast` and **never imports it**, which is what lets it flag a forbidden
`import fastapi` in `domain` while FastAPI is not installed at all; an import-time check
structurally cannot do that. `check_tree()` is a pure function over a directory, so every RED proof
runs against a throwaway tree in pytest `tmp_path` and the committed source is never touched.

| zone | may import from `pxapi` | third-party |
| --- | --- | --- |
| `pxapi` itself (root) | nothing | no |
| `domain` | `domain` | no |
| `ports` | `ports`, `domain` | no |
| `application` | `application`, `ports`, `domain` | no |
| `adapters` | `adapters`, `application`, `ports`, `domain`, `config` | **yes** |
| `config` | `config` | no |
| any other package under `pxapi/` | refused outright | — |

`adapters` may import `application` because the brief's rule is "adapters may depend inward"; a
driving adapter calls use cases by definition. The reverse edge is banned, which is what AC3/AC4
require. `config` is a leaf rather than a composition root, so it has an enforceable rule at all.

### Compatibility workflow

`.github/workflows/python-compat.yml` — matrix `["3.13","3.14"]`, five steps: `uv sync --locked`,
`uv lock --check`, `ruff check`, `ruff format --check`, `pytest`. Triggers: `push` (all branches)
and `pull_request`. `permissions: contents: read`.

**Its remit ends there.** The full repository CI/security/quality gate remains **A8**: no security
scanning, no secret scanning, no dependency security gate, no migration smoke, no API-auth tests,
no SSRF gate, no deployment gate, no regression-oracle orchestration.

---

## E. Verification results

All local. Every exit code read from a bare command, never through a pipe.

### Clean install from the committed lockfile — AC1

Run in a **fresh `git clone` of the branch with an empty `UV_CACHE_DIR`**, because a warm `.venv`
proves nothing:

| command | exit |
| --- | --- |
| `uv sync --locked` | 0 |
| `uv lock --check` | 0 |
| `uv run pytest -q` → `38 passed` | 0 |
| `uv run ruff check .` | 0 |
| `uv run ruff format --check .` | 0 |

### Both interpreters — AC2, AC6

| interpreter | pytest | ruff check | ruff format |
| --- | --- | --- | --- |
| CPython **3.13.3** (primary) | **38 passed**, exit 0 | 0 | 0 |
| CPython **3.14.6** | **38 passed**, exit 0 | 0 | 0 |

Both were executed locally from the same lockfile; neither is a limitation to report. Tooling:
uv 0.9.16, pytest 9.1.1, ruff 0.16.5.

Suite composition: `test_boundaries.py` 3, `test_boundaries_detect_violations.py` 23,
`test_package_scaffold.py` 12 — **38** collected.

### The gates were observed failing, not merely observed green

A gate that has never failed is `not_run`, not `passed`. Each was deliberately broken and seen red:

| gate | mutation | result |
| --- | --- | --- |
| boundary guard | `_judge` returns `[]` | 18 of 38 fail |
| boundary guard | `_iter_imports` yields nothing | 18 of 38 fail |
| boundary guard | `AC3_BANNED_ROOTS` → empty | 6 fail |
| boundary guard | `LAYER_IMPORTS` → everything permitted | 6 fail |
| boundary guard | `THIRD_PARTY_ALLOWED` → all zones | 9 fail |
| boundary guard | `ROOT_ALLOWED` → all layers | 1 fails |
| boundary guard | ungoverned-package check disabled | 2 fail |
| AC5 scope gate | append `X = 1` to `src/pxapi/domain/__init__.py` | fails, naming `['domain/__init__.py']` |
| ruff exclusion | drop `extend-exclude` | 5 × E501 return from the frozen oracle |

No surviving mutant. Every mutation was verified to have actually applied before its run — a first
attempt using `frozenset() or frozenset(...)` was a no-op that produced a false "surviving mutant",
which is exactly the failure mode this table exists to exclude.

The AC5 gate and the boundary guard are **complementary, not redundant**: under the `X = 1`
mutation the boundary test stays green, because `check_tree` only walks `Import`/`ImportFrom` nodes
and an assignment creates no edge. Each covers a failure class the other cannot see.

All mutations ran against copies outside the repository, or were reverted and checksum-verified.
`git status --porcelain` and `git diff HEAD --stat` were both empty afterwards.

---

## F. Scope and regression

### Frozen prior-slice evidence — unchanged

All six files tracked at the base commit are byte-identical at head:

| blob | path |
| --- | --- |
| `879f2ed27bacaeff729173adb33c3502cc05a53f` | `LICENSE` |
| `2f9dd9b716438a28791003565b168aec83316781` | `docs/evidence/PXK-14-repository-preflight.md` |
| `6fa10e33040a57a7e2ab8a1d63d4c75356589db6` | `docs/evidence/PXK-15-website-diagnosis-regression-oracle.md` |
| `0b12f0e3c1ea5e7b9241672d9ea386185210221b` | `oracle/website-diagnosis/README.md` |
| `ca34a19187bacf2ef050880809adbf0671133843` | `oracle/website-diagnosis/oracle-manifest.json` |
| `deec59527a3b89287cd908b514d6dfd0ff5142ab` | `oracle/website-diagnosis/oracle_probe.py` |

`git diff f2d2a79c..HEAD -- LICENSE docs oracle` is empty. Protection is also **preventive**:
`oracle/` and `docs/evidence/` are outside ruff's scope via `extend-exclude` plus
`force-exclude = true`, so A3 tooling cannot rewrite them even when a path is passed explicitly.
This matters because ruff formats Python code fences inside Markdown, which put the frozen PXK-15
evidence document inside `ruff format`'s write scope until the exclusion was added.

### No analysis implementation was introduced — AC5

Every file under `src/pxapi/` is an `__init__.py` containing a module docstring and nothing else,
plus the zero-byte `py.typed`. `test_scaffold_declares_no_behavior` asserts this by AST, so no
scoring, measurement, SERP, synthesis, projection or rendering implementation can be present —
because no executable statement can be present at all.

A vocabulary scan of `src/pxapi/` for `score|scoring|metric|serp|crawl|render|pdf|analysis_run|
measurement|diagnos` returns exactly two hits, both inside the root docstring's sentence *denying*
those capabilities. No Website Diagnosis logic was copied from `oracle/`.

### Nothing pulled forward from later slices

No canonical contracts, Analysis Run state machine, schema inventory, measurement collector,
crawler, HTTP/SSRF handling, SERP logic, business context, AI/LLM adapter, scoring formula, product
diagnosis, customer projection, report rendering, FastAPI endpoint, CLI use-case interface,
SQLAlchemy, Postgres run store, S3/artifact store, boto3 or other cloud SDK, auth, API key, CRM
integration, self-service, email delivery, Docker or deployment configuration.

---

## G. Defects found by review, and fixed

Recorded because they are the most transferable output of this slice. Each was reproduced before
being fixed, and re-measured after.

1. **`astral-sh/setup-uv@v10` was not a resolvable ref.** The pin came from reading the *releases*
   API (latest `v10.0.1`) and assuming a floating major tag existed. It does not: that repository
   publishes moving major tags only through `v7`, and `git/ref/tags/v10` returns 404. Both matrix
   jobs would have failed before running any Python. Now pinned to `v10.0.1`, verified to resolve.
   `actions/checkout@v7` does exist and was left unchanged.
2. **Three ways to reach `adapters` or a banned dependency with the gate fully green.**
   `src/pxapi/__init__.py` was exempt from every rule; any package under `pxapi/` outside the five
   declared layers was entirely ungoverned *and* freely importable by inner layers; and bare
   `import pxapi` reached every layer by attribute access. All three returned **zero** violations
   before the fix. The root package is now its own zone, undeclared siblings are refused, and bare
   package imports are rejected — with committed RED proofs for each.
3. **`ruff check .` failed on the frozen oracle.** Five E501 violations in
   `oracle/website-diagnosis/oracle_probe.py` made AC2 unachievable. Since that file must never be
   reformatted, the fix was to take it out of lint scope, not to touch it.
4. **`extend-exclude = ["oracle"]` was an unanchored basename match**, silently un-linting any
   directory named `oracle` at any depth — including a plausible future
   `src/pxapi/adapters/oracle/`. Corrected to `"oracle/*"`, verified to keep the frozen artifact
   excluded while restoring linting of nested paths.
5. **The third-party ban had rules but no tests for `ports` and `config`.** RED proofs added.

Two environment traps produced *silently vacuous* measurements during this work and are worth
carrying forward: a local hook rewrites bare `python3 -c` into an error line, and bare `git` was
observed vanishing inside a shell loop — the latter made a reviewer's diffs compare empty against
empty and pass. Both yield green results that mean nothing.

---

## H. Deliberately deferred

- `ban-relative-imports = "all"` in ruff — the AST guard enforces direction more precisely; adding
  unrequested lint configuration would be over-building.
- Dynamic imports (`__import__`, `importlib.import_module`, `exec`) are outside a static checker's
  reach by construction. The guard does not claim to catch them.
- Widening `THIRD_PARTY_ALLOWLIST` for an inner layer must remain an explicit, reviewed edit.
- Pinning the `uv` version in CI — the compatibility matrix currently tracks the latest uv.

## I. Status of this document

The results above are **AGENT_REPORTED**. This slice is **not merged** and PXK-16 is **not**
transitioned to Done.

**CI has since executed and passed** — recorded here because it is now observed fact rather than a
prediction from the YAML:

| run | event | jobs | conclusion |
| --- | --- | --- | --- |
| `33567255569` | `push` | `py3.13`, `py3.14` | success |
| `33567284722` | `pull_request` | `py3.13`, `py3.14` | success |

Pull request: [#4](https://github.com/DYAI2025/PXAPI-Analyse-API/pull/4), head
`afdc9584f83e3f0c637ed5ccc49da1cb936e9c06`, base `main` at
`f2d2a79c6e4be22e18360e3a4a03e1dfbba28ba1`, `merged: false`. This repository also has a Sourcery
review app that posts a check on pull requests, so "no CI is configured here" would be false.

Note that this section, and the head SHA it names, necessarily predate the commit that records
them. The orchestrator should re-derive both against the actual PR head.
