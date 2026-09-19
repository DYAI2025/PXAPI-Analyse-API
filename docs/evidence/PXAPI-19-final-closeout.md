# PXAPI-19 — Final Evidence & Documentation Closeout

**Jira:** `PXAPI-19` — PXAPI Acquisition Method, Site Inventory & Sampling Manifest v1 (`In Arbeit` when read on 2026-09-19)
**Theme:** PXAPI-19 closeout, documentation and evidence only. No source, test, schema, example,
dependency, lockfile or workflow file is changed by this closeout, and it implements nothing of
`PXAPI-20`.
**Bound base:** `main` = `bfe06cc07ea0dfde31fedb8e7115940da24fb9fd`, verified before any change
(`git fetch origin main`; `git rev-parse HEAD` = `git rev-parse origin/main`; clean worktree).

This document records the evidence for closing PXAPI-19 and the Product Owner's closeout
dispositions. **It does not claim Jira Done, and it does not authorize `PXAPI-20`.** Ticket-level
IC / R2G / R4M are Orchestrator and Product Owner authority and are not declared here.

---

## 1. Bound state

| Fact | Value | Source |
| --- | --- | --- |
| current implementation baseline | `bfe06cc07ea0dfde31fedb8e7115940da24fb9fd` — `main` when this closeout was written | `git rev-parse origin/main` |
| PR #18 exact candidate | `95c061a0716a25031145587a3cc40bbf5c04b6a4` (`fix/pxapi-19-discovery-correctness`) | GitHub PR #18 |
| PR #18 bound base | `aa75d6b52fe060b76a7cf900617ad5f990901183` (merge of documentation-reconcile PR #17) | GitHub PR #18, Jira comment `16082` |
| PR #18 merge | `bfe06cc…`, parents `aa75d6b…` and `95c061a…`, merged 2026-09-18T12:06:39Z | `git log -1 --format=%P bfe06cc`; GitHub |
| candidate ↔ merge | tree-identical: `git diff --quiet 95c061a bfe06cc` exits 0 | measured 2026-09-19 |
| PR #18 candidate CI | `python-compat` `35335399143` (`push`) and `35335402205` (`pull_request`), both `success` | `gh run list --commit 95c061a…` |
| post-merge `main` CI | `python-compat` `35342958323`, `push`, head `bfe06cc…`, `success`; jobs `py3.13` `success`, `py3.14` `success` | `gh run view 35342958323` |
| PR #18 gates | IC `GREEN`, R2G `GREEN` (comment `16081`, `AD-008`); R4M `GREEN — READY FOR MERGE` (comment `16082`, `AD-009`), for exact head `95c061a…` only; merge receipt comment `16083` | Jira `PXAPI-19` |
| historical 19.B merge | PR #16, candidate `7e5d67e…`, merge `fe8d838…` — no longer `main` | `docs/context/project-state.md` |
| historical PR #16 `R4M` | `UNKNOWN — HISTORICAL GOVERNANCE EXCEPTION`, **permanently**; never reconstructed, never `GREEN` | Jira comment `16044`; `C-PXAPI-008`; `D-PXAPI19-PO-008` |

PR #18's own `R4M` applies to PR #18 alone. It neither alters nor substitutes for the historical
PR #16 gate, which stays `UNKNOWN`.

## 2. Authority chain

| Authority | Date | What it decided |
| --- | --- | --- |
| Jira `PXAPI-19` comment `16044` | 2026-09-17 | historical PR #16 `R4M = UNKNOWN`, permanently (AD-005) |
| Jira `PXAPI-19` comment `16045` | 2026-09-17 | 19.B IC `NOT_GREEN — REPAIR REQUIRED` and R2G `NOT_GREEN` on `fe8d838` — historical, answered by PR #18 |
| Jira `PXAPI-19` comment `16081` (`AD-008`) | 2026-09-18 | `C-PXAPI-013`/`014` closed, `015` superseded as implementation defect, `016` non-material; PR #18 IC and R2G `GREEN` |
| Jira `PXAPI-19` comment `16082` (`AD-009`) | 2026-09-18 | PR #18 exact-head `R4M` `GREEN` |
| Jira `PXAPI-19` comment `16083` | 2026-09-18 | PR #18 merge receipt; AC8 still open at that time |
| Product Owner closeout disposition | 2026-09-19 | AC8 accepted with evidence ceiling (`C-PXAPI-009`, `D-PXAPI19-PO-011`); `C-PXAPI-010` resolved by documentation authority (`D-PXAPI19-PO-012`); `C-PXAPI-011` resolved with the historical overstatement preserved; F-1 … F-3 non-blocking (F-1 as new `C-PXAPI-017`); the three-condition `PXAPI-20` unlock rule of §7. It keeps `C-PXAPI-008` as comment `16044` decided it (historical PR #16 `R4M = UNKNOWN`, permanently) and restates the `C-PXAPI-013` … `016` dispositions that comment `16081` had already made; `C-PXAPI-012` is not touched. **Issued as the brief for this closeout PR and not yet recorded in Jira** — recording and reading it back in Jira is one of the `PXAPI-20` unlock conditions (§7). |

## 3. Final AC1–AC9 evidence matrix

Requirement text is abridged from the Jira `PXAPI-19` description. **EVIDENCED** means: the named
committed evidence exists at `bfe06cc` and the full suite that contains it passed in post-merge CI
run `35342958323` on Python 3.13 and 3.14. Test paths are relative to `tests/`; `semantics` is
`acquisition/test_acquisition_contract_semantics.py`. "Live" refers to the two accepted AC8
executions of §4.

| AC | Requirement | Evidence at `bfe06cc` | Class | Status |
| --- | --- | --- | --- | --- |
| AC1 | same frozen input + same method/contract version → same `site-inventory.v1` and `sampling-manifest.v1` | `application/test_discover_site.py::test_the_same_frozen_input_in_any_order_yields_the_same_documents`; `domain/test_acquisition_digests.py::test_the_producer_reproduces_every_registered_inventory_digest`. Live: runs A and B have identical inventory `input_digest` and `output_digest`, identical candidates, identical selections and an identical manifest `output_digest`. The manifest `input_digest` differs only through `inventory_ref`, which is provenance binding, not nondeterminism (`C-PXAPI-010`) | test + real-boundary observation | EVIDENCED |
| AC2 | no provider decides which pages become score- or diagnosis-relevant | `semantics::test_no_declared_member_lets_a_provider_own_page_selection`, `semantics::test_no_selection_vocabulary_token_names_a_provider_or_a_threshold`; `architecture/test_provider_neutrality.py::test_no_module_imports_a_crawler_or_browser_provider` with its planted-import canary; selection is made by the PXAPI planner `CENSUS_FIRST_DETERMINISTIC` | test | EVIDENCED |
| AC3 | `CENSUS` vs `STRATIFIED_SAMPLE` explicit and versioned; `CENSUS`-only while the threshold is `MISSING` | `domain/test_sampling_policy.py::test_the_policy_module_can_name_no_sampling_mode_but_census`; producer rule `census_never_emits_a_sample` (`src/pxapi/domain/acquisition_semantics.py`); `semantics::test_no_numeric_threshold_is_declared_by_either_contract`; `adapters/test_discover_cli.py::test_the_production_default_selects_a_full_census_and_declares_no_page_ceiling`. Live: `mode = CENSUS`, policy `CENSUS_FIRST_DETERMINISTIC 1.0.0`. The threshold stays `MISSING` (AD-004, `C-PXAPI-005`) | test + real-boundary observation | EVIDENCED |
| AC4 | every selected page has Page-Type/Stratum, selection reason and stable reference | `semantics::test_a_selected_page_without_a_stratum_is_refused`, `semantics::test_every_selection_of_every_registered_manifest_carries_a_stratum`, `semantics::test_each_declared_selection_reason_is_representable`. Live: all 506 selections of each run carry a non-empty `stratum`, `selection_reason`, `selection_rank` and `url_key` | test + contract + real-boundary observation | EVIDENCED |
| AC5 | every technically excluded page has a neutral exclusion reason; no website finding, no score penalty | `semantics::test_an_excluded_candidate_must_name_its_technical_reason`, `semantics::test_an_exclusion_reason_outside_the_closed_vocabulary_is_refused`, `semantics::test_no_neutral_technical_condition_can_be_given_a_verdict`, `semantics::test_duplication_is_not_an_exclusion_reason_anywhere_in_either_contract`. Live: zero exclusions and zero finding / score / severity keys — so the live runs exercised **no** exclusion; the exclusion semantics rest on the tests | test + contract | EVIDENCED |
| AC6 | missing or faulty sitemap, duplicate URLs, unclassifiable pages and discovery limits are technical states, not website defects | `adapters/test_site_discovery_adapter.py::test_a_missing_sitemap_is_absent`, `::test_a_document_that_is_not_a_sitemap_is_malformed`, `::test_a_seed_that_is_not_a_readable_page_still_establishes_the_origin`, `::test_robots_declaring_only_malformed_sitemaps_is_malformed_not_a_missing_declaration`; `adapters/test_html_links.py::test_a_malformed_href_never_discards_its_valid_siblings`; `semantics::test_an_unclassified_candidate_is_valid_and_says_nothing_about_the_page`; duplicates aggregate provenance (`D-PXAPI19-PO-007`). The four post-merge findings are dispositioned (§5). Live: `SITEMAP = BUDGET_EXHAUSTED` at the declared 500-entry bound, reported as a source outcome and nothing else | test + real-boundary observation | EVIDENCED |
| AC7 | contract examples and targeted invalid fixtures cover version, IDs, duplicate / ordering / reason semantics and forbidden polarity fields | `contracts/test_examples_valid.py`, `contracts/test_invalid_fixtures.py`, `acquisition/test_semantic_keys.py`; 19.A evidence `docs/evidence/PXAPI-19A-site-inventory-and-sampling-manifest.md` (19.A `CLOSED / VERIFIED`). `git diff --stat 926c241 bfe06cc -- contracts/` is empty: no contract changed after 19.A | test + contract | EVIDENCED |
| AC8 | at least one controlled Real-Boundary smoke on a public website; no full-crawl or production-scale claim | §4; `docs/evidence/PXAPI-19-AC8-real-boundary-receipt.json` | real-boundary observation, accepted by the Product Owner | **ACCEPTED WITH EVIDENCE CEILING** |
| AC9 | `selection_complete` mandatory; `false` means a runtime / safety / budget limit, stays neutral and is structurally traceable | `semantics::test_an_incomplete_selection_without_a_technical_cause_is_refused`, `semantics::test_a_complete_selection_may_not_claim_an_incompleteness_cause`, `semantics::test_selection_complete_is_neutral_in_both_values`; `application/test_discover_site.py::test_the_producer_regenerates_the_registered_bounded_census`. Live: `selection_complete = true` with no `incompleteness`, although a discovery source reached its bound — the selection over the inventory is complete; the inventory is not a claim of complete site coverage (`D-PXAPI19-PO-002`) | test + contract + real-boundary observation | EVIDENCED |

## 4. AC8 — evidence class and ceiling

**Accepted execution.** An attached clean `main` checkout at exactly `bfe06cc…`, target
`https://www.rfc-editor.org/`, 2026-09-18:

| Run | Interpreter | Smoke (`PXAPI_REAL_BOUNDARY_SMOKE_URL` set) | Opt-in canary (unset) | CLI | Envelope SHA-256 |
| --- | --- | --- | --- | --- | --- |
| A | CPython 3.13.3 | rc 0, `1 passed` | rc 0, `1 skipped` | rc 0, stderr 0 bytes | `404c4fda…c814476` |
| B | CPython 3.14.6 | rc 0, `1 passed` | rc 0, `1 skipped` | rc 0, stderr 0 bytes | `1c288afa…31186ee` |

Observed in both runs: run `SUCCEEDED`; canonical origin `https://www.rfc-editor.org/` established;
506 candidates, all `ELIGIBLE`; sources `CANONICAL_SEED USED 1`, `ROBOTS_DECLARATION USED 0`,
`SAME_ORIGIN_PAGE_LINKS USED 19`, `SITEMAP BUDGET_EXHAUSTED 500`; `CENSUS`, 506 selections,
`selection_complete = true`, no `budgets`, no `incompleteness`, no exclusions; zero finding, score
or severity keys; zero schema violations across all six documents of each envelope, and zero
semantic and producer violations for its site inventory and sampling manifest, the only two
contracts that carry such rules.

**Evidence classes, kept apart.**

- **Real-boundary observation.** The two executions above crossed a real public origin through the
  shipped composition.
- **Test assertion.** `tests/smoke/test_real_boundary_smoke.py` asserts the selection-side
  invariants on every run. It does **not** assert `SITEMAP = BUDGET_EXHAUSTED`: that is an
  observation from the envelopes, not a tested property (`C-PXAPI-011`).
- **Derived receipt.** `docs/evidence/PXAPI-19-AC8-real-boundary-receipt.json` draws on two kinds
  of source, both read on 2026-09-19. Contract, digest, inventory and manifest values were
  re-computed from the two captured envelopes with the repository's own validators
  (`ContractRegistry.validate`, the semantic and producer checks, the digest functions) at `bfe06cc`.
  Exit codes, pytest summaries — including the smoke pass — time windows and checkout state were read
  from the run driver's per-run log files, which an envelope cannot carry. Every value was re-derived
  rather than copied from an earlier receipt. Neither the envelopes nor the logs are committed; the
  envelopes are derived data, not raw site bodies, but at about 237 KB each they are left out
  deliberately, so the receipt is the durable record. **Retention caveat:** the envelopes, the
  per-run logs and the run driver were session-scratchpad artifacts on the evidence workstation;
  they are not in the repository and their retention is not guaranteed. The recorded envelope and
  log hashes can be checked only against a retained copy, and no retained copy is promised here —
  the same property `C-PXAPI-009`'s prior record noted for the 2026-09-11 run, now disclosed for this
  one.
- **Acceptance.** The Product Owner accepted this evidence for ticket closeout on 2026-09-19.

**Relation to the historical record.** This is a **new reproduction**. It does not upgrade the
2026-09-11 record in `docs/evidence/PXAPI-19B-site-discovery-runtime.md` section D, which keeps its
original class and stays unedited. No further public smoke was run for this closeout.

**Evidence ceiling.** This proves one controlled public-origin Discovery → SiteInventory →
SamplingManifest boundary. It does **not** prove complete site coverage, arbitrary crawling,
production scale, browser rendering, PXAPI-20, scoring quality, customer output or customer value.

## 5. Contradiction dispositions

| Row | Disposition | Authority |
| --- | --- | --- |
| `C-PXAPI-008` | `RESOLVED BY GOVERNANCE DECISION / HISTORICAL EXCEPTION PRESERVED` — status unchanged, with a dated cross-reference note appended; historical PR #16 `R4M = UNKNOWN`, permanently | Jira `16044` |
| `C-PXAPI-009` | `RESOLVED — FRESH REAL-BOUNDARY REPRODUCTION ACCEPTED` — a new reproduction, not a retroactive upgrade of the 2026-09-11 record | PO closeout disposition 2026-09-19 |
| `C-PXAPI-010` | `RESOLVED BY DOCUMENTATION AUTHORITY` — `sampling-manifest.input_digest` intentionally binds the concrete upstream `inventory_ref`; `contracts/README.md` wording corrected; **no code change**, pinning test preserved | PO closeout disposition 2026-09-19 |
| `C-PXAPI-011` | `RESOLVED / HISTORICAL EVIDENCE OVERSTATEMENT PRESERVED` — the smoke tests the selection side; the discovery-side `BUDGET_EXHAUSTED` is a separate observation; the historical documents stay unedited | PO closeout disposition 2026-09-19 |
| `C-PXAPI-013` | `CLOSED — repaired by PR #18` (with NF-5 in `_robots()`) | Jira `16081`, `16082` |
| `C-PXAPI-014` | `CLOSED — repaired by PR #18` | Jira `16081`, `16082` |
| `C-PXAPI-015` | `SUPERSEDED AS IMPLEMENTATION DEFECT` — the accepted canonical-seed semantics are preserved | Jira `16081` |
| `C-PXAPI-016` | `NON_MATERIAL AS IMPLEMENTATION DEFECT` under the currently authoritative named-limit definitions | Jira `16081` |
| `C-PXAPI-017` | **new**, `OPEN / NON-BLOCKING FOLLOW-UP CANDIDATE — NOT A PXAPI-19 ACCEPTANCE BLOCKER` — F-1 of §8 | PO closeout disposition 2026-09-19 |

Each changed row keeps its prior status and original record in
`docs/context/contradiction-ledger.md`; nothing was deleted. In `docs/context/decision-ledger.md`,
`D-PXAPI19-PO-008` indexes comment `16044`, `-009` and `-010` index comments `16081` and `16082`
(the `C-PXAPI-013` … `016` dispositions and PR #18's gates), `-011` indexes the AC8 acceptance
(`C-PXAPI-009`) and `-012` the `C-PXAPI-010` ruling. Two 2026-09-19 dispositions have no decision row of
their own: the `C-PXAPI-011` resolution is recorded in the contradiction ledger and here, and the
non-blocking classification of F-1 … F-3 (`C-PXAPI-017`) in the contradiction ledger,
`docs/context/project-state.md` and here.

## 6. What this closeout changes

| File | Change |
| --- | --- |
| `docs/context/project-state.md` | current state reconciled to `bfe06cc`; 19.B `NOT_GREEN` verdicts relabelled historical; AD-006 and AD-007 resolved with prior state quoted; AD-008 / AD-009 added; PXAPI-20 unlock conditions with their authority; follow-ups, with NF-3 / NF-4 status; heading "Active anti-drift findings" renamed "Anti-drift findings"; the 19.A-closeout sentence about the Jira state restated in the past tense. In AD-005: a pointer to `D-PXAPI19-PO-008` added to its decision-authority line, a dated cross-reference note appended to "What it no longer is", and one pre-existing measurement sentence corrected — it said a `git grep` for the PR #16 candidate SHA "remains" at 0 files, which stopped being true once the ledgers and the repair evidence began citing that SHA (3 citing files at `bfe06cc`, none an `R4M` artifact) |
| `docs/context/decision-ledger.md` | `D-PXAPI19-PO-008` … `-012` added, and the paragraph indexing them; `D-PXAPI19-PO-004`'s evidence-boundary cell updated with its prior wording quoted verbatim; the older index paragraph scoped to `-001` … `-007` |
| `docs/context/contradiction-ledger.md` | `C-PXAPI-009` … `011` and `013` … `016` resolved with prior state preserved; `C-PXAPI-017` added; `C-PXAPI-008` status unchanged, with a dated cross-reference note appended; the paragraph after the `013` … `016` rows restated in the past tense, with its prior wording quoted verbatim |
| `contracts/README.md` | `C-PXAPI-010` wording correction in *The digest topology*; no schema, example or rule changed |
| `docs/evidence/PXAPI-19-final-closeout.md` | this document |
| `docs/evidence/PXAPI-19-AC8-real-boundary-receipt.json` | the AC8 receipt |

**Deliberately unchanged:** `src/`, `tests/`, `contracts/v1/`, `pyproject.toml`, `uv.lock`,
`.github/`, and the historical evidence documents `PXAPI-19A-…`, `PXAPI-19B-site-discovery-runtime.md`
and `PXAPI-19B-discovery-correctness-repair.md`. Supersession is recorded in the ledgers and here,
not by editing those documents. Jira and Confluence were read and not written.

## 7. PXAPI-20

**`PXAPI-20` is still not authorized.** Authority: the Product Owner's 2026-09-19 closeout
disposition (not yet recorded in Jira). It is consistent with Jira comments `16044`, `16045`,
`16081` and `16083`, each of which states that `PXAPI-20` stays blocked; comment `16082`, the PR #18
`R4M` gate, does not address it. It stays `BLOCKED / NOT AUTHORIZED` until all three hold, in order:

1. this closeout PR is merged;
2. post-merge `main` CI succeeds on that exact merge SHA;
3. the PXAPI-19 closeout is recorded in Jira and read back.

This PR satisfies none of the three by being opened.

## 8. Non-blocking follow-up candidates

Surfaced by the final AC8 verification. They are **not** part of PXAPI-19 acceptance, nothing is
repaired here, and each needs its own authorised ticket.

| ID | Finding | Evidence, re-measured 2026-09-19 |
| --- | --- | --- |
| F-1 | Terminal `analysis_run_state.entered_at` is the run's start instant, while the contract describes it as when the run entered its current state (`C-PXAPI-017`). | `discover_site.py` lines 229-230 and 390-391, `analyze_homepage.py` lines 221-225 and 378 pass `started` as `entered_at`; envelope A: `SUCCEEDED`, `entered_at 21:51:55Z`, `finished_at 21:51:57Z`; no test pins terminal `entered_at` |
| F-2 | Local CPython trust-store configuration can depend on `SSL_CERT_FILE`; a misconfigured environment surfaces as a provider failure. | python.org CPython 3.13.3 on the evidence workstation: compiled-in CA file absent, 0 CA anchors without `SSL_CERT_FILE`, 193 with it; the fetcher uses `ssl.create_default_context()`. Run A can only have succeeded through an inherited `SSL_CERT_FILE`, which the run did not record — an inference from these measurements, not a recorded fact. |
| F-3 | The neutrality helper is primarily key-name based; stronger value-level anti-verdict testing is a future hardening candidate. | `verdict_keys_in` in `tests/application/test_discover_site.py`, also used by the smoke, intersects key names with `VERDICT_KEYS` and never inspects values |

Other residues stay recorded where they were raised and are unchanged here: NF-1, NF-2, NF-6 and the
`CANONICALISATION_VERSION` judgement (`PXAPI-19B-discovery-correctness-repair.md`), the untriaged
unguarded `urljoin` at `analyze_homepage.py:478`, `C-PXAPI-012`, and the `MISSING` sampling
threshold (`C-PXAPI-005`). The repair document also names `page_fetcher.py:168` as unguarded; re-read
at `bfe06cc`, that call sits inside `try: … except ValueError` and returns `INVALID_REDIRECT`, so it
is not a residue. The repair document is left unedited and this record corrects it.

Of the other findings in the repair document, NF-4 (`project-state.md` still naming `fe8d838` as
current `main`) is resolved by this closeout's `project-state.md` reconcile, and NF-3 (sitemap
declarations canonicalised twice) is informational and not a defect.

**Observed while editing, not changed:** `contracts/README.md` still describes the acquisition
contracts as 19.A left them in several places — the introduction of *Site inventory and sampling
manifest* ("registers **no producer for either**"), *The digest topology* (the reference
implementation is test code "because PXAPI-19.A ships no producer"), and the closing paragraph of
*Semantic keys, and why the digest fails closed* ("this layer is test code and no `src/pxapi` module
is added for it"; "Equivalent producer-side enforcement is mandatory in PXAPI-19.B"). 19.B delivered
the producer-side digests and semantic enforcement in `src/pxapi/domain/acquisition_digests.py` and
`src/pxapi/domain/acquisition_semantics.py`. These passages were true of 19.A and sit outside the
`C-PXAPI-010` correction this closeout was authorized to make.

## 9. Evidence ceiling of this document

1. **No gate declaration.** Ticket-level IC / R2G / R4M and Jira Done are not declared.
2. **No new real-boundary run.** §4 re-derives recorded envelopes; no public site was contacted for
   this closeout.
3. **The 2026-09-19 Product Owner disposition is not yet in Jira.** It exists as the brief for
   this PR. Everything that rests on it therefore still needs its Jira record and readback: the AC8
   acceptance (`C-PXAPI-009`, `D-PXAPI19-PO-011`), the `C-PXAPI-010` ruling (`D-PXAPI19-PO-012`), the
   `C-PXAPI-011` resolution, the non-blocking classification of F-1 … F-3 (`C-PXAPI-017`), the
   reaffirmation of `C-PXAPI-008`, and the three-condition `PXAPI-20` unlock rule of §7.
4. **CI is not runtime.** The matrix's EVIDENCED means committed evidence passed in CI. It is not a
   production, scale or customer-value claim.
5. **A commit cannot record its own identity.** This closeout's commit and merge SHAs are stated on
   its PR, not here.
