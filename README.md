# PXAPI — Pixelkiez Website Analysis Platform

PXAPI is a Python **modular monolith** built as **Ports & Adapters**.

> **This repository analyses one public homepage, and nothing more** (slices A3 / PXK-16,
> PXK-59, PXK-60, PXK-61, PXK-67 and PXK-20.A). PXK-67 added the first vertical product
> path: a real public URL in, real HTTP and HTML observations out, as canonical contract
> documents. PXK-20.A adds the first *actionable* step on that path — three fixed rules turn
> established website evidence into evidence-bound diagnostic findings. The repository
> contains **no** scoring, score model, severity, confidence, ranking or intervention level, and
> no product diagnosis, contextual synthesis, customer projection, rendering, delivery,
> persistence, queueing, browser execution, SERP or business-context capability, and **no
> authentication, authorisation, rate limiting or deployment**. It does not crawl: it fetches
> exactly one page. `contracts/` remains the versioned vocabulary, as data rather than
> behavior, and is still the single contract authority.

## Analysing a page

```bash
# the command line, which is what the real-boundary smoke uses
uv run python -m pxapi.adapters.inbound.cli https://example.com/

# the same use case over HTTP
uv run uvicorn pxapi.adapters.inbound.http_api:app --port 8000
curl -sS -X POST localhost:8000/v1/analysis-runs -H 'Content-Type: application/json' -d '{
  "schema_version": "1.0.0", "run_id": "run-1", "request_id": "req-1",
  "requested_at": "2026-09-07T10:00:00Z", "target_url": "https://example.com/",
  "scan_mode": "PUBLIC_NON_INVASIVE"
}'
```

Both return the same canonical envelope — the accepted request, the run state, the stage
executions, the measurements, the website evidence and the diagnostic findings — in which
**every member validates against its own merged contract on its own**. The envelope itself
is deliberately not a registered contract: it adds no analysis meaning, and registering it
would create a second authority beside the contracts it carries.

**A technical failure is never a finding about the website.** A timeout, a DNS failure, a
refused target, a broken parser and a response we cannot decode each record why *our process*
did not measure — carrying no value and no polarity — and fail the run rather than the site.
Three states are kept apart: *absent* is a fact about the site, *not applicable* a fact about
the measurement, and *unknown* an assessment that established nothing.

### Findings rest on evidence, and nothing else

A `diagnostic-finding` is the first document allowed to speak about a site in ordinary
language, so the chain behind it is enforced in code:

```
DiagnosticFinding.evidence_refs
  -> WebsiteEvidence.evidence_id
    -> WebsiteEvidence.measurement_refs
      -> MeasurementRecord.measurement_id
```

A finding exists only where the evidence belongs to this run, was itself `KNOWN`, and
references a measurement of this run that established a value. There is deliberately no path
from a raw measurement to a conclusion.

Four rules are implemented, each at version `1.0.0`: `HTTP_ERROR_RESPONSE` (a `KNOWN` status
of 400 or above), `NON_HTTPS_FINAL_TRANSPORT` (a final response `KNOWN` to be plain HTTP),
`MISSING_HOMEPAGE_TITLE` (title presence `KNOWN` to be false) and `HOMEPAGE_EXPLICIT_NOINDEX`
(a generic noindex directive `KNOWN` to be present). Each rule's four product texts —
summary, business impact, recommended action and limitation — are **constants, not templates**:
no measured value is interpolated into them, which is why a 418 and a 503 produce byte-identical
texts and the number stays in the contract-validated measurement record.

**An empty `diagnostic_findings` means only that these four rules emitted nothing.** It never
means the website is good, complete, compliant or fully assessed.

### Homepage indexability is observed on two channels, and combined once

A generically applicable `noindex` directive can arrive in a document's
`<meta name="robots">` declarations or in the response's `X-Robots-Tag` headers, so each
channel is recorded on its own — `META_ROBOTS_GENERIC_NOINDEX_PRESENT` and
`X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT` — and `HOMEPAGE_GENERIC_NOINDEX_PRESENT` carries the one
result the rule decides on. **Generic means "not addressed to a named crawler"**: an
`X-Robots-Tag: googlebot: noindex` is outside the generic verdict, which makes that verdict
`false` rather than unknown, and nothing here infers how any named crawler behaves.

One channel that established the directive settles it; one channel that established *nothing*
— an ambiguously scoped header, a read truncated at our byte bound, a document we could not
decode or parse — forbids concluding an absence. A channel that does not apply, such as an HTML
declaration in a response that is not a document, does not hold the result open. **No
`noindex` claim is made about a site whose response never arrived.**

This establishes only that a directive was *observed in this response*. It does not establish
current index status, rankings or traffic.

### Which destinations may be fetched

`http` and `https` only, no credentials in the URL authority, and every resolved address must
be public — loopback, private, link-local (where cloud metadata lives), unspecified, multicast,
reserved, carrier-grade NAT and unique-local are all refused. **A host is refused outright if
any one of its addresses is forbidden**, and the connection is made to the address that was
validated rather than to the hostname, so a name cannot be rebound between the check and the
connect. Redirects are followed by hand, and every hop is re-validated and re-resolved.

The shipped policy takes no argument that could widen that rule. Integration tests reach a
loopback server by subclassing it in test code, never by configuring the product.

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

`jsonschema` and `referencing` are **runtime dependencies as of PXK-67**, because the HTTP
boundary validates what arrives and what leaves against the same registry the tests use. The
old blanket rule — nothing under `src/pxapi` may import a validator — was **narrowed rather
than dropped**, the way PXK-60 narrowed the behavior gate: `domain`, `ports`, `application` and
`config` may still never import one, and exactly one allowlisted adapter may.
`tests/contracts/test_dependency_isolation.py` fails if that changes, and an allowlist entry
that is stale, unearned or outside `adapters` fails on its own.

`tests/contracts/support.py` builds on that same runtime registry rather than restating it, so
the validation the tests exercise is the code the service runs.

An invalid fixture proves one token is rejected; it does not pin the set a closed `enum`
declares. Measured on this tree: a third `scan_mode`, a fifth stage `status` and a fourth member
of the run state's terminal condition each left the whole suite green.
`tests/test_closed_vocabularies.py` closes that — it states every closed vocabulary in the
registry once and in full, derives the ones the Domain owns from the Domain, and fails when the
registry declares a closed vocabulary nobody pinned.

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
entry that is stale, unearned, outside a layer or blanket fails on its own. The mapping reads:

| module | authorised by |
| --- | --- |
| `domain/run_state.py` | PXK-60 |
| `domain/observations.py` | PXK-67 |
| `domain/findings.py` | PXK-20 |
| `ports/page_fetch.py`, `ports/html_observation.py` | PXK-67 |
| `application/analyze_homepage.py` | PXK-67 |
| `application/derive_findings.py` | PXK-20 |
| `adapters/contracts/registry.py` | PXK-67 |
| `adapters/web/*` | PXK-67 |
| `adapters/inbound/*`, `adapters/composition.py` | PXK-67 |
| `config/contract_root.py`, `config/fetch_limits.py` | PXK-67 |

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
