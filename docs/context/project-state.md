# PXAPI Project State

**Snapshot date:** 2026-09-19  
**Execution mode:** PXAPI-19 final evidence and documentation closeout — documentation only. `WIP=1` is this closeout theme; no mutating implementation theme is active, and `PXAPI-20` is not authorized.  
**Repository:** `DYAI2025/PXAPI-Analyse-API`  
**19.A integrated implementation baseline:** `926c2415503f27084ab314629548b2e79ddce8a9`  
**19.B integrated implementation baseline (historical; no longer `main`):** `fe8d838023c8f9967151cad9aa1981e76dcf7d75`  
**Current implementation baseline:** `bfe06cc07ea0dfde31fedb8e7115940da24fb9fd` — the merge of PR #18 (discovery-correctness repair), and `main` when this snapshot was written. The closeout PR that carries this file changes documentation only: once it merges, `main` advances to that merge while the implementation baseline stays `bfe06cc`.

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

At the current implementation baseline `bfe06cc07ea0dfde31fedb8e7115940da24fb9fd`, the PXAPI-19.B site-discovery runtime **is present**, including the PR #18 discovery-correctness repair. `SiteDiscoveryPort`, `HttpSiteDiscovery`, the `DiscoverSite` use case, the deterministic `CENSUS_FIRST_DETERMINISTIC` planner, producer-side semantic enforcement and `python -m pxapi.adapters.inbound.discover_cli` are all on `main`, authorized by the twelve `PXAPI-19.B` entries in `BEHAVIOR_ALLOWED` (`tests/test_package_scaffold.py`).

Acquisition is therefore no longer homepage-only at the discovery layer: one run establishes a canonical public origin, reads `/robots.txt` for `Sitemap:` declarations only, reads sitemaps and bounded same-origin seed links, canonicalizes and deduplicates them into a `site-inventory.v1`, and plans a `sampling-manifest.v1` in `CENSUS` mode. **No discovered page is fetched** — page acquisition over the manifest is PXAPI-20 and is not implemented.

**The defects found after the 19.B merge are dispositioned.** A post-merge review had found four defect classes inside the authorized boundary (AD-007, `C-PXAPI-013` … `C-PXAPI-016`). PR #18 repaired the two that were implementation defects — malformed-link isolation, together with the same defect class in `robots.txt` declaration reading (NF-5), and fragment canonicalization — and Jira `PXAPI-19` comment `16081` ruled the canonical-seed finding superseded as an implementation defect and the named-limit finding non-material. Residues that were recorded but do not block PXAPI-19 are listed under *Non-blocking follow-up candidates* below. The discovery layer still makes **no** completeness claim about a real site beyond what one inventory records: the accepted Real-Boundary evidence proves one controlled public-origin boundary (AD-006).

PXAPI-19.A had added the provider-neutral contract/foundation layer for that step, including registered `site-inventory.v1` and `sampling-manifest.v1` schemas, shared acquisition definitions, valid examples, targeted invalid fixtures, deterministic digest/semantic guards and contract evidence. 19.A intentionally introduced no runtime; 19.B is what made those contracts executable.

Still **not** present at `bfe06cc`: browser/Crawl4AI execution, `RenderedPagePort`, multi-page static acquisition, `page-acquisition-record.v1`, scoring/customer output changes, queueing, CRM integration and deployment behavior. No customer-value claim follows from the 19.B merge, from its repair, or from this closeout.

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

**Jira state at snapshot:** `In Arbeit` (read 2026-09-19). Jira Done is a Product Owner action in Jira and is **not** claimed by this repository.

**Evidence state.** The final AC1–AC9 evidence matrix, the AC8 evidence class and ceiling, and the contradiction dispositions are in `docs/evidence/PXAPI-19-final-closeout.md`; the machine-readable AC8 receipt is `docs/evidence/PXAPI-19-AC8-real-boundary-receipt.json`. AC8 is accepted **with its explicit evidence ceiling** (AD-006, `D-PXAPI19-PO-011`).

**Gates.** The historical PR #16 `R4M` stays `UNKNOWN`, permanently. PR #18's gates apply to `95c061a…` only. Ticket-level PXAPI-19 IC / R2G / R4M are Orchestrator and Product Owner authority and are not declared by this file. The closeout PR that carries this file changes documentation only.

**PXAPI-20 stays `BLOCKED / NOT AUTHORIZED` until all three of these hold, in order** (authority: Product Owner closeout disposition, 2026-09-19, not yet recorded in Jira):

1. the PXAPI-19 closeout PR is merged;
2. post-merge `main` CI succeeds on that exact merge SHA;
3. the PXAPI-19 closeout is recorded in Jira and read back.

## Completed prerequisite

`PXAPI-4` — Skill Capability Baseline & Parity Gap Contract — is **Erledigt** as of 2026-09-10 for its discovery/contract scope.

Accepted source-bound baseline:

- Confluence page `54362137` — `PXAPI — Skill V2.1 Capability Baseline & Parity Gap Matrix — 2026-09-10`;
- Skill artifact `pixelkiez-website-diagnosis_V2.1.zip`;
- Skill ZIP SHA-256 `ab8bba6d1bbd23179b7a9761767971def54986a8e398da38919ea37c23ebb060`;
- Skill package artifact digest `959ea94775c147ca3d6c197a4cc62f4e603557b53ec6bf8ca236a67ffabee13b`.

This completion proves the source-bound parity/gap decision artifact, not implementation parity.

## Current prioritized delivery sequence

1. **`PXAPI-19` final evidence and documentation closeout** — the current and only `WIP=1` theme. A documentation-only PR; it opens no implementation scope. After it merges: post-merge `main` CI on the merge SHA, then the Jira closeout and its readback, which are Product Owner actions. The discovery-correctness repair that preceded it is done (PR #18).
2. `PXAPI-20` — Multi-Page Static Acquisition & Canonical Evidence Population v1, only after the three unlock conditions under *PXAPI-19 ticket-level closeout*. Merging 19.B did not release it; deciding AD-005 did not release it; the PR #18 repair did not release it; and this closeout PR alone does not release it. Jira `PXAPI-19` comments `16044`, `16045`, `16081` and `16083` each state that it stays blocked; comment `16082`, the PR #18 `R4M` gate, does not address it.
3. Re-measure evidence gain before paying browser/async complexity.
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

Status: `CONFLICT / OPEN / NON-BLOCKING FOR PXAPI-19 CLOSEOUT`. Do not mutate, reverse or delete these links until the current link semantics and a safe reversible operation are independently verified. Do not infer PXAPI-20 authorization from the link representation.

### AD-004 — sampling threshold remains missing

The census-to-stratified-sampling threshold remains `MISSING`. No numeric threshold may be invented in 19.B. Executable policy remains `CENSUS`-only until representative benchmark evidence and an explicit versioned decision exist.

### AD-005 — the 19.B candidate merged without an independent exact-head R4M

**Status: `DECIDED / HISTORICAL GOVERNANCE EXCEPTION — PRESERVED`. Not an open evidence search.**

**Historical gate state: `R4M = UNKNOWN`.** Permanently. It is **never** to be reconstructed, inferred or retroactively recorded as `GREEN`.

**Decision authority:** Jira `PXAPI-19` comment `16044`, 2026-09-17 — *"AD-005 — Historical R4M decision / closeout governance"*. Indexed as `D-PXAPI19-PO-008`.

What was measured: the merge commit `fe8d838` states that PR #16 was merged "after exact-head R4M", and no artifact independently supporting that statement exists. On `fe8d838`, `git grep -l '7e5d67eb95f85216eff32d99ff82227cb5786efc' HEAD` returned **0** tracked files, and `grep -c '7e5d67e' docs/evidence/PXAPI-19B-site-discovery-runtime.md` returned **0**. The second count is still 0 at `bfe06cc`. The first is not, and the reason matters: at `bfe06cc` it returns 3 files, and each only *cites* the candidate SHA: this file and `docs/context/contradiction-ledger.md` while recording this very gap, and `docs/evidence/PXAPI-19B-discovery-correctness-repair.md` as the starting `HEAD` of its repair. None is an R4M artifact, so the absence stands. The 19.B evidence document explicitly declines to declare one ("`R4M` is not declared here"; "**MISSING:** an independent `R4M`"), and the candidate's own tip commit message says the same. The only GitHub review on PR #16 is from `sourcery-ai[bot]`, state `COMMENTED`, aborting the review because the diff exceeds its 150,000-character limit; there are zero issue comments and zero review comments. `main` carries no branch protection, so nothing required a review.

**What the Product Owner decided.** Of the two lawful paths this finding originally offered, the second was taken: PR #16 merged **without** independently evidenced exact-head R4M, and that is recorded rather than repaired. The merge is a fact; the missing evidence may be neither reconstructed nor marked passed. The gap is preserved as a governance deviation, not closed by producing something that does not exist. **No retrospective approval has been or may be manufactured.**

**What this is not.** It is not a new implementation defect, and it is not evidence against any PXAPI-19 acceptance criterion. It does bar any claim that the original 19.B merge process was fully DRS-conformant, and that bar is permanent.

**What it no longer is.** A current closeout blocker. AD-005 does not gate PXAPI-19's ticket-level closeout any more, and deciding it authorises nothing: `PXAPI-20` stays blocked, and AD-006 is untouched and still open. See `C-PXAPI-008`. **2026-09-19 note:** AD-006 has since been resolved on its own authority (below), and PR #18 carried its own exact-head `R4M` (AD-009). Neither touches this finding: the historical PR #16 `R4M` stays `UNKNOWN`.

### AD-006 — AC8 real-boundary evidence class

**Status: `RESOLVED — FRESH REAL-BOUNDARY REPRODUCTION ACCEPTED`.** Authority: Product Owner closeout disposition, 2026-09-19 (`D-PXAPI19-PO-011`; not yet recorded in Jira). See `C-PXAPI-009`.

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

Surfaced by the final AC8 verification and recorded at the Product Owner's direction as **non-blocking** for PXAPI-19. None is repaired here, and each needs its own authorised ticket before any change.

- **F-1 — terminal `entered_at`.** Terminal `analysis_run_state` documents carry the run's start instant as `entered_at`, while the contract describes it as when the run entered its current state. See `C-PXAPI-017`.
- **F-2 — local trust-store dependency.** The python.org CPython 3.13.3 build on the evidence workstation has no usable compiled-in CA file; HTTPS works only through an inherited `SSL_CERT_FILE` (measured 2026-09-19: 0 CA anchors without it, 193 with it). The fetcher uses `ssl.create_default_context()`, so a misconfigured environment surfaces as a provider failure rather than as a local configuration fault. Live-smoke evidence should record `SSL_CERT_FILE`.
- **F-3 — neutrality helper is key-name based.** `verdict_keys_in` (`tests/application/test_discover_site.py`), which the Real-Boundary smoke also uses, compares **key names** against `VERDICT_KEYS`; it does not inspect values. A value-level anti-verdict test is a future hardening candidate.

Of the repair document's other findings, NF-4 (this file naming `fe8d838` as current `main`) is resolved by this reconcile, and NF-3 is informational and not a defect. Residues recorded elsewhere and unchanged by this closeout, none of them a PXAPI-19 acceptance blocker: NF-1 (no vocabulary for "origin established, seed document answered 4xx/5xx" — a contract question), NF-2 (raw ASCII-space fragment makes an observed form non-persistable — a contract boundary), NF-6 (`EMPTY` for an all-unresolvable-links document), the `CANONICALISATION_VERSION` judgement (all in `docs/evidence/PXAPI-19B-discovery-correctness-repair.md`); the untriaged unguarded `urljoin` at `src/pxapi/application/analyze_homepage.py:478` (the repair document also names `page_fetcher.py:168`, which is in fact already guarded by `except ValueError` at `bfe06cc`); `C-PXAPI-012` (credential echo on the homepage path); and `C-PXAPI-005` / AD-004 (sampling threshold `MISSING`).

## Current Jira focus

- `PXAPI-4` — **Erledigt**, discovery/contract scope accepted.
- `PXAPI-19` — **In Arbeit** (read 2026-09-19). 19.A is bounded `CLOSED / VERIFIED`; 19.B is merged and repaired by PR #18 (merge `bfe06cc`, gates `GREEN` at exact head `95c061a` per comments `16081` and `16082`); the historical PR #16 `R4M` is `UNKNOWN`, permanently (AD-005); AC8 is accepted with its evidence ceiling (AD-006). Open: this closeout PR, its post-merge CI, and the Jira closeout and readback. The issue's labels still included `repair-required` and `delivery-ready-blocked` when read on 2026-09-19; relabelling is a Jira action and is not performed by this repository change.
- `PXAPI-20` — `NEXT / BLOCKED / NOT AUTHORIZED` until the three unlock conditions under *PXAPI-19 ticket-level closeout* hold.

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
