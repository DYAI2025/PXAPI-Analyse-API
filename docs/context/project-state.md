# PXAPI Project State

**Snapshot date:** 2026-09-29 (PXAPI-25 reconcile; every older statement below is kept where it describes history)  
**Previous snapshot date (historical):** 2026-09-27 (evidence reconcile; the 2026-09-19 snapshot statements below are kept where they describe history)  
**Execution mode:** `PXAPI-25` — Operator Workbench & Multi-Page Run Validation v1, `In Arbeit` since 2026-09-28 23:35 +02:00, the only `WIP=1` theme. One PR candidate on branch `agent/pxapi25-operator-workbench` from exact base `ce4de1820d2516f9b3bf73b11ad9441dbad941ba`; not merged, ticket not Done (see *PXAPI-25 candidate*).  
**Previous execution mode (2026-09-27, historical):** `PXAPI-20` — Multi-Page Static Acquisition & Canonical Evidence Population v1. `WIP=1` is this implementation theme and it is the only one; the PXAPI-19 closeout theme is finished. PXAPI-20 is delivered as two sequential PR candidates under one Jira item, `20.A` then `20.B` (Jira `PXAPI-20` comment `16259`, `D-20-K`). `20.A — Static Page Evidence Foundation` is **merged** (`e4066161…`, PR #20). `20.B — Multi-Page Runtime & Real-Boundary` exists as a candidate at exact head `28e29a0aff59cd41a4bc1cb96030075082d9f4ad`: the multi-page runtime, the mandatory proof descriptor `.agent-proofs.json` and a **verified real-boundary proof** are on that candidate; its PR, merge and the `PXAPI-20` ticket closeout are **still pending**. Neither candidate's merge nor its green gates alone make `PXAPI-20` Done.  
**Repository:** `DYAI2025/PXAPI-Analyse-API`  
**19.A integrated implementation baseline:** `926c2415503f27084ab314629548b2e79ddce8a9`  
**19.B integrated implementation baseline (historical; no longer `main`):** `fe8d838023c8f9967151cad9aa1981e76dcf7d75`  
**PXAPI-19 closeout baseline and 20.A base (historical; no longer `main`):** `19a9a855d603384c216bbf9ab92e4e7cb0334bfb` — the merge of closeout PR #19, and `main` when the 2026-09-19 snapshot was written. It advances documentation only over the previous baseline `bfe06cc07ea0dfde31fedb8e7115940da24fb9fd`: `git diff --quiet bfe06cc 19a9a855 -- src tests contracts/v1 pyproject.toml uv.lock .github` exits **0**, and the six files that do differ are `contracts/README.md`, the three `docs/context/` files and the two PXAPI-19 closeout evidence artifacts. The runtime at `19a9a855` is therefore byte-for-byte the runtime PR #18 merged. `PXAPI-20.A` was implemented from this exact base.  
**Current implementation baseline (`main`):** `ce4de1820d2516f9b3bf73b11ad9441dbad941ba` — PXAPI-20.B merged (merge of PR #21); exact-SHA `python-compat` run `36405179068` `success` (read 2026-09-29); Jira `PXAPI-20` `Erledigt` (read live 2026-09-29). PXAPI-25 is implemented from this exact base.  
**Previous implementation baseline (2026-09-27, historical):** `e4066161f5d31bb10fccb9d36baac4197e61fc02` — the merge of PXAPI-20.A (PR #20). `PXAPI-20.B` is implemented from this exact base; its candidate head `28e29a0…` is **not** on `main`.

## Purpose

This file is a compact rehydration snapshot for delivery gates. It does not replace Confluence, Jira, GitHub, CI, or runtime authorities. Every session must live-read those authorities before material decisions.

## Domain authorities

- PXAPI Confluence: Product Intent, requirements, accepted architecture decisions and governance.
- Jira PXAPI / Board 436: backlog, priority, workflow status, sprint membership and ownership.
- GitHub `DYAI2025/PXAPI-Analyse-API` exact ref/SHA: code, repository contracts, tests and CI configuration.
- CI: executed checks for an exact candidate SHA.
- Runtime/deployment: deployed and observed behavior only.
- PXK-web-skill Confluence and frozen Skill package: migration source / Regression Oracle, not permanent PXAPI domain authority.

## Current authorized product direction

- One canonical Analysis Run feeds internal and external projections.
- Measurement, business context, synthesis, scoring/product diagnosis, customer projection, rendering and adapters remain separate responsibilities.
- Missing/unavailable/provider-error evidence must not become a website defect or score penalty.
- Acquisition and site intelligence are PXAPI responsibilities; the Skill remains migration source / Regression Oracle.
- Sampling is Pixelkiez methodology, not provider policy.
- Static HTTP and rendered browser evidence are separate observation modes.
- Crawl4AI is an adapter candidate, not domain authority.
- WIP limit: 1 mutating implementation theme.

## Current code truth

**On `main` at `ce4de1820d2516f9b3bf73b11ad9441dbad941ba` (2026-09-29).** PXAPI-20.B is merged: manifest-driven multi-page static acquisition (`AcquireSelectedPages`, `build_site_acquisition`, `acquire_cli` with a required `--max-selected-pages`) and `.agent-proofs.json` are on `main`. The statements below that call 20.B a candidate "not on `main`" are the 2026-09-27 truth, preserved.

**On the PXAPI-25 candidate (branch `agent/pxapi25-operator-workbench`, not on `main`).** Additive only — no existing `src/` file is modified: the registered `analysis-validation-receipt.v1` contract; `domain/run_validation.py`, `ports/contract_validation.py`, `application/validate_analysis_run.py` (run validation); `adapters/inbound/workbench.py` and `workbench_views.py` (the Operator Workbench, `uvicorn pxapi.adapters.inbound.workbench:app`); the `browser` dependency group, `tests/browser` and the `workbench-browser` workflow; `tools/pxapi25_workbench_real_boundary_proof.py`. Five `PXAPI-25` entries join `BEHAVIOR_ALLOWED`. `POST /v1/analysis-runs` is unchanged and homepage-only.

**On `main` at `e4066161f5d31bb10fccb9d36baac4197e61fc02` (20.A merged).** The PXAPI-19.B site-discovery runtime **is present**, including the PR #18 discovery-correctness repair. `SiteDiscoveryPort`, `HttpSiteDiscovery`, the `DiscoverSite` use case, the deterministic `CENSUS_FIRST_DETERMINISTIC` planner, producer-side semantic enforcement and `python -m pxapi.adapters.inbound.discover_cli` are all on `main`, authorized by the twelve `PXAPI-19.B` entries in `BEHAVIOR_ALLOWED` (`tests/test_package_scaffold.py`). PXAPI-20.A added, and `main` now carries, the registered `page-acquisition-record.v1` contract with its examples and invalid fixtures, the acquisition vocabulary and producer invariants in `src/pxapi/domain/page_acquisition.py`, and the isolated generic static-page observer `src/pxapi/application/observe_static_page.py`, authorized by two `PXAPI-20.A` entries in `BEHAVIOR_ALLOWED`. `main` itself still fetches no discovered page: 20.A deliberately shipped no multi-page runtime.

**On the 20.B candidate at `28e29a0aff59cd41a4bc1cb96030075082d9f4ad` (not on `main`).** Manifest-driven multi-page static acquisition **is implemented**: `src/pxapi/application/acquire_selected_pages.py` orchestrates discovery → admission → one static fetch per selected page → `PageAcquisitionRecord(STATIC_HTTP)` → page-scoped measurements and evidence; the admission gate in `domain/page_acquisition.py` runs before any fetch; `build_site_acquisition` is in the composition root; `python -m pxapi.adapters.inbound.acquire_cli` requires an explicit `--max-selected-pages N`; the mandatory proof descriptor `.agent-proofs.json` and the harness `tools/pxapi20b_real_boundary_proof.py` exist; and the real-boundary proof has been executed and verified against `https://www.rfc-editor.org/` on that exact head (see *PXAPI-20.B candidate*). Two `PXAPI-20.B` entries join `BEHAVIOR_ALLOWED`.

Acquisition is therefore no longer homepage-only: one run establishes a canonical public origin, reads `/robots.txt` for `Sitemap:` declarations only, reads sitemaps and bounded same-origin seed links, canonicalizes and deduplicates them into a `site-inventory.v1`, plans a `sampling-manifest.v1` in `CENSUS` mode and — on the 20.B candidate — acquires every selected page over `STATIC_HTTP` within the operator-declared selection budget. **Historical statement, preserved:** the 2026-09-19 snapshot recorded here that "no discovered page is fetched — page acquisition over the manifest is PXAPI-20 and is not implemented"; that was true of `19a9a855` and remains true of `main` until 20.B merges.

**The defects found after the 19.B merge are dispositioned.** A post-merge review had found four defect classes inside the authorized boundary (AD-007, `C-PXAPI-013` … `C-PXAPI-016`). PR #18 repaired the two that were implementation defects — malformed-link isolation, together with the same defect class in `robots.txt` declaration reading (NF-5), and fragment canonicalization — and Jira `PXAPI-19` comment `16081` ruled the canonical-seed finding superseded as an implementation defect and the named-limit finding non-material. Residues that were recorded but do not block PXAPI-19 are listed under *Non-blocking follow-up candidates* below. The discovery layer still makes **no** completeness claim about a real site beyond what one inventory records: the accepted Real-Boundary evidence proves one controlled public-origin boundary (AD-006).

PXAPI-19.A had added the provider-neutral contract/foundation layer for that step, including registered `site-inventory.v1` and `sampling-manifest.v1` schemas, shared acquisition definitions, valid examples, targeted invalid fixtures, deterministic digest/semantic guards and contract evidence. 19.A intentionally introduced no runtime; 19.B is what made those contracts executable.

Still **not** present on `main` at `e4066161`, nor on the 20.B candidate at `28e29a0`: browser/Crawl4AI execution, `RenderedPagePort`, any `RENDERED_BROWSER` producer, scoring/customer output changes, PDF, queueing, CRM integration and deployment behavior. No customer-value claim follows from the 19.B merge, from its repair, from the closeout, from the 20.A merge or from the 20.B proof. **Historical statement, preserved:** at `19a9a855` the list of absent items also included multi-page static acquisition and `page-acquisition-record.v1`; the contract and observer arrived on `main` with 20.A, and the runtime exists on the 20.B candidate, so that part of the list is no longer current truth.

## PXAPI-19.A closeout

**Bounded 19.A state:** `CLOSED / VERIFIED`

- PR head/candidate: `1ec66b6bc38cc8a3c1959af211797b9220bbb8d1`
- PR: `#14`, merged
- merge / integrated implementation baseline: `926c2415503f27084ab314629548b2e79ddce8a9`
- post-merge main CI: `python-compat` run `34557847326`, exact head SHA `926c2415503f27084ab314629548b2e79ddce8a9`, `success`
- 19.A IC: `GREEN`
- 19.A R2G: `GREEN`
- 19.A R4M: `GREEN`, consumed by merge
- runtime/deployment evidence for 19.A: `NOT_APPLICABLE`

Overall Jira item `PXAPI-19` stayed incomplete and `In Arbeit` after 19.A. Its ticket-level state is recorded under *PXAPI-19 ticket-level closeout* below.

## PXAPI-19.B closeout

**Bounded 19.B state:** `MERGED / REPAIRED BY PR #18`. From 2026-09-17 until the PR #18 merge on 2026-09-18 it was `MERGED / REPAIR REQUIRED`; that state is historical.

- PR head/candidate: `7e5d67eb95f85216eff32d99ff82227cb5786efc`
- PR: `#16`, merged 2026-09-11T23:54:09Z
- bound base: `468ce6f187efcd108a930bf977858a3790e4bc52`
- merge / integrated implementation baseline: `fe8d838023c8f9967151cad9aa1981e76dcf7d75`
- candidate CI: `python-compat` run `34653734998` (`push`) and `34653738494` (`pull_request`), both exact head `7e5d67eb95f85216eff32d99ff82227cb5786efc`, both `success`, Python 3.13 and 3.14 jobs `success`
- post-merge main CI: `python-compat` run `34659764590`, exact head `fe8d838023c8f9967151cad9aa1981e76dcf7d75`, `success`
- `git diff fd3ad8a..7e5d67e -- src/ tests/ contracts/` is **0 bytes**, so the gate results measured on `fd3ad8a` carry to the merged head for code, lint and tests
- 19.B IC — **historical verdict about `fe8d838`, superseded by the repair:** `NOT_GREEN — REPAIR REQUIRED`, per Jira `PXAPI-19` comment `16045` (2026-09-17), which had itself superseded an earlier `GREEN` claim. The repair increment that answered it carries its own gates (see *PXAPI-19 discovery-correctness repair*). This verdict about `fe8d838` is preserved, not rewritten.
- 19.B R2G — **historical verdict about `fe8d838`, superseded by the repair:** `NOT_GREEN`, because R2G requires IC `GREEN` on the same candidate. This was a gate verdict, not a CI result: the CI runs above really did pass on the exact candidate and on the merge SHA, and they remain accurate.
- 19.B R4M: `UNKNOWN — HISTORICAL GOVERNANCE EXCEPTION`. Never independently evidenced, and **never to be recorded as `GREEN`**. Decision authority: Jira `PXAPI-19` comment `16044` (2026-09-17). See AD-005. PR #18's own `R4M` does not alter it.

**What R2G covers here.** `.github/workflows/python-compat.yml` is the only workflow. It runs `uv sync --locked`, `uv lock --check`, `ruff check`, `ruff format --check` and `uv run pytest` on Python 3.13 and 3.14. Contract validation runs inside that suite. The workflow's own header records that repository-wide security, secret and dependency-security scanning are deliberately **not** implemented here and belong to A8. `main` carries no branch protection, so no review was required to merge.

## PXAPI-19 discovery-correctness repair (PR #18)

**Bounded state:** `MERGED — IC / R2G / R4M GREEN at the exact head, R4M consumed by merge`

- PR: `#18`, merged 2026-09-18T12:06:39Z
- bound base: `aa75d6b52fe060b76a7cf900617ad5f990901183` (the merge of documentation-reconcile PR #17)
- exact candidate: `95c061a0716a25031145587a3cc40bbf5c04b6a4`
- merge / current implementation baseline: `bfe06cc07ea0dfde31fedb8e7115940da24fb9fd`; its tree is byte-identical to the candidate's (`git diff --quiet 95c061a bfe06cc` exits 0)
- candidate CI: `python-compat` run `35335399143` (`push`) and `35335402205` (`pull_request`), both exact head `95c061a…`, both `success`
- post-merge main CI: `python-compat` run `35342958323`, exact head `bfe06cc…`, `success`, Python 3.13 and 3.14 jobs `success`
- IC `GREEN`, R2G `GREEN`: Jira `PXAPI-19` comment `16081` (`AD-008`). R4M `GREEN — READY FOR MERGE`: comment `16082` (`AD-009`), for exact head `95c061a…` only. Merge receipt: comment `16083`.
- finding dispositions (comment `16081`, `D-PXAPI19-PO-009`): `C-PXAPI-013` closed, together with NF-5 in `_robots()`; `C-PXAPI-014` closed; `C-PXAPI-015` superseded as an implementation defect; `C-PXAPI-016` non-material as an implementation defect.
- scope: `src/` +93 −18 across `html_links.py`, `site_discovery.py` (`_robots()` only) and `site_identity.py`, plus tests and one evidence document. `contracts/`, `.github/`, `pyproject.toml` and `uv.lock` are a 0-byte diff against the base. No PXAPI-20 surface.
- evidence: `docs/evidence/PXAPI-19B-discovery-correctness-repair.md`.

## PXAPI-19 ticket-level closeout

**Jira state at snapshot:** `Erledigt` (read live 2026-09-19). The closeout labels `closeout-only`, `repair-required` and `delivery-ready-blocked` are no longer on the issue (read live 2026-09-19; the removal is recorded in Jira `PXAPI-20` comment `16258`).

**Evidence state.** The final AC1–AC9 evidence matrix, the AC8 evidence class and ceiling, and the contradiction dispositions are in `docs/evidence/PXAPI-19-final-closeout.md`; the machine-readable AC8 receipt is `docs/evidence/PXAPI-19-AC8-real-boundary-receipt.json`. AC8 is accepted **with its explicit evidence ceiling** (AD-006, `D-PXAPI19-PO-011`).

**Gates.** The historical PR #16 `R4M` stays `UNKNOWN`, permanently. PR #18's gates apply to `95c061a…` only. Ticket-level PXAPI-19 IC / R2G / R4M are Orchestrator and Product Owner authority and are not declared by this file.

**Closeout record.** Jira `PXAPI-19` comment `16257` (2026-09-19) is the Product Owner's final ticket closeout: final integration SHA `19a9a855d603384c216bbf9ab92e4e7cb0334bfb`, closeout PR #19, exact reviewed head `bd2c95b666c21fb207975243b34fb864659839dc`, post-merge `main` CI `python-compat` run `35414652333` **success** on that exact merge SHA with the Python 3.13 and 3.14 jobs both `success`. It accepts AC1–AC9 as mapped in the two evidence artifacts, keeps the AC8 evidence ceiling, and states that the historical PR #16 `R4M = UNKNOWN` is permanent and not retroactively changed.

**The three PXAPI-20 unlock conditions are met.** They were recorded here on 2026-09-19 as `BLOCKED / NOT AUTHORIZED` until, in order: (1) the PXAPI-19 closeout PR is merged; (2) post-merge `main` CI succeeds on that exact merge SHA; (3) the PXAPI-19 closeout is recorded in Jira and read back. Each is now evidenced: (1) PR #19 merged as `19a9a855…`; (2) run `35414652333` on head `19a9a855…`, `success`; (3) comment `16257`, read back in Jira `PXAPI-20` comment `16258` ("PXAPI-19: **Erledigt**, readback-verified"). The prior blocked state is preserved above as the condition set it discharged, not deleted.

## PXAPI-20 authorization and delivery shape

**Jira state:** `In Arbeit`, priority `Highest` (read live 2026-09-19). **WIP = PXAPI-20 only.**

**Authority chain, all read live on 2026-09-19:**

- Jira `PXAPI-20` comment `16258` — `PRE_IMPLEMENTATION` reconcile: PXAPI-19 `Erledigt` and readback-verified, canonical `main` `19a9a855d603384c216bbf9ab92e4e7cb0334bfb`, exact-merge-SHA CI run `35414652333` success on both interpreters, architecture authority Confluence `54362115` `ACCEPTED`, DRS authority Confluence `55181314` `CURRENT`. It required the first coding-agent action to be `PLAN_REQUIRED_STOP` with an architecture/change-scope declaration against that exact base.
- Jira `PXAPI-20` comment `16259` — Product Owner plan review: **APPROVED WITH BOUNDED AMENDMENTS**, and **Delivery Ready = GREEN** for PXAPI-20 under the decisions `D-20-A` … `D-20-P`. That comment supersedes the `Delivery Ready = BLOCKED` state of comment `16042`. Delivery readiness is a project decision and **not** a DRS runtime gate.

**DRS at this snapshot** (comment `16259`, unchanged by it): `definition_state = DRS_DEFINITION_READY`, `IC = UNKNOWN`, `R2G = UNKNOWN`, `R4M = UNKNOWN`. Nothing green is inherited from PXAPI-19.

**Delivery shape (`D-20-K`).** One Jira item, one WIP theme, two sequential PR candidates:

- **`20.A` — Static Page Evidence Foundation.** A first documentation commit reconciling this file, the decision ledger and the contradiction ledger (`D-20-N`, discharging condition 3 of comment `16042` inside the PXAPI-20 branch rather than in another docs-only PR); `page-acquisition-record.v1` with examples and targeted invalid fixtures; its domain semantics and invariants; an isolated generic static-page observer with deterministic tests. **No production multi-page CLI or runtime.**
- **`20.B` — Multi-Page Runtime & Real-Boundary.** Rebound to the post-20.A `main`: manifest → safe page fetch → acquisition record → measurements/evidence orchestration, composition and CLI, integration and error-path tests, the multi-page Real-Boundary smoke, final traceability evidence.

Each candidate carries its own bounded `IC` / `R2G` / `R4M`. **Neither the 20.A merge nor its green gates make `PXAPI-20` Done**, and no second Jira ticket is created.

### PXAPI-20.A candidate

**State:** **merged** as `e4066161f5d31bb10fccb9d36baac4197e61fc02` (PR #20), now `main`. Base
`19a9a855d603384c216bbf9ab92e4e7cb0334bfb`; evidence
`docs/evidence/PXAPI-20A-static-page-evidence-foundation.md`. The `F-20A-R4M-001`
shared-vocabulary narrowing found by the independent `R4M` review (Jira `PXAPI-20` comment `16325`)
was repaired on the candidate **before** the merge (`C-PXAPI-021`). The 20.A gate verdicts and the
merge itself are Orchestrator and Product Owner authority and are **not** declared by this
repository; the 20.A merge does not make `PXAPI-20` Done (`D-20-K`). **Prior state, preserved:**
"candidate open, **not** on `main`; five commits" — true when the 2026-09-19 snapshot was written.
The paragraphs below describe what the candidate added and are kept as history.

What the candidate adds, and nothing else: the registered `page-acquisition-record.v1` contract
with three examples and fourteen targeted invalid fixtures; `src/pxapi/domain/page_acquisition.py`
(the acquisition vocabulary, the contract-URL predicate, the body digest and eleven producer
invariants); `src/pxapi/application/observe_static_page.py` (an isolated generic static-page
observer). Two `PXAPI-20.A` entries join `BEHAVIOR_ALLOWED`.

What it deliberately does **not** add: no multi-page CLI or runtime, no orchestration over a
manifest, no composition wiring — nothing calls the observer and no page is fetched; no HTTP
endpoint; no browser, Crawl4AI, queue, worker, ArtifactStore, scoring or customer output; no
`DiagnosticFinding` on any page path. `AnalyzeHomepage`, `derive_findings`, `discover_site`,
`adapters/web/**`, `ports/**`, `config/**`, `adapters/contracts/**`, `adapters/composition.py`,
`adapters/inbound/**`, the twelve existing schema files, `pyproject.toml`, `uv.lock`, `.github/`
and `oracle/` are each a **0-byte** diff against the base, so the candidate adds no dependency,
changes no CI, changes no existing contract and changes no homepage behaviour.

**Hard amendments that bound 20.A** (comment `16259`): `AnalyzeHomepage` is not refactored, subclassed, extracted in place or behaviourally modified, and `H1`–`H5` are not repaired in this slice (`D-20-E`, see `C-PXAPI-018`); the static-page path is a separate generic observation path; the **producer** observes with `observation_mode = STATIC_HTTP` only, while the contract carries the architecture's own `STATIC_HTTP | RENDERED_BROWSER` vocabulary (`D-20-C` as reconciled by `F-20A-R4M-001`); page linkage uses `measurement_refs` and neither `measurement-record.v1` nor `website-evidence.v1` is versioned to carry page identity (`D-20-B`); site-caused and technical outcomes stay neutral while PXAPI's own contract/invariant defects stay visible run failures (`D-20-D`); `raw_artifact_ref` exists as optional opaque provenance and is never emitted (`D-20-H`); the HTML parser is not altered and `H7` is an operational precondition rather than a blocker (`D-20-L`, see `C-PXAPI-019`); existing `SafePageFetcher` safety coverage is not duplicated to raise test volume (`D-20-O`); after 20.B merges with green gates, feature development **stops** for the first real customer/prospect pilot (`D-20-P`).

### PXAPI-20.B candidate

**State:** candidate at exact head `28e29a0aff59cd41a4bc1cb96030075082d9f4ad`, **not** on `main`;
**no PR created, not merged, ticket not Done.** Base `e4066161f5d31bb10fccb9d36baac4197e61fc02`
(PXAPI-20.A merged, PR #20). Evidence `docs/evidence/PXAPI-20B-multi-page-runtime.md`. DRS
`IC` / `R2G` / `R4M` are Orchestrator and Product Owner authority and are **not** declared here;
an independent Governor review **recommends** `IC` / `R2G` / `R4M` `GREEN` for `28e29a0`, and a
recommendation is not a declared gate. The paragraphs on the 20.A candidate above are kept as
history; 20.A is merged.

What the candidate adds: `src/pxapi/application/acquire_selected_pages.py` (the orchestrator:
discovery → admission → one static fetch per selected page → acquisition record → page-scoped
measurements and evidence); an admission gate in `domain/page_acquisition.py` that runs before
any fetch; `build_site_acquisition` in the composition root; `adapters/inbound/acquire_cli.py`
with a **required** `--max-selected-pages N` and no default; the D-20-F reading constraint in the
observer (a non-2xx document is not parsed as page content); focused tests and an opt-in
multi-page real-boundary smoke. Two `PXAPI-20.B` entries join `BEHAVIOR_ALLOWED`. Later commits on
the candidate added the proof harness `tools/pxapi20b_real_boundary_proof.py`, its tests, the
canonical container-cardinality check in `acquire_cli` (`C-PXAPI-022`, closed at `c1bf4cd5…`), the
interpreter / configuration / `PATH` discovery repairs (`C-PXAPI-023`, closed at `479bc1db…`) and,
as the final descriptor-only change, `.agent-proofs.json` registering `pxapi20b-real-boundary` as a
mandatory proof (`28e29a0`).

**Real-boundary proof, executed and verified at `28e29a0`** (`run-pxapi20b-proof-activate-20260927-004`,
status `VERIFIED`, reason `VERIFIED_ORACLE_CHANGED/INDEPENDENT_REVIEW` because `.agent-proofs.json`
was the intentional one-file oracle change): target `https://www.rfc-editor.org/` via the
production module `pxapi.adapters.inbound.acquire_cli` with explicit `--max-selected-pages 3` and a
fresh output directory; selected installed system Python `/opt/homebrew/opt/python@3.14/bin/python3.14`
`3.14.6` (`D-20-L`), disposable project runtime also `3.14.6`, `uv.lock` byte-identical before and
after; run `px-8674bf01befc4c849bd77de39621c3c6` `SUCCEEDED`; inventory of 506 candidates; manifest
`selected_count = 3`, `selection_complete = false`, `SELECTION_BUDGET_EXHAUSTED`, 503 excluded by
budget; three page acquisitions, all `RESPONSE_RECEIVED` HTTP 200 with 13 measurements and 13
evidence records each, 39 measurements and 39 evidence records in total, every one linked to
exactly one page; producer `STATIC_HTTP_PAGE_FETCH 1.0.0` / `STATIC_HTTP` only. Runner
verification on the exact head: `3307 passed, 2 skipped`, Ruff green; exact-head GitHub Actions
`python-compat` run `36349224176` `success`. The independent artifact review recomputed all ten
published SHA-256 values, canonical counts, digests and linkage with no findings. Every id, digest
and artifact SHA-256 is in the evidence document.

**Evidence ceiling.** One bounded point-in-time selection of one controlled public origin over
`STATIC_HTTP`. No complete-site claim beyond `selection_complete = false`; no browser, scoring, PDF,
production-scale, customer-value or future-refetch-determinism claim. The boundary observed three
successes; neutral mixed failure remains test regression evidence, not observed in this proof.

**What is still pending for 20.B:** PR creation, independent exact-head `R4M` declaration
(`D-20-M`), merge, exact-merge-SHA `main` CI, and the `PXAPI-20` ticket closeout. Because a
commit cannot contain its own SHA, the documentation-only head that records this evidence is
re-proved by the Delivery Runner at its own exact SHA with fresh artifacts; the figures above stay
bound to `28e29a0`.

## PXAPI-25 candidate

**State:** candidate on `agent/pxapi25-operator-workbench` from exact base `ce4de1820d2516f9b3bf73b11ad9441dbad941ba`; **not merged, ticket not Done.** Evidence `docs/evidence/PXAPI-25-operator-workbench.md`; every executed figure there is bound to the SHA it names. DRS `IC` / `R2G` / `R4M` are Orchestrator and Product Owner authority and are **not** declared here.

What it adds: the first browser-visible PXAPI product surface. An internal operator enters a URL and an explicit page budget, starts exactly one synchronous multi-page run through the existing core, and inspects run and stage state, inventory, manifest and `selection_complete`, per-page acquisition outcomes, page → measurement → website evidence, limitations, and a run-level `analysis-validation-receipt.v1` (seven gates, `FAIL > BLOCKED > PASS`, `NOT_APPLICABLE` neutral), then downloads the canonical bundle and the receipt. State is ephemeral by design (one active run, the latest completed run, memory only).

**Independent review and repair.** A read-only adversarial review of `ce4de18..7e5572d` (five lenses, each finding checked by a refuting verifier) confirmed 13 of 20 findings, 10 distinct; all were fixed at `32703a67b5af03f5b297e6ad18d996e9ab349d74` with RED tests first, and eleven deliberate mutants of the fixes and key rules were each killed. Details in the evidence document, §5.

**Real-boundary browser proof, executed at `32703a67b5af03f5b297e6ad18d996e9ab349d74`:** production Workbench, Chrome 154 headless via Playwright, `https://www.rfc-editor.org/`, budget 3 → run `SUCCEEDED`, three pages `RESPONSE_RECEIVED` HTTP 200, 39 measurements and 39 evidence records, `selection_complete = false` (`SELECTION_BUDGET_EXHAUSTED`); validation `BLOCKED` on `ACQUISITION_COMPLETENESS` (`SELECTION_INCOMPLETE`) and `UNRESOLVED_CONFLICTS_LIMITATIONS` (`DISCOVERY_SOURCE_LIMITED`: the sitemap source hit this service's own 500-entry bound), every other gate `PASS`; the canonical bundle and the receipt downloaded through the browser and read back independently with no problem. Exact-head CI at `32703a6`: `python-compat` run `36494804515` (3.13.15 and 3.14.7, `3816 passed, 3 skipped` each) and `workbench-browser` run `36494804385` (`7 passed`), all `success`. An earlier proof at `7e5572d` (before the review fixes) also passed and is kept in the evidence document.

**Evidence ceiling.** One bounded point-in-time run of one public origin, static HTTP only; internal operator use on loopback; no durability, no authentication, no public deployment, no business diagnosis, no customer output.

## Completed prerequisite

`PXAPI-4` — Skill Capability Baseline & Parity Gap Contract — is **Erledigt** as of 2026-09-10 for its discovery/contract scope.

Accepted source-bound baseline:

- Confluence page `54362137` — `PXAPI — Skill V2.1 Capability Baseline & Parity Gap Matrix — 2026-09-10`;
- Skill artifact `pixelkiez-website-diagnosis_V2.1.zip`;
- Skill ZIP SHA-256 `ab8bba6d1bbd23179b7a9761767971def54986a8e398da38919ea37c23ebb060`;
- Skill package artifact digest `959ea94775c147ca3d6c197a4cc62f4e603557b53ec6bf8ca236a67ffabee13b`.

This completion proves the source-bound parity/gap decision artifact, not implementation parity.

## Current prioritized delivery sequence

**Current ordering (2026-09-28, Confluence `71991298` v3 §6 and §18):** `PXAPI-25` Operator Workbench & Multi-Page Run Validation (the current `WIP=1` theme) → `PXAPI-23` Cross-Page Business Diagnosis → `PXAPI-24` Strategic Lever Hypothesis → `PXAPI-7` Customer Report Model / PDF → commercial pilot gate. How this relates to `D-20-P` is open and recorded as `C-PXAPI-025`. The numbered list below is the 2026-09-27 ordering, preserved as history.

1. **`PXAPI-20` — Multi-Page Static Acquisition & Canonical Evidence Population v1** — the current and only `WIP=1` theme, `20.A` then `20.B` (see *PXAPI-20 authorization and delivery shape*). `PXAPI-19` closed on 2026-09-19 (comment `16257`) and its three unlock conditions are discharged; the historical statements that PXAPI-20 stayed blocked — Jira `PXAPI-19` comments `16044`, `16045`, `16081`, `16083` — remain accurate about the moment each was written and are not rewritten.
2. **The first real customer/prospect pilot** — mandated by `D-20-P` immediately after 20.B merges with exact-merge-SHA `main` CI green and the bounded multi-page Real-Boundary gate passed. Browser/Crawl4AI, async queueing, automated PDF, scoring redesign and cross-page diagnosis do **not** start before that pilot unless a newly discovered blocker makes the pilot impossible.
3. Re-measure evidence gain before paying browser/async complexity — the pilot is that measurement.
4. Depending on observed bottleneck, continue with either cross-page diagnosis (`PXAPI-23`) or async/browser path (`PXAPI-15..18`, then `PXAPI-21`, `PXAPI-22`).
5. Strategic lever / impact verification contracts (`PXAPI-24`) later.

The 80/20 expectation is a Product Owner hypothesis, not production-measured fact.

## PXAPI-19.B delivered scope

19.B was implemented from base `468ce6f187efcd108a930bf977858a3790e4bc52` and merged as `fe8d838023c8f9967151cad9aa1981e76dcf7d75`. The scope below is what it was authorized to deliver and what the merged tree carries:

- provider-neutral `SiteDiscoveryPort`;
- safe canonical public target-origin establishment and same-origin discovery;
- bounded `/robots.txt` support only for `Sitemap:` declarations;
- sitemap handling with neutral missing/malformed/runtime states;
- bounded same-origin links and transient normalized anchor-label signal;
- runtime canonicalization/deduplication with provenance aggregation;
- page type/stratum classification and deterministic planner production;
- executable `CENSUS`-only policy while the census-to-sampling threshold remains `MISSING`; `STRATIFIED_SAMPLE` remains contract vocabulary only;
- producer-side enforcement of 19.A semantic invariants;
- controlled public Real-Boundary-Smoke for PXAPI-19 acceptance.

Out of scope for 19.B, and verified absent on `fe8d838`: browser/Crawl4AI, PXAPI-20 multi-page static acquisition pipeline, scoring/PDF/customer projection, PostgreSQL queue/worker, CRM/buyer-intent and deployment changes. `pyproject.toml`, `uv.lock`, `.github/` and `contracts/` are each a **0-byte** diff against the base, so 19.B added no dependency, changed no CI and changed no contract. The PR #18 repair stayed inside this scope and likewise changed no contract, dependency or workflow.

## Anti-drift findings

### AD-001 — stale legacy PR

GitHub PR #5 (`PXK-17 (A4): define Contracts v1 and the Analysis Run state machine`) remains stale legacy drift. It is not active WIP. A separate reconcile is required before any close/merge decision.

### AD-002 — repository governance context

The repository context documents exist and are maintained as rehydration aids. Their presence does not prove the project is globally drift-free; live reconciliation remains mandatory.

### AD-003 — Jira dependency-link direction conflict

Jira's raw issue-link representation for `PXAPI-19` currently exposes `PXAPI-20` and `PXAPI-21` as `inwardIssue` values under the `Blocks` link type (`is blocked by`), while the accepted product sequence and downstream Jira descriptions require full `PXAPI-19` before `PXAPI-20`. Other Jira graph rendering may present the relationship differently.

Status: `CONFLICT / OPEN / NON-BLOCKING`. It did not block the PXAPI-19 closeout and it does not block PXAPI-20: the authorization comes from Jira `PXAPI-20` comments `16258` and `16259`, never from a link representation. Do not mutate, reverse or delete these links until the current link semantics and a safe reversible operation are independently verified, and do not infer PXAPI-20 authorization from the link representation.

### AD-004 — sampling threshold remains missing

The census-to-stratified-sampling threshold remains `MISSING`. No numeric threshold may be invented in 19.B. Executable policy remains `CENSUS`-only until representative benchmark evidence and an explicit versioned decision exist.

### AD-005 — the 19.B candidate merged without an independent exact-head R4M

**Status: `DECIDED / HISTORICAL GOVERNANCE EXCEPTION — PRESERVED`. Not an open evidence search.**

**Historical gate state: `R4M = UNKNOWN`.** Permanently. It is **never** to be reconstructed, inferred or retroactively recorded as `GREEN`.

**Decision authority:** Jira `PXAPI-19` comment `16044`, 2026-09-17 — *"AD-005 — Historical R4M decision / closeout governance"*. Indexed as `D-PXAPI19-PO-008`.

What was measured: the merge commit `fe8d838` states that PR #16 was merged "after exact-head R4M", and no artifact independently supporting that statement exists. On `fe8d838`, `git grep -l '7e5d67eb95f85216eff32d99ff82227cb5786efc' HEAD` returned **0** tracked files, and `grep -c '7e5d67e' docs/evidence/PXAPI-19B-site-discovery-runtime.md` returned **0**. The second count is still 0 at `bfe06cc`. The first is not, and the reason matters: at `bfe06cc` it returns 3 files, and each only *cites* the candidate SHA: this file and `docs/context/contradiction-ledger.md` while recording this very gap, and `docs/evidence/PXAPI-19B-discovery-correctness-repair.md` as the starting `HEAD` of its repair. None is an R4M artifact, so the absence stands. The 19.B evidence document explicitly declines to declare one ("`R4M` is not declared here"; "**MISSING:** an independent `R4M`"), and the candidate's own tip commit message says the same. The only GitHub review on PR #16 is from `sourcery-ai[bot]`, state `COMMENTED`, aborting the review because the diff exceeds its 150,000-character limit; there are zero issue comments and zero review comments. `main` carries no branch protection, so nothing required a review.

**What the Product Owner decided.** Of the two lawful paths this finding originally offered, the second was taken: PR #16 merged **without** independently evidenced exact-head R4M, and that is recorded rather than repaired. The merge is a fact; the missing evidence may be neither reconstructed nor marked passed. The gap is preserved as a governance deviation, not closed by producing something that does not exist. **No retrospective approval has been or may be manufactured.**

**What this is not.** It is not a new implementation defect, and it is not evidence against any PXAPI-19 acceptance criterion. It does bar any claim that the original 19.B merge process was fully DRS-conformant, and that bar is permanent.

**What it no longer is.** A current closeout blocker. AD-005 does not gate PXAPI-19's ticket-level closeout any more, and deciding it authorised nothing: when the decision was written `PXAPI-20` stayed blocked, and AD-006 was untouched and still open. See `C-PXAPI-008`. **2026-09-19 note:** AD-006 has since been resolved on its own authority (below), PR #18 carried its own exact-head `R4M` (AD-009), PXAPI-19 was closed by Jira comment `16257`, and PXAPI-20 was authorised by comments `16258` and `16259`. None of those touches this finding, and this finding contributed to none of them: the historical PR #16 `R4M` stays `UNKNOWN`.

### AD-006 — AC8 real-boundary evidence class

**Status: `RESOLVED — FRESH REAL-BOUNDARY REPRODUCTION ACCEPTED`.** Authority: Product Owner closeout disposition, 2026-09-19 (`D-PXAPI19-PO-011`), now recorded in Jira `PXAPI-19` comment `16257`, which accepts AC8 **only** with its explicit evidence ceiling. See `C-PXAPI-009`.

The Product Owner accepts, for ticket closeout, a **fresh** reproduction from an attached clean `main` checkout at `bfe06cc07ea0dfde31fedb8e7115940da24fb9fd` against `https://www.rfc-editor.org/`, on Python 3.13.3 and 3.14.6. The opt-in smoke passed on both. Each run established the canonical origin and produced a contract-valid `SiteInventory` and `SamplingManifest`: 506 eligible candidates, `CENSUS`, 506 selections, `selection_complete = true`, and `SITEMAP = BUDGET_EXHAUSTED` at the declared 500-entry discovery bound, which stayed a technical source outcome and produced no website finding, score or severity. Receipt: `docs/evidence/PXAPI-19-AC8-real-boundary-receipt.json`.

**Evidence ceiling.** This proves one controlled public-origin Discovery → SiteInventory → SamplingManifest boundary. It does **not** prove complete site coverage, arbitrary crawling, production scale, browser rendering, PXAPI-20, scoring quality, customer output or customer value. It is a new reproduction, not a retroactive upgrade of the historical 2026-09-11 record.

**Prior state, preserved** — `OPEN / EVIDENCE CLASS`, with this record:

> The controlled public Real-Boundary-Smoke required by PXAPI-19 AC8 exists in this repository in two forms, and they are not the same thing. The **mechanism** is committed and executable: `tests/smoke/test_real_boundary_smoke.py` drives the shipped composition against a real public origin and is opt-in through `PXAPI_REAL_BOUNDARY_SMOKE_URL`, so it is skipped in CI. The **execution record** of the runs against `www.rfc-editor.org` and `example.com` is prose in `docs/evidence/PXAPI-19B-site-discovery-runtime.md` section D; no machine-readable capture accompanies it (`git ls-files docs/` matches **0** `.json`/`.txt`/`.log`/`.csv` files), and the document states its run driver is scratchpad tooling outside the repository.
>
> Status: `OPEN / EVIDENCE CLASS`. The prose record is `DOC_PERSISTED`, not independently verified by any committed artifact. Re-deriving it requires outbound network access. See `C-PXAPI-009`.

### AD-007 — the merged 19.B discovery implementation had material defects

**Status: `RESOLVED — REPAIRED AND DISPOSITIONED`.** Authority: Jira `PXAPI-19` comments `16081` (`AD-008`) and `16082` (`AD-009`); PR #18 merged as `bfe06cc`. Findings A and B were repaired by PR #18; finding C was superseded as an implementation defect; finding D was ruled non-material under the currently authoritative named-limit definitions. See `C-PXAPI-013` … `C-PXAPI-016`.

**Prior state, preserved** — `OPEN / REPAIR REQUIRED`, the mutating theme from 2026-09-17 until the PR #18 merge on 2026-09-18, with this record:

> **Decision authority:** Jira `PXAPI-19` comment `16045`, 2026-09-17 — *"PXAPI-19 closeout reopened — implementation repair required"*, which supersedes the earlier `19.B IC = GREEN` closeout claim.
>
> A post-merge review of the already merged 19.B implementation surfaced four defect classes inside the boundary 19.B was **already authorized** to deliver. They were first reported by a coding agent and then independently corroborated against the exact current `main` `fe8d838023c8f9967151cad9aa1981e76dcf7d75`. None of them opens new scope, and none of them is a PXAPI-20 concern.
>
> **A — malformed-link isolation is not preserved.** `read_links()` (`src/pxapi/adapters/web/html_links.py`) wraps only the parser feed loop in the guard that converts failures into `HtmlUnreadable`; `_base_for(...)` and the `urljoin(base, target)` loop run outside it. A malformed `<base href>` or a malformed `href` therefore raises after parsing, and the whole `SAME_ORIGIN_PAGE_LINKS` source ends as `RUNTIME_ERROR` with zero observations — discarding the valid sibling links of the same document. The module's own contract says the opposite: *"Unclosed tags, stray markup and links nested in ways the standard forbids are ordinary input and are read tolerantly."* See `C-PXAPI-013`.
>
> **B — canonicalization contradicts its own fragment rule.** `_canonicalise()` (`src/pxapi/domain/site_identity.py`) scans the whole raw written form for forbidden characters *before* `urlsplit`, while `URL_CANONICAL_BASELINE` and the module's own comment state that the fragment is dropped without being examined. A URL whose page identity is perfectly valid but whose fragment contains a space is therefore refused outright and omitted from the inventory — losing a page, which that module names as the one error it must not make. See `C-PXAPI-014`.
>
> **C — canonical-seed source truth is overstated.** `HttpSiteDiscovery` (`src/pxapi/adapters/web/site_discovery.py`) initializes `CANONICAL_SEED` as `SourceOutcome.USED` immediately after origin bootstrap, without deriving that outcome from the seed's HTTP status; the link source evaluates the same status separately two lines later. A 4xx/5xx seed response can therefore be reported as a successfully used canonical-seed source. This bears directly on AC6, which requires technical states to be modelled truthfully and neutrally. See `C-PXAPI-015`.
>
> **D — the named discovery limits do not bound what the prose implies they bound.** Off-origin `Sitemap:` declarations return from the planning step before the queue-size gate, so `max_sitemap_documents` does not stop the declaration loop and every declaration is canonicalized. Separately, `max_page_links` bounds distinct written `href` forms while persisted `DiscoveryObservation`s are keyed on `(href, label)`, so one target carrying many labels yields many observations without the source ever reporting `BUDGET_EXHAUSTED`. **Execution remains bounded** — the outer `FetchLimits` response cap still applies to both paths — so this is *not* an unbounded-runtime claim. The defect is precise and narrower: the named limits do not mean what the implementation and the 19.B evidence prose say they mean. See `C-PXAPI-016`.
>
> **Consequences.** 19.B IC is `NOT_GREEN — REPAIR REQUIRED` and 19.B R2G is `NOT_GREEN`. The historical 19.B `R4M` is untouched by this and stays `UNKNOWN` (AD-005). These defects sit inside still-open PXAPI-19 scope and get **no separate ticket**: they are repaired, or explicitly shown non-material, before PXAPI-19 closes. `PXAPI-20` stays blocked throughout.

### AD-008 — PR #18 repair gate and finding-authority reconcile

**Status: `DECIDED`.** Jira `PXAPI-19` comment `16081`, 2026-09-18, indexed as `D-PXAPI19-PO-009`. It supersedes the implementation-defect reading of findings 2–4 of comment `16045` only where the exact-candidate evidence shows a narrower truth, records IC `GREEN` and R2G `GREEN` for PR #18 at `95c061a…`, and leaves AC8 (then still open) and the historical PR #16 `R4M` untouched. The label `AD-008` is Jira's; this repository uses it for the same decision.

### AD-009 — PR #18 exact-head R4M

**Status: `GREEN — READY FOR MERGE`, consumed by merge `bfe06cc`.** Jira `PXAPI-19` comment `16082`, 2026-09-18, indexed as `D-PXAPI19-PO-010`; merge receipt comment `16083`. It applies to exact head `95c061a0716a25031145587a3cc40bbf5c04b6a4` only, and it is neither a ticket-level gate nor Jira Done. The label `AD-009` is Jira's; this repository uses it for the same decision.

## Non-blocking follow-up candidates

`F-1` … `F-3` were surfaced by the final AC8 verification and recorded at the Product Owner's direction as **non-blocking** for PXAPI-19. `F-4` and `F-5` were measured during PXAPI-20 planning against this exact base and are non-blocking for PXAPI-20 by `D-20-E` and `D-20-L`. None is repaired here, and each needs its own authorised ticket before any change.

- **F-1 — terminal `entered_at`.** Terminal `analysis_run_state` documents carry the run's start instant as `entered_at`, while the contract describes it as when the run entered its current state. See `C-PXAPI-017`.
- **F-2 — local trust-store dependency.** The python.org CPython 3.13.3 build on the evidence workstation has no usable compiled-in CA file; HTTPS works only through an inherited `SSL_CERT_FILE` (measured 2026-09-19: 0 CA anchors without it, 193 with it). The fetcher uses `ssl.create_default_context()`, so a misconfigured environment surfaces as a provider failure rather than as a local configuration fault. Live-smoke evidence should record `SSL_CERT_FILE`.
- **F-3 — neutrality helper is key-name based.** `verdict_keys_in` (`tests/application/test_discover_site.py`), which the Real-Boundary smoke also uses, compares **key names** against `VERDICT_KEYS`; it does not inspect values. A value-level anti-verdict test is a future hardening candidate.
- **F-4 — the homepage producer is not hardened against a site-declared canonical (`H1`–`H5`).** Site-controlled HTML can drive `AnalyzeHomepage` into emitting a contract-invalid `CANONICAL_URL` measurement, or into raising out of `run()`. Not repaired in PXAPI-20 (`D-20-E`: the homepage path stays byte-identical). See `C-PXAPI-018`, which records each measured input.
- **F-5 — page parse time is unbounded on some supported CPython builds (`H7`).** `read_html` calls `HTMLParser.close()`, whose cost is quadratic in the number of unclosed tags on CPython 3.13.3. Not repaired in PXAPI-20 (`D-20-L`: the parser is protected; real-boundary and pilot runs use a measured-fast build and record it). See `C-PXAPI-019`.

Of the repair document's other findings, NF-4 (this file naming `fe8d838` as current `main`) was resolved by the PXAPI-19 closeout reconcile, and NF-3 is informational and not a defect. Residues recorded elsewhere and unchanged by the PXAPI-19 closeout and by this PXAPI-20 reconcile, none of them a PXAPI-19 acceptance blocker: NF-1 (no vocabulary for "origin established, seed document answered 4xx/5xx" — a contract question), NF-2 (raw ASCII-space fragment makes an observed form non-persistable — a contract boundary), NF-6 (`EMPTY` for an all-unresolvable-links document), the `CANONICALISATION_VERSION` judgement (all in `docs/evidence/PXAPI-19B-discovery-correctness-repair.md`); the untriaged unguarded `urljoin` at `src/pxapi/application/analyze_homepage.py:478` (the repair document also names `page_fetcher.py:168`, which is in fact already guarded by `except ValueError` at `bfe06cc`); `C-PXAPI-012` (credential echo on the homepage path); and `C-PXAPI-005` / AD-004 (sampling threshold `MISSING`).

## Current Jira focus

- `PXAPI-25` — **In Arbeit** since 2026-09-28 23:35 +02:00 (transition read back live), `Highest`, the only WIP theme; one PR candidate, see *PXAPI-25 candidate*.
- `PXAPI-20` — **Erledigt** (read live 2026-09-29). The `PXAPI-20` bullet below is the 2026-09-27 state, preserved.

- `PXAPI-4` — **Erledigt**, discovery/contract scope accepted.
- `PXAPI-19` — **Erledigt** (read live 2026-09-19), closed by comment `16257`. 19.A is bounded `CLOSED / VERIFIED`; 19.B is merged and repaired by PR #18 (merge `bfe06cc`, gates `GREEN` at exact head `95c061a` per comments `16081` and `16082`); the historical PR #16 `R4M` is `UNKNOWN`, permanently (AD-005); AC8 is accepted with its evidence ceiling (AD-006). The `repair-required` and `delivery-ready-blocked` labels are gone.
- `PXAPI-20` — **In Arbeit**, `Highest`, the only WIP theme (Jira last read live 2026-09-19; not re-read for this 2026-09-27 reconcile). `Delivery Ready = GREEN` (comment `16259`). `20.A` is merged (`e4066161…`, PR #20). Candidate in flight: `20.B — Multi-Page Runtime & Real-Boundary` at `28e29a0…`, runtime plus descriptor plus verified real-boundary proof present; PR, merge and ticket closeout pending. DRS `IC` / `R2G` / `R4M` for 20.B are not declared by this file; independent Governor review recommends `GREEN` for `28e29a0`. **Prior wording, preserved (2026-09-19):** "DRS `IC` / `R2G` / `R4M` all `UNKNOWN`. Candidate in flight: `20.A — Static Page Evidence Foundation`."

No sprint membership or commitment is asserted by this file. Jira must be read live for that claim.

## Delivery gate rules

A coding-agent handoff may be called `READY` only after a fresh PRE_IMPLEMENTATION reconcile verifies:

- current Product Goal / authorities;
- exact Git base SHA;
- architecture snapshot current;
- no unresolved critical drift for the slice;
- one active mutating WIP maximum;
- testable AC, failure paths, evidence requirements and stop conditions.

DRS progression is `IC -> R2G -> R4M`; candidate changes invalidate R2G/R4M. Merge is not Done. CI is not runtime proof. Agent output is not independently verified evidence.

## Rehydrate checklist

On session start/resume, read at minimum:

1. this file;
2. `docs/context/decision-ledger.md`;
3. `docs/context/contradiction-ledger.md`;
4. relevant current PXAPI Confluence pages;
5. relevant Jira issue(s) and actual sprint membership;
6. GitHub default branch head, relevant files, PRs, reviews and CI;
7. runtime only if runtime claims are required.

If any required read is unavailable, classify the affected claim `UNVERIFIED` or `CAPABILITY_MISSING`; do not infer it.
