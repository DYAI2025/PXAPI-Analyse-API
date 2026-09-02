# PXAPI — Pixelkiez Website Analysis Platform

PXAPI is a Python **modular monolith** built as **Ports & Adapters**.

> **This repository holds the scaffold (A3 / PXK-16) plus the v1 contracts and the Analysis Run
> state machine (A4 / PXK-17).** It contains **no** analysis, measurement, crawling, SERP,
> business-context, synthesis, scoring, product-diagnosis, customer-projection, rendering,
> persistence or API capability. Nothing here analyses a website yet. The contracts fix the
> shapes those capabilities will produce; the state machine fixes the run lifecycle; the layout
> and the boundary rules exist so that the slices which add the capabilities cannot quietly
> violate the architecture.

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
│   ├── run_state.py         the 19 run states and the 27 approved transitions (A4)
│   └── stage_execution.py   stage vocabulary and the Pass-1 projection onto run states (A4)
├── ports/         explicit boundaries the application talks through
├── application/   orchestration; depends on domain + ports (and itself)
├── adapters/      implementations that bind ports to the outside world
└── config/        configuration primitives; a leaf, depends on no other pxapi layer

contracts/v1/        the language-neutral v1 contracts: manifest, JSON Schemas, valid examples
                     (see contracts/README.md for versioning, categories and semantics)
tests/architecture/  the import-boundary guard (and the proofs it can fail)
tests/contracts/     schema meta-rules, valid examples, targeted invalid fixtures, vocabulary parity
tests/domain/        transition matrix (27 legal / 334 illegal, derived) and Pass-1 projection
oracle/              frozen regression oracle from A2 — reference evidence, not application code
docs/evidence/       per-slice verification records
```

### Dependencies

| Group | Packages | Why |
| --- | --- | --- |
| runtime (`[project].dependencies`) | *none* | no runtime behaviour needs one; `src/` is standard library only |
| dev | `pytest`, `ruff`, `jsonschema` | test runner, lint/format, Draft 2020-12 validation of the contracts **in tests only** |

`jsonschema` is deliberately not a runtime dependency: A4 ships no validator port or adapter.
The slice that validates documents at runtime decides where that dependency lives.

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

## The `oracle/` directory

`oracle/website-diagnosis/` is the frozen A2 regression oracle: a record of the behavior of the
separate, pre-existing `pixelkiez-website-diagnosis` tool — **not** of PXAPI. It is kept as
migration evidence, and it is **not** application code and **not** a source to copy from.

## CI

`.github/workflows/python-compat.yml` runs, on Python 3.13 and 3.14: `uv sync --locked`,
`uv lock --check`, `ruff check`, `ruff format --check`, and `pytest`. That is its entire remit.
The full repository CI/security/quality gate is a separate slice (A8).
