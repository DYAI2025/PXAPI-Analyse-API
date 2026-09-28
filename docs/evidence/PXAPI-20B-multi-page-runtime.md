# PXAPI-20.B — Multi-Page Runtime & Real-Boundary

**Slice:** `PXAPI-20.B`, the second of the two sequential PR candidates of Jira `PXAPI-20`
(`D-20-K`). **This document does not declare `IC`, `R2G`, `R4M` or `PXAPI-20` Done** — those are
Orchestrator / Product Owner authority (`D-20-M`).

**Exact base:** `e4066161f5d31bb10fccb9d36baac4197e61fc02` (PXAPI-20.A merged).
**Branch:** `agent/pxapi20b-20260927-001` (first authoring branch; the later repair and
reconcile runs named in §5 each worked on their own `agent/pxapi20b-…` branch).
**Proven candidate SHA:** `28e29a0aff59cd41a4bc1cb96030075082d9f4ad` — the descriptor-only
activation head (`run-pxapi20b-proof-activate-20260927-004`, whose one intentional file change was
`.agent-proofs.json`). Every executed figure in §4 and §5 is bound to **that** SHA. The commit that
carries this reconciled document is a documentation-only head on top of `28e29a0`; it cannot
truthfully contain its own SHA, so the Delivery Runner re-runs the mandatory real-boundary proof at
the exact documentation result SHA and publishes fresh artifacts externally. Nothing in this file
claims a merge, a PR, `main` CI on a merge SHA, or `PXAPI-20` Done.

**Review checkpoint and repair (2026-09-28).** Jira `PXAPI-20` comment `16689` is the accepted
independent exact-head review of `0bbd7878d3478ab0ff91787f5ea2e2008d32ccc1`, the
evidence-reconcile head on top of `28e29a0`: `IC` GREEN, `R2G` NOT_GREEN, `R4M` NOT_GREEN, because
of `F-20B-R4M-001` and `F-20B-R4M-002` (§5.5). The exact-base GitHub Actions `python-compat` run
`36350997318` succeeded on Python 3.13.15 and 3.14.7 with Ruff green and `3307 passed, 2 skipped`.
§5.5 records the proof-integrity repair authored on
`agent/pxapi20b-proof-integrity-repair-20260928-001`: it changes the proof oracle, its focused
test, the proof descriptor's integrity roots and the two documents, and nothing of the verified
runtime. The proof at the repair's result SHA was not executed by this document's author; the
Delivery Runner runs it and, because the oracle changed, its verdict is reviewed independently.
Every figure in §4 and §5 stays bound to `28e29a0`; the two findings concern what the proof
*checked*, not what the runtime produced.

**Authority:** Jira `PXAPI-20` comments `16258`, `16259` (`D-20-A` … `D-20-P`), `16325`, `16656`,
`16689`; Confluence `54362115` v1, `55181314` v1, `40239107` current, `39846055` v4.

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

Measured by the Delivery Runner on the exact head `28e29a0aff59cd41a4bc1cb96030075082d9f4ad`
(`run-pxapi20b-proof-activate-20260927-004`):

| Gate | Result at `28e29a0` |
| --- | --- |
| `uv run ruff check .` / `ruff format --check .` | green |
| `uv run pytest` | `3307 passed, 2 skipped` |
| exact-head GitHub Actions `python-compat` | run `36349224176`, `success` |

**History, preserved.** The first authoring session, and the two repair authoring sessions of
§5.1 and §5.2, had no shell tool and recorded here that the gates were not run in the authoring
session, rather than invented numbers. The exact-head GitHub Actions run `36319802878` on an earlier head was
**red** on Python 3.13 and 3.14 because `ruff format --check` would have reformatted the proof
harness (§5.1). Those earlier heads are not the head the numbers above describe; the table applies
to `28e29a0` only.

## 5. Real-boundary run

**Executed and verified** as the mandatory project-native proof `pxapi20b-real-boundary`
(`.agent-proofs.json`, entrypoint `tools/pxapi20b_real_boundary_proof.py`) in
`run-pxapi20b-proof-activate-20260927-004`, status **`VERIFIED`**, reason
`VERIFIED_ORACLE_CHANGED/INDEPENDENT_REVIEW` — the descriptor `.agent-proofs.json` was the run's
intentional one-file oracle change, so the verdict rests on the independent artifact review rather
than on an unchanged oracle. Exact proof / candidate SHA
`28e29a0aff59cd41a4bc1cb96030075082d9f4ad`.

| Field | Observed at `28e29a0` |
| --- | --- |
| target | `https://www.rfc-editor.org/` (PXAPI-19 authorised origin) |
| invocation | the production module `pxapi.adapters.inbound.acquire_cli`, run by the harness as the disposable project-runtime Python, with explicit `--max-selected-pages 3` and a fresh canonical output directory (`.proof-output/pxapi20b-real-boundary/canonical/`, untracked) |
| equivalent opt-in smoke | `PXAPI_REAL_BOUNDARY_ACQUISITION_URL=https://www.rfc-editor.org/ PXAPI_REAL_BOUNDARY_OUTPUT_DIR=<dir> uv run --locked pytest tests/smoke/test_real_boundary_acquisition_smoke.py` — the smoke was **not** the proof driver; the harness above was |
| selected interpreter | installed system `/opt/homebrew/opt/python@3.14/bin/python3.14`, Python `3.14.6` (`D-20-L`: measured-fast 3.14.x); disposable project runtime also `3.14.6`; `requires-python >=3.13,<3.15` |
| `uv.lock` before / after | `sha256:c2479e8f90207cef2deac99b438f97f1865d80d1363dd4bef8c2665bff4c6a48` both times — unchanged |
| run id / state | `px-8674bf01befc4c849bd77de39621c3c6` / `SUCCEEDED` |
| inventory id / candidates / output digest | `px-fd7bfcac8620486e9b1bd4da242ede8e` / 506 / `sha256:530a0d1ba432e8d16a07dfaf50d3c1333395125488a738ebb3256b67b5ac52a8` |
| manifest id / inventory ref | `px-4b401785ea504ca58238d5b46c1ec58d` / `px-fd7bfcac8620486e9b1bd4da242ede8e` |
| manifest input / output digest | `sha256:d4fb624edb6b9a9cf1c77426b9addb9987ce606e8f2551812de0376e39852dbe` / `sha256:c1c60a53ddbffcf0f675184a75fdd4064e5517002154d7ce2c1ca3f62a5f82ac` |
| `selected_count` / `selection_complete` / `incompleteness` | 3 / `false` / `SELECTION_BUDGET_EXHAUSTED`, 503 candidates excluded by budget |
| page acquisitions | count 3, digest `sha256:7da87ce469c15c9e196c57cd6878fbff8e7bbb55deb334ab8134068641348e7d` |
| measurements | count 39, digest `sha256:2906b46825bea203c89db3438f1f102940438f4657011eacdceeb5f92289107b` |
| website evidence | count 39, digest `sha256:65fd06ca37eca95df604105216b9ea89c854427a5e58a581dff35d588c2c02a2` |
| producer | `STATIC_HTTP_PAGE_FETCH` `1.0.0`, `observation_mode = STATIC_HTTP` on every record |

Per-page table (from `receipt.json` → `pages`):

| Rank | Page Ref | Acquisition | Outcome | HTTP | Measurement refs | Evidence refs | Neutral / withheld reason | Body digest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `https://www.rfc-editor.org/` | `px-962d9cd34e5a4254b7c670e21c20344b` | `RESPONSE_RECEIVED` | 200 | 13 | 13 | none | `sha256:aa92be14fdf91e745194166ead157cbb0c785487c90e6662b2491bf99321f575` |
| 2 | `https://www.rfc-editor.org/about/contact/` | `px-3a947b34a667465e9462634910bd5549` | `RESPONSE_RECEIVED` | 200 | 13 | 13 | none | `sha256:540fdac418ebce976c7d9abf2a05a7055e5963961e48d5825d5bf5c4a7470838` |
| 3 | `https://www.rfc-editor.org/about/rfc-editor/` | `px-6a1c2e6044c242a9acc1d67a4474c8af` | `RESPONSE_RECEIVED` | 200 | 13 | 13 | none | `sha256:6908f405d2525eb5942a0d3f26a976002f7f00d6045adf3421d413102564daba` |

Linkage as read back by the harness and re-checked by the independent artifact review: every
selected URL is present in the bound inventory; selections and acquisitions are unique and in rank
order; every measurement has exactly one page-acquisition owner and every evidence record resolves
to that same page; the producer is `STATIC_HTTP_PAGE_FETCH 1.0.0` / `STATIC_HTTP` only. The
independent review recomputed all ten published SHA-256 values, the canonical counts and digests and
the linkage, with no findings.

No artifact under `docs/evidence/PXAPI-20B-real-boundary/` is committed, and the proof output
directory is untracked: the artifacts of record are the Agent-team publications listed in §5.4 by
SHA-256 filename.

**History, preserved.** The first authoring session had no shell tool and did not execute this
run; every field above was then marked as not executed, no artifact was claimed and no figure was
invented. §5.1 and §5.2 record the two repairs written in that same state. §5.3 records the
repair chain that followed before the proof first succeeded.

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
| `uv run ruff check .` / `ruff format --check .` | not run in that authoring session (no shell tool); superseded by the exact-head measurement at `28e29a0` in §4 |
| `uv run pytest` | not run in that authoring session (no shell tool); superseded by the exact-head measurement at `28e29a0` in §4 |

Written at the time, preserved as history: the authoring session again had no shell tool, so
formatting was applied by hand to the formatter's rules, not by running it; the declared
real-boundary execution was still pending, the coding agent neither executed nor claimed any
network proof, no `proof-receipt.json` existed, and no proof descriptor was added by this repair.
That pending state ended with the run recorded in §5 and §5.4.

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
| `uv run ruff check .` / `ruff format --check .` | not run in that authoring session (no shell tool); superseded by the exact-head measurement at `28e29a0` in §4 |
| `uv run pytest` | not run in that authoring session (no shell tool); superseded by the exact-head measurement at `28e29a0` in §4 |

Written at the time, preserved as history: the authoring session again had no shell tool, so
neither the tests, Ruff nor the proof could be executed there; the declared real-boundary
execution was still pending, no `proof-receipt.json` existed and no proof descriptor was added.
The canonical-container-cardinality repair described above is the change closed at
`c1bf4cd57d1045bf73c93cfb64b7a4a594dcbb42` (`C-PXAPI-022` in the contradiction ledger).

### 5.3 Proof interpreter / configuration / `PATH` discovery chain, and descriptor activation

After §5.2 the proof still did not complete on the Agent-team host: the harness could not reliably
select an installed system Python under the proof sandbox. The chain of repairs, each a separate
Delivery Runner run and commit on the candidate, was:

| Commit | Run | What it changed |
| --- | --- | --- |
| `64d8f22` | `run-pxapi20b-system-python-discovery-repair-20260927-001` | system-Python discovery for the proof interpreter |
| `f32d023` | same run, correction 1 | correction to that discovery |
| `2946709` | `run-pxapi20b-uv-env-isolation-repair-20260927-001` | isolation of the harness's `uv` calls from host `UV_*` variables and from project or user uv configuration |
| `479bc1d` (`479bc1db4902bc914dfe32e77cd772935b48f46d`) | `run-pxapi20b-proof-path-discovery-repair-20260927-001` | `PATH` discovery: each `uv python find` sees the inherited `PATH` followed by the existing well-known system and package-manager interpreter directories for the requested minor, so a sandbox `PATH` that omits e.g. `/opt/homebrew/opt/python@3.14/bin` still resolves the installed interpreter — which is then probed and checked like any other candidate |
| `28e29a0` (`28e29a0aff59cd41a4bc1cb96030075082d9f4ad`) | `run-pxapi20b-proof-activate-20260927-004` | **descriptor-only activation**: `.agent-proofs.json` registers `pxapi20b-real-boundary` as a mandatory proof with its ten artifacts and integrity roots `src/pxapi`, `contracts/v1`, `pyproject.toml`, `uv.lock`; no other file changed |

The chain is closed at `479bc1d` and operationally proven by `28e29a0`, whose proof selected
`/opt/homebrew/opt/python@3.14/bin/python3.14` (`3.14.6`) with downloads, uv-managed Pythons,
`.python-version` and uv configuration all excluded (`C-PXAPI-023`). The end state is the harness
docstring of `tools/pxapi20b_real_boundary_proof.py` at `28e29a0`. Each repair was an
implementation or oracle repair under `D-20-L`, `D-20-M` and `D-20-O`; **no product or architecture
decision was made**, and the decision ledger is unchanged by this chain. The failed states before
`28e29a0` are not laundered: no run before `run-pxapi20b-proof-activate-20260927-004` produced a
verified proof, and the runs named above exist because the earlier heads did not.

### 5.4 Published artifacts of `run-pxapi20b-proof-activate-20260927-004`

Agent-team artifact publications, named by SHA-256 of their content, for exact SHA `28e29a0`:

| Artifact | SHA-256 |
| --- | --- |
| `proof-receipt.json` | `0048f451c2054837bef55e3f5cdc1aa6156994df151a9790c65f1c9e8f146dfa` |
| `canonical/analysis-run-request.json` | `b0971da579ceca96fbfa7690d589d82b9709f6300ba3acda317745ab86180b14` |
| `canonical/analysis-run-state.json` | `c006ed5b315711412919b52e14a70fd42b4521dba2c2c5855698ae320c4663b6` |
| `canonical/stage-execution-records.json` | `6125a6c4c4dda076b714495df48ec2816211f4f50511aa03c3484b37e25d96a7` |
| `canonical/site-inventory.json` | `fdd5b2b758c3323ee0f21d849ba36c46268a75a63804d68a6a445cadfa0627a4` |
| `canonical/sampling-manifest.json` | `41e502d53344c833831fc84087f0effcf163972a47932b649d841186588cc473` |
| `canonical/page-acquisition-records.json` | `7742efe0b82ad4493708db5ea66410578aad36c41b9ad2cd356f2f174daac5b9` |
| `canonical/measurement-records.json` | `cd18ece23e3e8879a4f94e7e686c07e5c9516c381b4e786d27fd1ad064a4c540` |
| `canonical/website-evidence.json` | `ac18c493ceacc3c2632da8e750025b232c7fe3aa48dc35c7230833d3fcd9d76d` |
| `canonical/receipt.json` | `c8f081a5ee210937805a79308769c0f1e317e8ad26adc4d5831cff99ff606694` |

These are the artifacts of record; this repository commits none of them. Because the head that
contains this document is later than `28e29a0`, the Delivery Runner re-executes the same mandatory
proof at that documentation result SHA and publishes a fresh set, which will carry new run,
inventory, manifest and acquisition ids and new artifact digests. That later set is evidence about
its own SHA and is recorded by its own run, not by editing this table.

### 5.5 Proof-integrity repair (`run-pxapi20b-proof-integrity-repair-20260928-001`)

**Base:** `0bbd7878d3478ab0ff91787f5ea2e2008d32ccc1` on
`agent/pxapi20b-evidence-reconcile-20260927-001`. **Branch:**
`agent/pxapi20b-proof-integrity-repair-20260928-001`. Current `main`
`e4066161f5d31bb10fccb9d36baac4197e61fc02`; no 20.B PR exists. Authority for the findings: Jira
`PXAPI-20` comment `16689`. This is a bounded repair of the proof oracle, not a new implementation
and not a new ticket; the verified 20.B runtime is preserved byte for byte.

**Findings repaired.**

- `F-20B-R4M-001` — at the base, `tools/pxapi20b_real_boundary_proof.py` checked JSON, container
  shape and linkage, but validated no canonical document against its registered contract, applied
  no producer invariant, and copied `receipt.document_digests` into its own summary instead of
  recomputing anything. A bundle with a missing `schema_version`, invalid digest strings and a
  forged document count could return no problems and a `PASSED` receipt.
- `F-20B-R4M-002` — checkout cleanliness was `git status --porcelain --untracked-files=no`, and the
  command line ran with the checkout root as its working directory, so an untracked top-level
  `pxapi` package would have been imported in place of the tracked `src/pxapi` while the proof
  recorded the tracked SHA.

**What changed** — proof oracle only. `src/pxapi/**` (acquisition runtime, application,
composition and `acquire_cli.py` included), `contracts/**`, every test outside
`tests/tools/test_pxapi20b_real_boundary_proof.py`, `AnalyzeHomepage`, `SafePageFetcher`,
`adapters/web/**`, `pyproject.toml`, `uv.lock`, `.github/**`, `oracle/**`, `README.md`,
`docs/context/project-state.md` and `docs/context/decision-ledger.md` are byte-identical to the
base. No PR, merge, Jira transition or comment, or Confluence mutation was made.

| File | Change |
| --- | --- |
| `tools/pxapi20b_real_boundary_proof.py` | **Isolation.** After the tracked-cleanliness check, `git status --porcelain --untracked-files=all -- src contracts` must print nothing and no checkout-root entry named `pxapi` or `pxapi.<ext>` may exist, else stage `isolation` fails before `uv` runs. Every Python the harness starts — the interpreter probes, the production command line and the verifier — runs with `-I` (no `PYTHON*` variable, no user site, no script or working directory on `sys.path`) from an empty scratch working directory under `TMPDIR`, never from the checkout; `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, `SSL_CERT_DIR` and `PXAPI_CONTRACTS_DIR` are dropped from the command environment as well. **Verification.** A second consumer (`CONTRACT_VERIFIER`) runs as the locked project runtime after the command line: it reports the real `pxapi.__file__`, the runtime's contract root and its `isolated`/`safe_path` flags, validates every canonical document against its registered contract in the checkout's `contracts/v1`, and applies `pxapi.domain.page_acquisition.acquisition_violations` to the documents as read back. The observed origin must resolve to the tracked `src/pxapi` of the checkout or to a `pxapi` package inside the disposable environment, the contract root must be the checkout's, and the flags must be set, else stage `isolation` fails; any schema or producer-invariant violation fails stage `contract`. The verifier reads no receipt and reports malformed files as problems rather than raising. **Recomputation**, standard library only, in the control interpreter: the semantic SHA-256 digests and counts of the page-acquisition, measurement and WebsiteEvidence documents; `SiteInventory.output_digest`; `SamplingManifest.input_digest` and `output_digest` — projections and canonical JSON options restated from `pxapi.domain.acquisition_digests` and pinned by test; and every `receipt.json` member derivable from the canonical documents (`run_id`, `run_state`, `failure_code`, the inventory and manifest blocks including `selected_count` and `candidate_count`, `document_digests`, and every per-page row and its cardinality), compared for exact parity with recomputed digests in place of copied ones. `SiteInventory.input_digest` is shape-checked only: it is over discovery observations the published bundle does not carry (`INVENTORY_INPUT` is empty), and that ceiling is stated rather than filled. **Cardinality.** Selections must be objects with positive whole-number ranks, unique, dense `1..n`, at most the budget and candidates of the bound inventory; acquisitions must be exactly the selections in rank order with none missing, extra or duplicated and unique `acquisition_id`; measurement refs must be unique per record, resolve, be owned by exactly one record, and every measurement must be owned; each measurement must be observed at its record's `acquired_at`, sourced at the Page Ref when no response arrived and at no more than one response URL otherwise, and a page may measure one metric once; every evidence record must carry nonempty refs resolving to measurements of exactly one page, mirror its measurement's `source_url` and `observed_at`, and carry no polarity; `measurements_withheld_reason` if and only if there are no refs; no `raw_artifact_ref`. **Fail-closed.** `NaN`/`Infinity` are refused as the registry refuses them; a malformed bundle is a deterministic list of problems and a nonzero result; a harness defect still leaves a `FAILED` receipt. New receipt members `isolation`, `verification` and `recomputed_digests`; new failure stages `isolation`, `verification` and `contract`. |
| `tests/tools/test_pxapi20b_real_boundary_proof.py` | The schema-invalid placeholder fixture is replaced by the shipped runtime's own output over the frozen discovery report and a fake fetch port, published through `acquire_cli.expected_bundle` — asserted contract-valid and producer-valid before use, with a neutral 200 / 404 / `TIMEOUT` variant and a complete-selection variant. The harness's canonical JSON options, digest member classes, projections and re-derived receipt are pinned against `pxapi.domain.acquisition_digests` and `acquire_cli.page_receipt`. Negative cases, each passing only when the proof rejects: an untracked checkout-root `pxapi` package, `pxapi.py` or `pxapi.pyc`; untracked entries under `src` / `contracts`; a `pxapi` imported from outside the locked project; a runtime without isolation flags; missing `schema_version` in a singleton and in a plural document; malformed and wrong inventory `output_digest`; malformed inventory `input_digest`; wrong manifest `input_digest` and `output_digest`; duplicate, gapped and unknown selections; missing, duplicate and extra acquisitions; a record unbound from the manifest; a `raw_artifact_ref`; empty refs without a reason; missing, duplicated and orphan measurements; a measurement owned by two records, named twice by one record, or measuring a metric twice; a measurement outside its page's instant or response context; unlinked, empty, duplicated, cross-page, out-of-context and polarised evidence; a document of another run; a failed run state; forged receipt document count, semantic digest, `selected_count`, manifest and inventory digests, `candidate_count` and `run_state`; forged receipt rows (outcome, status, measurement refs, evidence refs, reasons, withheld reason, rank, body digest); wrong row count, a missing and an underivable receipt member; stdout / file mismatch; six malformed-bundle shapes reported deterministically without raising. The real verifier is executed by the test interpreter under `-I` on the positive fixture (origin bound to `src/pxapi`, every file counted), on a document without `schema_version`, on an invalid digest and an unsupported version, on a duplicated record (producer rules named) and on a misshapen and an unreadable file. The scripted-host proof run covers the whole pipeline — every Python call isolated and started from the scratch directory, the command environment cleaned, each failure stage, contract and linkage problems recorded together — and one run over the repository's own checkout with the verifier actually executed. Every bootstrap, interpreter-selection, lock, uv-isolation and well-known-directory check of §5.1–§5.3 is retained. |
| `.agent-proofs.json` | Additive only: `tools/pxapi20b_real_boundary_proof.py` and `tests/tools/test_pxapi20b_real_boundary_proof.py` join `integrity_roots`. Every existing root, artifact, `mandatory`, `output_dir` and `timeout_seconds` is unchanged. |
| `docs/evidence/PXAPI-20B-multi-page-runtime.md`, `docs/context/contradiction-ledger.md` | This section, the header checkpoint note, the §6 note and `C-PXAPI-024`. |

**Authorship state, written at the time.** The authoring session had no shell tool: neither the
focused tests, the full suite, Ruff nor the proof were executed there, and no figure below is
invented. Formatting was written to the repository formatter's rules by hand, not by running it.

| Gate | Result |
| --- | --- |
| `uv run pytest tests/tools/test_pxapi20b_real_boundary_proof.py` | not run in this authoring session (no shell tool); to be measured by the Delivery Runner on the exact result SHA |
| `uv run pytest` from a fresh runner-owned locked environment | not run in this authoring session; the base's `2 skipped` and its warning count are expected to be preserved, and any deviation is a finding |
| `uv run ruff check .` / `uv run ruff format --check .` | not run in this authoring session |
| mandatory proof `pxapi20b-real-boundary` at the result SHA | not run in this authoring session. The Delivery Runner runs it under runner policy against `https://www.rfc-editor.org/` through the production command line with explicit `--max-selected-pages 3` on the measured-fast supported interpreter selection (`D-20-L`); because the oracle changed, its verdict requires independent review (`VERIFIED_ORACLE_CHANGED/INDEPENDENT_REVIEW`) and is not self-authorised by this repair |

**Evidence ceiling of this repair.** It makes the proof a second, independent consumer of the
bundle and binds the runtime it observed to the tracked installation. It does not change what the
runtime produces, does not widen the public proof beyond one bounded selection of one origin, adds
no product or architecture decision, and declares no gate. `resolution.next_action`: the Delivery
Runner executes the focused tests, the full suite, Ruff and the mandatory proof on the exact result
SHA and publishes the artifacts; then independent `R2G` / `R4M` at that head (`D-20-M`).

**Chronological note (2026-09-28, `run-pxapi20b-proof-integrity-verify-20260928-001`).**

1. The repair above was reviewed at exact head `9a582f3ea2354c52e51a10573c8ae0a5f8b00e4c` (`9a582f3e`),
   the second correction commit of `run-pxapi20b-proof-integrity-repair-20260928-001`. The
   authoring session's ceiling ("not run in this authoring session") was closed by later steps of
   that run, not by the author.
2. Correction sequences 2 and 3 of that run each executed, independently and at this unchanged
   head, fresh `uv`-locked full `pytest` and Ruff from a runner-owned environment. Latest evidence:
   `3399 passed, 2 skipped, 2 warnings`; `ruff check .` and `ruff format --check .` clean.
3. The independent exact-head review at `9a582f3e` found no Blocker, Critical, Important or Minor
   finding, and records `F-20B-R4M-001` and `F-20B-R4M-002` as closed in code: registered-contract
   and producer-invariant validation, independent digest, count, receipt and cardinality
   recomputation, and import-shadow prevention are present, each with negative tests.
4. The mandatory `pxapi20b-real-boundary` proof was nevertheless not executed by that run. Its
   immutable work-order snapshot omitted the machine oracle-scope declaration
   (`verification_scope_change`), so the dispatch control never authorised the proof, and the
   correction sequences could not change that frozen policy. This was a dispatch-control defect, not
   a repository defect; the repaired oracle at `9a582f3e` is unaffected.
5. `run-pxapi20b-proof-integrity-repair-20260928-001` was cancelled by the Governor after
   `GOAL_RECONCILED` (readback-confirmed `CANCELLED`, reason `CANCELLED_BY_GOVERNOR`) and its WIP
   slot released. The present run is its exact-base successor on `9a582f3e`; it exists only to
   execute the unchanged mandatory proof and changes nothing but this note.
6. No proof result, receipt, artifact reference or gate is claimed here. The Delivery Runner
   executes fresh full `pytest`, Ruff and the mandatory proof — through the production command line
   against `https://www.rfc-editor.org/` with explicit `--max-selected-pages 3` — at the exact
   result SHA of this note's commit, and publishes those artifacts externally after the commit.
   Because the oracle is unchanged from this run's base, a successful project-native proof at that
   SHA may serve as independent release evidence; `R2G` / `R4M` remain Orchestrator / Product Owner
   authority (`D-20-M`) and are not self-authorised by this note.

## 6. Evidence ceiling

Executed, this proves **one bounded point-in-time selection of one controlled public origin over
`STATIC_HTTP`**, acquired safely into valid, linked, page-scoped canonical documents at exact SHA
`28e29a0`. It does **not** prove complete site coverage — `selection_complete = false` with
`SELECTION_BUDGET_EXHAUSTED` is the only coverage statement, and 503 of 506 candidates were not
fetched — nor browser rendering, scoring validity, PDF readiness, production scale, customer value,
or that a future refetch of the same origin is deterministic. The boundary observed **three
successes**; the neutral mixed-failure behaviour (200 / 404 / `TIMEOUT` / `DNS_FAILURE` in one
run, §3) remains **regression evidence from tests** and is not claimed as observed in this receipt.
Independent Governor review recommends `IC` / `R2G` / `R4M` `GREEN` for `28e29a0`; that
recommendation, the gates themselves, PR creation, merge and `PXAPI-20` closeout are Orchestrator /
Product Owner authority (`D-20-M`) and none of them is declared by this document.

**Superseded, preserved (2026-09-28).** The recommendation above preceded the accepted exact-head
review of `0bbd787` in Jira `PXAPI-20` comment `16689`, which records `IC` GREEN and `R2G` /
`R4M` NOT_GREEN for the proof-oracle findings repaired in §5.5. The sentence is kept as written;
no gate is declared here, and the next evaluation is the independent one at the repair's result
SHA.
