# PXAPI Contradiction Ledger

This ledger preserves unresolved, historical or bounded cross-source divergences. It prevents a newer or more convenient source from silently laundering conflicting evidence into truth.

| ID | Status | Claim / contradiction | Sources | Resolution / current treatment |
| --- | --- | --- | --- | --- |
| C-PXAPI-001 | OPEN / NON-BLOCKING FOR PXAPI-19 | GitHub PR #5 remains open although current `main` has independently evolved far beyond its old base. | PR #5 base `b84a283...`, head `ed9814b...`; current main lineage through governance PR #12 | Treat PR #5 as stale legacy delivery drift. It is not current WIP and must not be merged without a separate reconcile. No automatic close/delete. |
| C-PXAPI-002 | RESOLVED BY AUTHORITY BOUNDARY | Historical PXK Jira issues describe earlier API slices while current project authority is Jira project `PXAPI` / Board 436. | Historical PXK tickets; PXAPI Confluence Jira-authority page `52625409`; current PXAPI backlog | Historical PXK items are reference/evidence only. New backlog/status/sprint truth uses PXAPI Jira. |
| C-PXAPI-003 | RESOLVED BY CURRENT/TARGET SPLIT | Skill V2.1 contains scoring, customer PDF, legal sidecar and batch capabilities that current PXAPI `main` does not implement. | PXK-web-skill docs / frozen V2.1 snapshot; PXAPI README/current contracts | This is expected parity gap, not false implementation. Skill is Regression Oracle / migration source; PXAPI target architecture may adopt/adapt capabilities incrementally. |
| C-PXAPI-004 | RESOLVED BY SOURCE BINDING | Confluence product amendment described the installed Skill baseline while GitHub `pxk-web-skill` contains multiple uploaded ZIPs. | PXAPI amendment `52527106`; parity page `54362137`; private repo `DYAI2025/pxk-web-skill@f29767f...` | `PXAPI-4` bound parity to exact V2.1 artifact/digests and is Erledigt. Any later Skill version requires a new parity rebaseline; unqualified repo `latest` remains invalid as parity authority. |
| C-PXAPI-005 | OPEN / DESIGN INPUT | Target acquisition architecture requires census-first sampling but the exact census-to-sampling threshold is unknown. | PXAPI architecture `54362115`; PXAPI-19 | Keep threshold `MISSING` until representative benchmarks support a versioned policy. Do not invent a threshold in implementation. |
| C-PXAPI-006 | OPEN / IMPLEMENTATION-TIME REVERIFY | Crawl4AI was evaluated at version `v0.9.3`, but provider facts are time-sensitive. | PXAPI architecture `54362115` | Reverify current upstream version, security notes and license/attribution terms before PXAPI-21 implementation. Do not treat the evaluation version as permanently current. |

## Severity rule

A contradiction blocks mutation only when it affects the same current claim, scope and validity window and cannot be resolved by the correct domain authority. Historical divergence and expected migration gaps remain visible but do not automatically block unrelated work.

## Update rule

Never delete a contradiction to make systems look aligned. Mark it resolved only with the resolving authority/evidence and preserve the prior state.