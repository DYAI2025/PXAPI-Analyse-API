# PXAPI Project State

**Snapshot date:** 2026-09-17  
**Execution mode:** PXAPI-19 ticket-level closeout reconcile; 19.A and 19.B are both merged  
**Repository:** `DYAI2025/PXAPI-Analyse-API`  
**19.A integrated implementation baseline:** `926c2415503f27084ab314629548b2e79ddce8a9`  
**19.B integrated implementation baseline / current `main`:** `fe8d838023c8f9967151cad9aa1981e76dcf7d75`

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

At current `main` `fe8d838023c8f9967151cad9aa1981e76dcf7d75`, the PXAPI-19.B site-discovery runtime **is present**. `SiteDiscoveryPort`, `HttpSiteDiscovery`, the `DiscoverSite` use case, the deterministic `CENSUS_FIRST_DETERMINISTIC` planner, producer-side semantic enforcement and `python -m pxapi.adapters.inbound.discover_cli` are all on `main`, authorized by the twelve `PXAPI-19.B` entries in `BEHAVIOR_ALLOWED` (`tests/test_package_scaffold.py`).

Acquisition is therefore no longer homepage-only at the discovery layer: one run establishes a canonical public origin, reads `/robots.txt` for `Sitemap:` declarations only, reads sitemaps and bounded same-origin seed links, canonicalizes and deduplicates them into a `site-inventory.v1`, and plans a `sampling-manifest.v1` in `CENSUS` mode. **No discovered page is fetched** — page acquisition over the manifest is PXAPI-20 and is not implemented.

PXAPI-19.A had added the provider-neutral contract/foundation layer for that step, including registered `site-inventory.v1` and `sampling-manifest.v1` schemas, shared acquisition definitions, valid examples, targeted invalid fixtures, deterministic digest/semantic guards and contract evidence. 19.A intentionally introduced no runtime; 19.B is what made those contracts executable.

Still **not** present at `fe8d838`: browser/Crawl4AI execution, `RenderedPagePort`, multi-page static acquisition, `page-acquisition-record.v1`, scoring/customer output changes, queueing, CRM integration and deployment behavior. No customer-value claim follows from the 19.B merge.

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

Overall Jira item `PXAPI-19` remains incomplete and `In Arbeit` until 19.B satisfies the remaining runtime and Real-Boundary acceptance criteria.

## PXAPI-19.B closeout

**Bounded 19.B state:** `MERGED / CLOSEOUT OPEN`

- PR head/candidate: `7e5d67eb95f85216eff32d99ff82227cb5786efc`
- PR: `#16`, merged 2026-09-11T23:54:09Z
- bound base: `468ce6f187efcd108a930bf977858a3790e4bc52`
- merge / integrated implementation baseline: `fe8d838023c8f9967151cad9aa1981e76dcf7d75`
- candidate CI: `python-compat` run `34653734998` (`push`) and `34653738494` (`pull_request`), both exact head `7e5d67eb95f85216eff32d99ff82227cb5786efc`, both `success`, Python 3.13 and 3.14 jobs `success`
- post-merge main CI: `python-compat` run `34659764590`, exact head `fe8d838023c8f9967151cad9aa1981e76dcf7d75`, `success`
- `git diff fd3ad8a..7e5d67e -- src/ tests/ contracts/` is **0 bytes**, so the gate results measured on `fd3ad8a` carry to the merged head for code, lint and tests
- 19.B IC: `GREEN` — the authorized 19.B scope is implemented and present on `main`
- 19.B R2G: `GREEN` on the exact candidate, bounded by the gates this repository actually runs (see below)
- 19.B R4M: `UNKNOWN — HISTORICAL GOVERNANCE EXCEPTION`. Never independently evidenced, and **never to be recorded as `GREEN`**. Decision authority: Jira `PXAPI-19` comment `16044` (2026-09-17). See AD-005.

**What R2G covers here.** `.github/workflows/python-compat.yml` is the only workflow. It runs `uv sync --locked`, `uv lock --check`, `ruff check`, `ruff format --check` and `uv run pytest` on Python 3.13 and 3.14. Contract validation runs inside that suite. The workflow's own header records that repository-wide security, secret and dependency-security scanning are deliberately **not** implemented here and belong to A8. `main` carries no branch protection, so no review was required to merge.

Overall Jira item `PXAPI-19` remains `In Arbeit`. What is open is ticket-level closeout, not implementation: see AD-006. AD-005 is no longer an open evidence search — it is a decided and preserved historical governance exception.

## Completed prerequisite

`PXAPI-4` — Skill Capability Baseline & Parity Gap Contract — is **Erledigt** as of 2026-09-10 for its discovery/contract scope.

Accepted source-bound baseline:

- Confluence page `54362137` — `PXAPI — Skill V2.1 Capability Baseline & Parity Gap Matrix — 2026-09-10`;
- Skill artifact `pixelkiez-website-diagnosis_V2.1.zip`;
- Skill ZIP SHA-256 `ab8bba6d1bbd23179b7a9761767971def54986a8e398da38919ea37c23ebb060`;
- Skill package artifact digest `959ea94775c147ca3d6c197a4cc62f4e603557b53ec6bf8ca236a67ffabee13b`.

This completion proves the source-bound parity/gap decision artifact, not implementation parity.

## Current prioritized delivery sequence

1. `PXAPI-19` ticket-level closeout. 19.A and 19.B are both merged; the remaining work is evidence-bound closeout and anti-drift reconcile, not implementation. The open item is AD-006 (AC8 real-boundary evidence class). AD-005 is **decided, not open**: the historical 19.B `R4M` stays `UNKNOWN` as a preserved governance exception per Jira `PXAPI-19` comment `16044`, so it is no longer a closeout blocker and no longer an evidence search. No mutating implementation theme is currently authorized, so the `WIP=1` slot is free but unclaimed.
2. `PXAPI-20` — Multi-Page Static Acquisition & Canonical Evidence Population v1, only after PXAPI-19 receives its ticket-level closeout/readback. Merging 19.B did **not** release it, and neither does deciding AD-005: a governance exception resolves a historical gate state, it authorises nothing. See AD-006 for what is still open, and Jira `PXAPI-19` comment `16044`, which keeps `PXAPI-20` blocked in the same breath as it decides AD-005.
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

Out of scope for 19.B, and verified absent on `fe8d838`: browser/Crawl4AI, PXAPI-20 multi-page static acquisition pipeline, scoring/PDF/customer projection, PostgreSQL queue/worker, CRM/buyer-intent and deployment changes. `pyproject.toml`, `uv.lock`, `.github/` and `contracts/` are each a **0-byte** diff against the base, so 19.B added no dependency, changed no CI and changed no contract.

## Active anti-drift findings

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

**Decision authority:** Jira `PXAPI-19` comment `16044`, 2026-09-17 — *"AD-005 — Historical R4M decision / closeout governance"*.

What was measured, and remains true on this tree: the merge commit `fe8d838` states that PR #16 was merged "after exact-head R4M", and no artifact independently supporting that statement exists. `git grep -l '7e5d67eb95f85216eff32d99ff82227cb5786efc' HEAD` returns **0** tracked files, and `grep -c '7e5d67e' docs/evidence/PXAPI-19B-site-discovery-runtime.md` returns **0**. The 19.B evidence document explicitly declines to declare one ("`R4M` is not declared here"; "**MISSING:** an independent `R4M`"), and the candidate's own tip commit message says the same. The only GitHub review on PR #16 is from `sourcery-ai[bot]`, state `COMMENTED`, aborting the review because the diff exceeds its 150,000-character limit; there are zero issue comments and zero review comments. `main` carries no branch protection, so nothing required a review.

**What the Product Owner decided.** Of the two lawful paths this finding originally offered, the second was taken: PR #16 merged **without** independently evidenced exact-head R4M, and that is recorded rather than repaired. The merge is a fact; the missing evidence may be neither reconstructed nor marked passed. The gap is preserved as a governance deviation, not closed by producing something that does not exist. **No retrospective approval has been or may be manufactured.**

**What this is not.** It is not a new implementation defect, and it is not evidence against any PXAPI-19 acceptance criterion. It does bar any claim that the original 19.B merge process was fully DRS-conformant, and that bar is permanent.

**What it no longer is.** A current closeout blocker. AD-005 does not gate PXAPI-19's ticket-level closeout any more, and deciding it authorises nothing: `PXAPI-20` stays blocked, and AD-006 is untouched and still open. See `C-PXAPI-008`.

### AD-006 — AC8 real-boundary evidence class

The controlled public Real-Boundary-Smoke required by PXAPI-19 AC8 exists in this repository in two forms, and they are not the same thing. The **mechanism** is committed and executable: `tests/smoke/test_real_boundary_smoke.py` drives the shipped composition against a real public origin and is opt-in through `PXAPI_REAL_BOUNDARY_SMOKE_URL`, so it is skipped in CI. The **execution record** of the runs against `www.rfc-editor.org` and `example.com` is prose in `docs/evidence/PXAPI-19B-site-discovery-runtime.md` section D; no machine-readable capture accompanies it (`git ls-files docs/` matches **0** `.json`/`.txt`/`.log`/`.csv` files), and the document states its run driver is scratchpad tooling outside the repository.

Status: `OPEN / EVIDENCE CLASS`. The prose record is `DOC_PERSISTED`, not independently verified by any committed artifact. Re-deriving it requires outbound network access. See `C-PXAPI-009`.

## Current Jira focus

- `PXAPI-4` — **Erledigt**, discovery/contract scope accepted.
- `PXAPI-19` — **In Arbeit**, closeout-only. 19.A is bounded `CLOSED / VERIFIED`; 19.B is merged (`MERGED / CLOSEOUT OPEN`) with its historical `R4M` decided `UNKNOWN` per AD-005. The remaining work is ticket-level closeout, open on AD-006 alone.
- `PXAPI-20` — `NEXT / NOT AUTHORIZED` until PXAPI-19 receives its ticket-level closeout/readback. The 19.B merge alone does not release it.

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
