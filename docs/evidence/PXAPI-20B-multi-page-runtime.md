# PXAPI-20.B — Multi-Page Runtime & Real-Boundary

**Slice:** `PXAPI-20.B`, the second of the two sequential PR candidates of Jira `PXAPI-20`
(`D-20-K`). **This document does not declare `IC`, `R2G`, `R4M` or `PXAPI-20` Done** — those are
Orchestrator / Product Owner authority (`D-20-M`).

**Exact base:** `e4066161f5d31bb10fccb9d36baac4197e61fc02` (PXAPI-20.A merged).
**Branch:** `agent/pxapi20b-20260927-001`.
**Candidate SHA:** `<GOVERNOR POST-PUSH EXACT-SHA READBACK>` — deliberately not embedded; a commit
cannot truthfully contain its own SHA.

**Authority:** Jira `PXAPI-20` comments `16258`, `16259` (`D-20-A` … `D-20-P`), `16325`, `16656`;
Confluence `54362115` v1, `55181314` v1, `40239107` v2, `39846055` v4.

## 1. What this candidate builds

`Target → SiteInventory → SamplingManifest → admission → PageFetchPort (SafePageFetcher) →
PageAcquisitionRecord(STATIC_HTTP) → MeasurementRecords → WebsiteEvidence`.

| Module | Change |
| --- | --- |
| `src/pxapi/application/acquire_selected_pages.py` | **new** — the orchestrator |
| `src/pxapi/domain/page_acquisition.py` | admission gate added (`ADMISSION_RULES`, `admitted_page_refs`, `SelectionNotAdmissible`); 20.A content unchanged |
| `src/pxapi/application/observe_static_page.py` | `D-20-F` reading constraint for non-2xx |
| `src/pxapi/adapters/composition.py` | `build_site_acquisition(budgets, …)` — `budgets` required |
| `src/pxapi/adapters/inbound/acquire_cli.py` | **new** — required `--max-selected-pages N`, optional `--output-dir` |
| tests | `tests/application/test_acquire_selected_pages.py`, `tests/adapters/test_acquire_cli.py`, `tests/smoke/test_real_boundary_acquisition_smoke.py`, additions to `tests/application/test_observe_static_page.py`, `tests/test_package_scaffold.py` (+2 `PXAPI-20.B` entries) |

Protected and unchanged: `analyze_homepage.py`, `derive_findings.py`, `discover_site.py`,
`adapters/web/**`, `ports/**`, `config/**`, `contracts/v1/**`, `pyproject.toml`, `uv.lock`,
`.github/`, `oracle/`. No contract, dependency or workflow changed.

## 2. Decisions realised, and how

| Decision | Realisation |
| --- | --- |
| `D-20-A` explicit bound, no secondary truncation | CLI `--max-selected-pages` is `required=True`, validated (ASCII whole number ≥ 1), and becomes `SelectionBudgets(max_selected_pages=N)` on the manifest. The orchestrator iterates **every** admitted selection; there is no other bound. `build_site_acquisition` has no default for `budgets`, and the existing `build_site_discovery` still declares none. |
| `D-20-B` linkage, admission before fetch | `admitted_page_refs` refuses, before any fetch: wrong run, manifest not naming/pinning its inventory, inventory or manifest digest that does not reproduce, empty selection, duplicate Page Ref/rank, unknown or ineligible Page Ref. Records carry `measurement_refs`; no carrier contract was versioned. |
| `D-20-C` static producer only | Every record: `STATIC_HTTP`, `STATIC_HTTP_PAGE_FETCH`, `1.0.0`. |
| `D-20-D` neutral containment; our defects visible | **Site / per-page outcomes** — every `PageFetchFailure` kind (timeout, DNS, blocked/private/rebinding target, connection, protocol, invalid redirect, redirect limit), 4xx/5xx, truncated or undecodable bodies, unsupported media types and parser failure — are contained on their own page and the run succeeds. **PXAPI runtime / port-contract defects** — a fetch port that raises or returns anything other than `PageFetchOutcome \| PageFetchFailure`, an observation that raises, or a producer-invariant violation — fail the run as `PAGE_ACQUISITION_NOT_EMITTABLE` and withhold every page acquisition, measurement and evidence document, siblings included. Failed admission fails it as `SAMPLING_MANIFEST_NOT_ADMISSIBLE`. This producer never emits the `RUNTIME_ERROR` acquisition outcome. |
| `D-20-F` non-2xx | Status, final URL and headers measured; the body is **not parsed**; document facts and the meta-robots channel are `NOT_ASSESSED / UNSUPPORTED`. |
| `D-20-G` run timing | `entered_at` reproduced from the discovery run state unchanged. |
| `D-20-H` | `raw_artifact_ref` never emitted; `body_digest` over decoded bytes whenever `body_decoded`. |
| `D-20-J` | The seed goes through the same observer as every page; no finding is emitted anywhere. |
| `D-20-O` | No `SafePageFetcher` unit case cloned; integration tests only prove the boundary sits in front of each page. |

**One declared choice.** A redirect ending at a URL the Domain cannot canonicalise (raw
backslash, malformed escape) has no `final_url_key`, which the contract requires on a received
response. It is recorded as `INVALID_REDIRECT` — a redirect this service could not carry — rather
than inventing an identity or letting a site fail the run.

## 3. Test evidence (what the new tests prove)

- exactly one attempt and one record per selection, in rank order; stage `PAGE_ACQUISITION`
- budget 2 over 4 eligible pages → `selection_complete: false`, cause `SELECTION_BUDGET_EXHAUSTED`,
  exactly 2 fetches (no secondary truncation, no over-fetch)
- linkage: every measurement owned by exactly one record; every evidence resolves to one page
- mixed 200 / 404 / `TIMEOUT` / `DNS_FAILURE` in one run → run `SUCCEEDED`, siblings intact
- 404, 410, 500, 503: error-document title never appears in output; parser never called
- every `FetchFailureKind`, truncated body, undecodable body, unsupported media type, parser
  failure, unkeyable redirect target — each contained on its page
- port-contract defects: a fetcher that raises, or returns text or a dict, fails the run with
  `PAGE_ACQUISITION_NOT_EMITTABLE` and emits no page document; a canary replacing the breach by
  an expected `CONNECTION_FAILURE` keeps the run `SUCCEEDED` with siblings intact
- replay: one frozen input serialises identically twice; a canary proves the comparison bites
- admission: eight tampering cases, each fails before any fetch and names its rule; every
  `ADMISSION_RULES` entry has a counterexample
- our defects: duplicate identities (invariant failure) and a raising observer both fail the run
  with all page documents withheld
- production wiring: `SafePageFetcher` with the shipped `PublicTargetPolicy` class; with only its
  DNS answer faked, private, link-local, partial-rebinding answers → `BLOCKED_TARGET` and a
  resolver failure → `DNS_FAILURE` on every selected page, no socket opened
- loopback integration through the real fetcher: `TOO_MANY_REDIRECTS`, `INVALID_REDIRECT`,
  truncation, 404, undecodable `br` body
- CLI: missing flag and seven invalid values exit 2; artifacts written, read back, re-validated;
  a record order altered on disk is caught by the read-back

## 4. Gate results

| Gate | Result |
| --- | --- |
| `uv run ruff check .` / `ruff format --check .` | `<NOT RUN IN THE AUTHORING SESSION — runner/Governor readback>` |
| `uv run pytest` | `<NOT RUN IN THE AUTHORING SESSION — runner/Governor readback>` |

The authoring session had no shell tool, so it could not execute Ruff, pytest or the CLI. These
fields are left for the runner's locked-runtime verification rather than filled with invented
numbers.

## 5. Real-boundary run

| Field | Value |
| --- | --- |
| target | `https://www.rfc-editor.org/` (PXAPI-19 authorised origin) |
| invocation | `uv run --locked python -m pxapi.adapters.inbound.acquire_cli https://www.rfc-editor.org/ --max-selected-pages 3 --output-dir docs/evidence/PXAPI-20B-real-boundary` |
| equivalent opt-in smoke | `PXAPI_REAL_BOUNDARY_ACQUISITION_URL=https://www.rfc-editor.org/ PXAPI_REAL_BOUNDARY_OUTPUT_DIR=docs/evidence/PXAPI-20B-real-boundary uv run --locked pytest tests/smoke/test_real_boundary_acquisition_smoke.py` |
| interpreter | `<NOT EXECUTED — record sys.version of the run>` |
| run id / state | `<NOT EXECUTED>` |
| inventory id / output digest | `<NOT EXECUTED>` |
| manifest id / input / output digest / `selection_complete` / `incompleteness` | `<NOT EXECUTED>` |
| page-acquisition / measurement / evidence set digests | `<NOT EXECUTED — receipt.json document_digests>` |

Per-page table (to be filled from `receipt.json` → `pages`):

| Rank | Page Ref | Outcome | HTTP | Measurement refs | Evidence refs | Neutral / withheld reason |
| --- | --- | --- | --- | --- | --- | --- |
| `<NOT EXECUTED>` | | | | | | |

**The real-boundary run was not executed in the authoring session** (no shell tool). No artifact
under `docs/evidence/PXAPI-20B-real-boundary/` is claimed, and no figure above is invented. The
invocation is exact and `--output-dir` produces every artifact plus `receipt.json`, whose
`pages` rows are this table's columns.

### 5.1 Proof harness repair (`run-pxapi20b-proof-harness-repair-20260927-001`)

**Base:** `926822759e77233594e4f55ef23f1a270bd8280c`. The declared real-boundary execution is run
by `tools/pxapi20b_real_boundary_proof.py` from the Agent-team control interpreter
(`/Users/benjaminpoersch/.agt-runner/venv/bin/python`, Python 3.11); the project runtime stays
separate and uv-locked. This repair changes only the harness, its tests and this record:

- **Formatter.** Exact-head GitHub Actions run `36319802878` was red on Python 3.13 and 3.14 only
  because `ruff format --check` would reformat the harness. The harness is brought to the
  repository formatter's output; the artifact-bundle implementation is not touched.
- **uv discovery.** Under the proof sandbox `PATH` holds only the control interpreter's directory
  and system directories, and `HOME` may be scratch, so the accepted uv at
  `/Users/benjaminpoersch/.local/bin/uv` was not found. Lookup order is now: `PATH`; beside the
  control interpreter as given and as resolved; then `<home>/.local/bin/uv`, where `<home>` is
  read off the interpreter path itself when it lies under `<home>/.agt-runner/` — never off
  `HOME`. No further system locations are added: the sandbox `PATH` already carries the system
  directories. Only an existing, executable regular file is accepted, a `PATH` hit included.
  Nothing is downloaded, no shell or credential is used, `runner.env` is untouched, and the
  exact uv path and `uv --version` are recorded in `proof-receipt.json` as before.
- **Tests.** `tests/tools/test_pxapi20b_real_boundary_proof.py` (offline, harness imported by
  file path): `PATH` first; `/Users/benjaminpoersch/.local/bin/uv` derived from the control
  interpreter path with `HOME` set to scratch and home lookup forbidden; absence and rejection of
  non-executable candidates; the Python 3.14 / `requires-python` predicate; the exact CLI argv
  with `https://www.rfc-editor.org/` and `--max-selected-pages 3`; bundle checks rejecting
  one-page, missing, extra, mixed-run and broken-linkage bundles and accepting a coherent
  two-page one; a scripted host proving the receipt keeps the exact SHA, both runtimes, the lock
  digest before and after, the page table and the evidence ceiling.

| Gate | Result |
| --- | --- |
| `uv run ruff check .` / `ruff format --check .` | `<NOT RUN IN THE AUTHORING SESSION — runner/Governor readback>` |
| `uv run pytest` | `<NOT RUN IN THE AUTHORING SESSION — runner/Governor readback>` |

The authoring session again had no shell tool: formatting was applied by hand to the formatter's
rules, not by running it. **The declared real-boundary execution is still pending**: the coding
agent neither executed nor claims any network proof, no `proof-receipt.json` exists, and every
`<NOT EXECUTED>` field above stands. No proof descriptor is added by this repair.

### 5.2 Oracle interpreter and canonical cardinality repair (`run-pxapi20b-oracle-cardinality-repair-20260927-002`)

**Base:** `cf8964ee8c985208e954e62f378b770b481478fc`. This repair changes only the harness, the
acquisition command line's canonical-output boundary, their tests and this record.

- **Proof interpreter.** The harness no longer hard-requires Python 3.14. It reads the exact
  `requires-python` of the checkout's `pyproject.toml` (`>=3.13,<3.15`), then asks
  `uv python find` — downloads and uv-managed Pythons off — for an already installed system
  Python 3.14 and, if that is missing or rejected, 3.13. A candidate is accepted only when it is
  not under `uv python dir`, its probe reports the requested minor version, and that release
  satisfies `requires-python`; none left fails the bootstrap before any sync. `HOME` is not used,
  nothing is downloaded, and the operator is never asked to install or select a Python.
  `UV_PYTHON_DOWNLOADS=never`, `UV_PYTHON_PREFERENCE=only-system`, `uv sync --locked`, the
  disposable `TMPDIR` environment and the `uv.lock` byte check are unchanged. The disposable
  project runtime is validated against `requires-python` and the selected interpreter's minor
  version, not an exact 3.14 tuple. `proof-receipt.json` records `requires_python`, every
  candidate's outcome (`python_candidates`) and the chosen interpreter path and version
  (`selected_python`). Exact SHA, target, `--max-selected-pages 3`, bundle, linkage, artifact and
  evidence-ceiling checks, and the proof's own container check (`_shaped`), are unchanged.
- **Canonical container cardinality.** `acquire_cli.CONTAINER_SHAPES` names the top-level
  container of every `PRODUCED_DOCUMENTS` member: `analysis_run_request`, `analysis_run_state`,
  `site_inventory` and `sampling_manifest` are exactly one JSON object; `stage_executions`,
  `page_acquisitions`, `measurements` and `website_evidence` are exactly one JSON array of
  objects. A member in any other shape — a singleton wrapped in a list, a plural member given as
  one object or a scalar, an array holding a non-object — is reported as a deterministic
  `<file>: container is not …` problem and its items are not validated. Before publication this
  makes the run `CANONICAL_OUTPUT_INVALID` (exit 3), so no receipt is derived and no artifact is
  written. On read-back the same rule runs first, and a misshapen member reaches none of the
  contract, binding, producer-invariant or receipt helpers. No JSON Schema and no valid document
  changed.
- **Tests.** `tests/tools/test_pxapi20b_real_boundary_proof.py`: 3.14 preferred over an installed
  3.13; automatic 3.13 fallback with home lookup forbidden; incompatible 3.14 (wrong release,
  outside `requires-python`) falling back; a uv-managed candidate rejected; missing, wrong and
  out-of-range candidates failing the bootstrap before any sync; an unsupported `requires-python`;
  locked, system-only, isolated uv calls; a rewritten lock; project-runtime validation; the
  proof's list members mirroring `CONTAINER_SHAPES`. `tests/adapters/test_acquire_cli.py`:
  singleton-as-list, plural-as-dict, plural with a non-object and plural-as-scalar withheld as
  `CANONICAL_OUTPUT_INVALID` with no artifact and no receipt; the same shapes read back from disk
  reported without raising and kept from the producer invariants; a neutral mixed
  200 / 404 / `TIMEOUT` run still publishing the same valid bundle.

| Gate | Result |
| --- | --- |
| `uv run ruff check .` / `ruff format --check .` | `<NOT RUN IN THE AUTHORING SESSION — runner/Governor readback>` |
| `uv run pytest` | `<NOT RUN IN THE AUTHORING SESSION — runner/Governor readback>` |

The authoring session again had no shell tool, so neither the tests, Ruff nor the proof could be
executed here. **The declared real-boundary execution is still pending**: no `proof-receipt.json`
exists, every `<NOT EXECUTED>` field above stands, and no proof descriptor is added.

## 6. Evidence ceiling

Even once executed, this proves one bounded, explicitly budgeted selection of one controlled
public origin acquired safely into valid, linked, page-scoped canonical documents. It does **not**
prove complete site coverage (the manifest's `selection_complete` is the only coverage
statement), browser rendering, scoring validity, PDF readiness, production scale, or customer
value.
