# PXAPI Decision Ledger

This ledger records delivery-relevant accepted decisions and their authority. It is an index, not a replacement for the cited authority.

| ID | Status | Decision | Authority | Evidence boundary |
| --- | --- | --- | --- | --- |
| D-PXAPI-001 | ACCEPTED | Federated authority by claim type; no global SSoT. | PXAPI project governance / Confluence | Requires live source read for current claims. |
| D-PXAPI-002 | ACCEPTED | One canonical Analysis Run / Analysis Truth feeds internal and external projections. | PXAPI Confluence `39846055`, amendment `52527106` | Target/product decision; does not prove runtime implementation. |
| D-PXAPI-003 | ACCEPTED | Measurement, Business Context, Synthesis, Scoring/Product Diagnosis, Customer Projection, Rendering and adapters are separate responsibilities. | PXAPI Confluence `39846055` | Architecture intent, not runtime proof. |
| D-PXAPI-004 | ACCEPTED | Missing, unavailable, provider-error or not-assessed evidence must not become website weakness or score penalty. | PXAPI Confluence `39846055`, `52527106`; Skill baseline | Cross-cutting semantic invariant. |
| D-PXAPI-005 | ACCEPTED | Skill parity is source-bound to an exact frozen Skill snapshot; no floating `latest skill` target. | PXAPI Confluence `52527106`; PXK-web-skill docs | Each new parity increment needs a fresh frozen reference. |
| D-PXAPI-006 | ACCEPTED | Acquisition and Site Intelligence belong to PXAPI; the Skill remains migration source / Regression Oracle. | PXAPI Confluence `54362115` | Target architecture. |
| D-PXAPI-007 | ACCEPTED | Sampling is Pixelkiez methodology; providers must not decide score-/diagnosis-relevant pages. | PXAPI Confluence `54362115` | Target architecture. |
| D-PXAPI-008 | ACCEPTED | Census first; deterministic stratified sampling only above a benchmark-based threshold. | PXAPI Confluence `54362115` | Exact threshold remains MISSING until benchmarked/versioned. |
| D-PXAPI-009 | ACCEPTED | Static HTTP and rendered-browser observations are separate modes; delta is not automatically conflict. | PXAPI Confluence `54362115` | Target evidence model. |
| D-PXAPI-010 | ACCEPTED | Crawl4AI may be used behind a provider-neutral adapter; it is not domain authority. | PXAPI Confluence `54362115` | Provider version/security/license must be reverified at implementation time. |
| D-PXAPI-011 | ACCEPTED | API and worker roles remain one Python codebase/modular monolith initially; no premature microservice split. | PXAPI Confluence `54362115` | Runtime isolation may still use separate process/container. |
| D-PXAPI-012 | ACCEPTED | Business action hypotheses and later impact verification are separate artifacts. | PXAPI Confluence `54362115` | No causal/ROI proof follows from diagnosis alone. |
| D-PXAPI-013 | ACCEPTED | WIP limit is one mutating implementation theme. | PXAPI governance / delivery policy | Planning/discovery can proceed read-only. |
| D-PXAPI-014 | ACCEPTED | Delivery gates follow IC -> R2G -> R4M; exact-candidate binding is mandatory. | PXAPI DRS / anti-drift governance | Candidate change invalidates R2G/R4M. |
| D-PXAPI-015 | ACCEPTED | Merge != Done; CI != runtime; agent report != independent verification. | PXAPI anti-drift governance | Closeout needs source-specific readback. |
| D-PXAPI-016 | ACCEPTED | Pareto-first acquisition path is PXAPI-4 -> PXAPI-19 -> PXAPI-20 -> measure evidence gain before browser complexity. | Product Owner decision recorded in PXAPI architecture/Jira receipt | Value expectation is a hypothesis until measured. |

## Change rule

A new decision may be appended only when its authority and scope are explicit. A newer artifact does not silently supersede an older authorized product decision. Supersession must name the prior decision and the bounded scope it changes.