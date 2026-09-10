# PXAPI Project State

**Snapshot date:** 2026-09-10  
**Execution mode:** post-governance closeout / PXAPI-19 pre-implementation  
**Repository:** `DYAI2025/PXAPI-Analyse-API`  
**Reconciled base/snapshot:** `8be473456f090a56b355e3e1a9981ba216bde783`

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

At the reconciled base/snapshot above, PXAPI still analyzes one public homepage only. The governance merge added only these context documents and changed no runtime, API contract, score or acquisition behavior:

- `docs/context/project-state.md`
- `docs/context/decision-ledger.md`
- `docs/context/contradiction-ledger.md`

Current registered application contracts remain:

- `problem`
- `analysis-run-request`
- `analysis-run-state`
- `stage-execution-record`
- `measurement-record`
- `website-evidence`
- `diagnostic-finding`

No current implementation claim is made here for multi-page acquisition, Crawl4AI/browser execution, PostgreSQL queueing, scoring, customer projection or production deployment.

## Completed prerequisite

`PXAPI-4` — Skill Capability Baseline & Parity Gap Contract — is **Erledigt** as of 2026-09-10 for its discovery/contract scope.

Accepted source-bound baseline:

- Confluence page `54362137` — `PXAPI — Skill V2.1 Capability Baseline & Parity Gap Matrix — 2026-09-10`;
- Skill artifact `pixelkiez-website-diagnosis_V2.1.zip`;
- Skill ZIP SHA-256 `ab8bba6d1bbd23179b7a9761767971def54986a8e398da38919ea37c23ebb060`;
- Skill package artifact digest `959ea94775c147ca3d6c197a4cc62f4e603557b53ec6bf8ca236a67ffabee13b`.

This completion proves the source-bound parity/gap decision artifact, not implementation parity.

## Current prioritized delivery sequence

1. `PXAPI-19` — Acquisition Method, Site Inventory & Sampling Manifest v1.
2. `PXAPI-20` — Multi-Page Static Acquisition & Canonical Evidence Population v1.
3. Re-measure evidence gain before paying browser/async complexity.
4. Depending on observed bottleneck, continue with either cross-page diagnosis (`PXAPI-23`) or async/browser path (`PXAPI-15..18`, then `PXAPI-21`, `PXAPI-22`).
5. Strategic lever / impact verification contracts (`PXAPI-24`) later.

The 80/20 expectation is a Product Owner hypothesis, not production-measured fact.

## Active anti-drift findings

### AD-001 — stale legacy PR

GitHub PR #5 (`PXK-17 (A4): define Contracts v1 and the Analysis Run state machine`) remains stale legacy drift: old base, large scope and non-current delivery lineage. It is not active WIP. A separate reconcile is required before any close/merge decision.

### AD-002 — governance intake gap closed

The repository context gap is **RESOLVED** by merged PR #12, merge commit `8be473456f090a56b355e3e1a9981ba216bde783`. The presence of these documents is not proof that the project is globally drift-free; live reconciliation remains mandatory.

## Current Jira focus

- `PXAPI-4` — **Erledigt**, discovery/contract scope accepted.
- `PXAPI-19` — next planned P0 implementation slice and only candidate for active mutating WIP after PRE_IMPLEMENTATION gate.

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