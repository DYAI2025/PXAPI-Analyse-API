# PXAPI — Pixelkiez Website Analysis Platform

PXAPI is a Python **modular monolith** built as **Ports & Adapters**.

> **This repository is scaffold plus a contract foundation (slices A3 / PXK-16, PXK-59 and
> PXK-60).** It contains **no** analysis, measurement, crawling, SERP, business-context,
> synthesis, scoring, product-diagnosis, customer-projection, rendering, delivery, persistence,
> orchestration or API capability. Nothing here analyses a website, runs a stage or stores
> anything. The layout and the boundary rules exist so that the slices which add those
> capabilities cannot quietly violate the architecture; `contracts/` adds the versioned
> vocabulary they will speak, as data rather than behavior. PXK-60 adds the first executable
> Domain module — the coarse Analysis Run lifecycle — and nothing else executable.

## Supported Python versions

| Version | Role |
| --- | --- |
| **3.13** | primary baseline — pinned in `.python-version`, used by default |
| **3.14** | supported; verified on every push by the compatibility job |

`requires-python = ">=3.13,<3.15"`.

## Prerequisites

[**uv**](https://docs.astral.sh/uv/) is the only prerequisite; it manages both the interpreter and
the dependencies. Install it per the [official instructions](https://docs.astral.sh/uv/getting-started/installation/).

## Bootstrap

```bash
uv sync --locked      # deterministic install from the committed uv.lock
```

`--locked` fails instead of silently re-resolving, so a stale lockfile is an error rather than a
surprise. Use plain `uv sync` only after intentionally changing dependencies (then commit the
regenerated `uv.lock`).

## Everyday commands

```bash
uv run pytest                      # full test suite
uv run ruff check .                # lint
uv run ruff format .               # format
uv run ruff format --check .       # verify formatting without writing

uv run --python 3.14 pytest        # run the suite on the compatibility interpreter
```

Switching interpreter rebuilds `.venv` — uv removes and recreates it each time you cross between
3.13 and 3.14, in both directions. That is expected, not a fault.

**What the ruff commands actually cover.** `oracle/` and `docs/evidence/` are excluded in
`pyproject.toml`, so neither is linted or formatted; editing a file there and seeing
`N files already formatted` does **not** mean your file was checked. Note also that `ruff check`
inspects no Markdown at all, while `ruff format` does reach Python code fences inside `.md` —
which is why the root `README.md` is deliberately left in scope.

## Repository structure

```
src/pxapi/
├── domain/        innermost ring — no framework, no database, no cloud SDK, no third party
├── ports/         explicit boundaries the application talks through
├── application/   orchestration; depends on domain + ports (and itself)
├── adapters/      implementations that bind ports to the outside world
└── config/        configuration primitives; a leaf, depends on no other pxapi layer

contracts/v1/        the versioned contract registry: manifest, schemas, valid examples
tests/architecture/  the import-boundary guard (and the proofs it can fail)
tests/contracts/     the contract validation harness and its invalid fixtures
tests/domain/        the run-state transition matrix and the orthogonality proofs
oracle/              frozen regression oracle from A2 — reference evidence, not application code
docs/evidence/       per-slice verification records
```

### Contracts are data, and the harness is test-only

`contracts/v1/manifest.json` is the single inventory of PXAPI contracts. The validation harness
under `tests/contracts/` derives everything from it — which contracts exist, their versions,
their schemas and examples — so registering a contract needs no change to any test. Each contract
carries its own version; there is no global contracts version. See
[`contracts/README.md`](contracts/README.md) for the registry model, the versioning rules, the
consumer compatibility rules and the Problem producer rule.

`jsonschema` and `referencing` are **dev/test dependencies only**. Nothing under `src/pxapi`
imports a validator, and `tests/contracts/test_dependency_isolation.py` fails if that changes.

### The architecture rule is executable, not documentation

| layer | may import from `pxapi` | third-party allowed |
| --- | --- | --- |
| `domain` | `domain` | no |
| `ports` | `ports`, `domain` | no |
| `application` | `application`, `ports`, `domain` | no |
| `adapters` | `adapters`, `application`, `ports`, `domain`, `config` | **yes** |
| `config` | `config` | no |

Dependencies point inward only. `tests/architecture/boundaries.py` enforces this by parsing every
module with `ast` — it never imports them, so it catches a forbidden `import fastapi` in `domain`
even when FastAPI is not installed. `tests/architecture/test_boundaries_detect_violations.py`
proves each rule genuinely fails when violated, so the guard cannot rot into a vacuous pass.

Adding a dependency to an inner layer is therefore a deliberate, reviewable edit to
`LAYER_IMPORTS` / `THIRD_PARTY_ALLOWLIST` — never an accident.

### Behavior exists only where a slice authorised it

A3 forbade every executable statement under `src/pxapi`: a scope gate that made it impossible
for scoring, measurement, synthesis, projection, rendering, persistence or an adapter to appear
by accident. PXK-60 adds the first real module, so the gate is **narrowed rather than dropped**.
`BEHAVIOR_ALLOWED` in `tests/test_package_scaffold.py` names each authorised module and the
slice that authorised it; every other module must still be a docstring and nothing else, and an
entry that is stale, unearned, outside a layer or blanket fails on its own. Today the mapping
holds exactly one entry:

| module | authorised by |
| --- | --- |
| `domain/run_state.py` | PXK-60 |

### The Analysis Run lifecycle

`src/pxapi/domain/run_state.py` is data plus one decision: is `current -> target` an approved
edge? It reads no store, consults no clock and knows nothing about stages. The vocabulary and
the approved edges are described in [`contracts/README.md`](contracts/README.md#the-analysis-run-lifecycle-and-scan-mode);
this module is the authority on which transitions are legal, and the contract is the authority
on what a persisted document looks like. `tests/domain/` decides all 36 ordered state pairs and
mechanically forbids a stage-to-run projection from reappearing.

## The `oracle/` directory

`oracle/website-diagnosis/` is the frozen A2 regression oracle: a record of the behavior of the
separate, pre-existing `pixelkiez-website-diagnosis` tool — **not** of PXAPI. It is kept as
migration evidence, and it is **not** application code and **not** a source to copy from.

## CI

`.github/workflows/python-compat.yml` runs, on Python 3.13 and 3.14: `uv sync --locked`,
`uv lock --check`, `ruff check`, `ruff format --check`, and `pytest`. That is its entire remit.
The full repository CI/security/quality gate is a separate slice (A8).
