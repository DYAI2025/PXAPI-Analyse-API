# PXAPI Project State

**Snapshot date:** 2026-09-10  
**Execution mode:** governance rebaseline / anti-drift intake  
**Repository:** `DYAI2025/PXAPI-Analyse-API`  
**Bound base:** `main@3a52929ad1ce8b56278344d37feaf0ce68f31289`

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

## Live code snapshot at rebaseline

Verified `main` head at snapshot creation:

`3a52929ad1ce8b56278344d37feaf0ce68f31289`

Current README explicitly states the implementation analyzes one public homepage only. Current registered contracts at that SHA are:

- `problem`
- `analysis-run-request`
- `analysis-run-state`
- `stage-execution-record`
- `measurement-record`
- `website-evidence`
- `diagnostic-finding`

No current implementation claim is made here for multi-page acquisition, Crawl4AI/browser execution, PostgreSQL queueing, scoring, customer projection or production deployment.

## Current prioritized delivery sequence

1. Verify/freeze Skill Capability Baseline and Parity Gap (`PXAPI-4`).
2. Implement Acquisition Method, Site Inventory & Sampling Manifest v1 (`PXAPI-19`) as next bounded implementation slice.
3. Implement Multi-Page Static Acquisition & Canonical Evidence Population v1 (`PXAPI-20`).
4. Re-measure evidence gain before paying browser/async complexity.
5. Depending on observed bottleneck, continue with either cross-page diagnosis (`PXAPI-23`) or async/browser path (`PXAPI-15..18`, then `PXAPI-21`, `PXAPI-22`).
6. Strategic lever / impact verification contracts (`PXAPI-24`) later.

The 80/20 expectation is a Product Owner hypothesis, not production-measured fact.

## Active anti-drift findings

### AD-001 — stale legacy PR

GitHub PR #5 (`PXK-17 (A4): define Contracts v1 and the Analysis Run state machine`) is still open from an old base SHA, has 252 changed files and is currently non-mergeable. It is treated as historical/stale delivery drift and is not the active PXAPI WIP. No merge or deletion is authorized by this snapshot.

### AD-002 — governance intake gap being closed by this branch

Before this branch, `docs/context/project-state.md` and repository Decision/Contradiction ledgers were absent on current `main`. This branch introduces those context artifacts only. Their existence is not proof that the wider project is drift-free; live reconciliation remains mandatory.

## Current Jira focus

- `PXAPI-4` — Skill Capability Baseline & Parity Gap Contract — discovery/contracting; must be accepted from source-bound evidence, not chat memory.
- `PXAPI-19` — Acquisition Method, Site Inventory & Sampling Manifest v1 — planned P0 slice; must not start as READY until `PXAPI-4` and governance readiness are accepted and exact base SHA is re-read.

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