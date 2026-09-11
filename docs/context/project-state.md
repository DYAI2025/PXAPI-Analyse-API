# PXAPI Project State

**Snapshot date:** 2026-09-11  
**Execution mode:** PXAPI-19.A governance closeout / PXAPI-19.B PRE_IMPLEMENTATION rebaseline  
**Repository:** `DYAI2025/PXAPI-Analyse-API`  
**19.A integrated implementation baseline:** `926c2415503f27084ab314629548b2e79ddce8a9`

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

At the 19.A integrated implementation baseline `926c2415503f27084ab314629548b2e79ddce8a9`, PXAPI still has no PXAPI-19.B site-discovery runtime. The existing application runtime therefore remains homepage-scoped for acquisition behavior.

PXAPI-19.A added the provider-neutral contract/foundation layer for the next acquisition step, including registered `site-inventory.v1` and `sampling-manifest.v1` schemas, shared acquisition definitions, valid examples, targeted invalid fixtures, deterministic digest/semantic guards and contract evidence.

19.A intentionally did **not** introduce SiteDiscoveryPort production, sitemap/robots/link runtime discovery, producer canonicalization/deduplication, page classification/planning runtime, Real-Boundary-Smoke, browser/Crawl4AI execution, scoring/customer output, queueing, CRM integration or deployment behavior.

No runtime or customer-value claim follows from the 19.A contract merge alone.

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

## Completed prerequisite

`PXAPI-4` — Skill Capability Baseline & Parity Gap Contract — is **Erledigt** as of 2026-09-10 for its discovery/contract scope.

Accepted source-bound baseline:

- Confluence page `54362137` — `PXAPI — Skill V2.1 Capability Baseline & Parity Gap Matrix — 2026-09-10`;
- Skill artifact `pixelkiez-website-diagnosis_V2.1.zip`;
- Skill ZIP SHA-256 `ab8bba6d1bbd23179b7a9761767971def54986a8e398da38919ea37c23ebb060`;
- Skill package artifact digest `959ea94775c147ca3d6c197a4cc62f4e603557b53ec6bf8ca236a67ffabee13b`.

This completion proves the source-bound parity/gap decision artifact, not implementation parity.

## Current prioritized delivery sequence

1. `PXAPI-19.B` — provider-neutral discovery/runtime production for the already merged 19.A contracts, including required Real-Boundary-Smoke. This is the next allowed mutating implementation theme (`WIP=1`) after this governance closeout is merged/read back and its exact new `main` SHA is bound.
2. `PXAPI-20` — Multi-Page Static Acquisition & Canonical Evidence Population v1, only after full PXAPI-19 closeout/readback including 19.B.
3. Re-measure evidence gain before paying browser/async complexity.
4. Depending on observed bottleneck, continue with either cross-page diagnosis (`PXAPI-23`) or async/browser path (`PXAPI-15..18`, then `PXAPI-21`, `PXAPI-22`).
5. Strategic lever / impact verification contracts (`PXAPI-24`) later.

The 80/20 expectation is a Product Owner hypothesis, not production-measured fact.

## PXAPI-19.B PRE_IMPLEMENTATION boundary

19.B may be bound only to the freshly re-read exact `main` after this governance closeout merges; the 19.A merge SHA above is an implementation baseline, not a permanent moving-head claim.

19.B intended scope remains bounded to:

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

Out of scope for 19.B: browser/Crawl4AI, PXAPI-20 multi-page static acquisition pipeline, scoring/PDF/customer projection, PostgreSQL queue/worker, CRM/buyer-intent and deployment changes.

## Active anti-drift findings

### AD-001 — stale legacy PR

GitHub PR #5 (`PXK-17 (A4): define Contracts v1 and the Analysis Run state machine`) remains stale legacy drift. It is not active WIP. A separate reconcile is required before any close/merge decision.

### AD-002 — repository governance context

The repository context documents exist and are maintained as rehydration aids. Their presence does not prove the project is globally drift-free; live reconciliation remains mandatory.

### AD-003 — Jira dependency-link direction conflict

Jira's raw issue-link representation for `PXAPI-19` currently exposes `PXAPI-20` and `PXAPI-21` as `inwardIssue` values under the `Blocks` link type (`is blocked by`), while the accepted product sequence and downstream Jira descriptions require full `PXAPI-19` before `PXAPI-20`. Other Jira graph rendering may present the relationship differently.

Status: `CONFLICT / OPEN / NON-BLOCKING FOR 19.B`. Do not mutate, reverse or delete these links until the current link semantics and a safe reversible operation are independently verified. Do not infer PXAPI-20 authorization from the link representation.

### AD-004 — sampling threshold remains missing

The census-to-stratified-sampling threshold remains `MISSING`. No numeric threshold may be invented in 19.B. Executable policy remains `CENSUS`-only until representative benchmark evidence and an explicit versioned decision exist.

## Current Jira focus

- `PXAPI-4` — **Erledigt**, discovery/contract scope accepted.
- `PXAPI-19` — **In Arbeit**. 19.A is bounded `CLOSED / VERIFIED`; 19.B is the next implementation slice after post-governance exact-main binding.
- `PXAPI-20` — `NEXT / NOT AUTHORIZED` until full PXAPI-19, including 19.B and Real-Boundary-Smoke, is closed/readback-verified.

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
