# PXK-17 — Contracts v1 & Analysis Run State Machine (Slice A4)

**Jira key:** PXK-17 (PXAPI A4 — Define Contracts v1 and Analysis Run state machine)
**Parent:** PXK-8 — PXAPI Foundation & Boilerplate
**UTC verification timestamp:** 2026-09-02T18:54:01Z
**Status:** implementation complete and locally verified — **not merged, not accepted**. Every
result below is `AGENT_REPORTED` until the Orchestrator re-derives it at the exact head; the
CI result for that head is recorded in the pull request once observed (section J).

---

## A. Start state

| Property | Verified value |
| --- | --- |
| Repository | `DYAI2025/PXAPI-Analyse-API`, origin `https://github.com/DYAI2025/PXAPI-Analyse-API.git` |
| Fetched `origin/main` at start | `b84a283a855cbad8c12e02b8a5273c3d141731d5` — equal to the authority SHA |
| Local checkout at start | `feat/pxk-16-python-scaffold` @ `c114866` (ancestor of `b84a283`), `git status --porcelain --untracked-files=all` empty |
| PXK-17 branch / PR before work | none (`git ls-remote`, `gh pr list --state all`: PRs #1–#4 only) |
| Canonical sources re-read | PXK-17 (updated 2026-08-31), Confluence 39846055 / 40239107 / 40337411 (all last modified 2026-08-31) — no material change against the implementation prompt |
| A3 baseline before mutation | `uv sync --locked` ok · `uv lock --check` exit 0 · `ruff check` "All checks passed!" · `ruff format --check` "13 files already formatted" · `pytest` **38 passed** |
| Derived plan (scratchpad, `derived_noncanonical`) | SHA-256 `787e5f72741c93a3baf54e8f279c88903f6e1b24103c22e1290f5e9706c96431` — matched; used as supporting material only. It conflicted with the prompt in three places and the prompt won: no pre-materialised ten-stage records, `unknown_reason` open (not an enum), no full ten-stage projection engine |
| Branch | `feat/pxk-17-contracts-v1` created from fetched `origin/main` (`b84a283`) |

## B. Commits (in order, each green in a clean worktree)

| SHA | Subject | `pytest` at that commit (clean `git worktree`) |
| --- | --- | --- |
| `8711b01` | build(pxk-17): add jsonschema as a dev-only contract test dependency | 38 passed |
| `9a4aed1` | feat(pxk-17): add the v1 contract surface | 38 passed |
| `9f7c40c` | test(pxk-17): prove the v1 contracts with meta-rules, examples and invalid fixtures | 484 passed |
| `0808187` | feat(pxk-17): add the Analysis Run state machine, the Pass-1 projection and the A4 module guard | 956 passed |
| `79445d0` | test(pxk-17): keep contract and domain vocabularies in parity | 963 passed |
| `ea67605` | docs(pxk-17): document the contract surface, versioning and consumer rules | 963 passed |

`git diff b84a283 --name-status`: 246 added, **5 modified** (`README.md`, `pyproject.toml`,
`uv.lock`, `src/pxapi/domain/__init__.py` docstring, `tests/test_package_scaffold.py`), 0 deleted.

## C. Dependency diff

`pyproject.toml`: `[dependency-groups].dev += "jsonschema>=4.26,<5"`; `[project].dependencies`
stays `[]`. `uv.lock`: +103 lines (jsonschema 4.26.0, attrs, jsonschema-specifications,
referencing, rpds-py). `uv lock --check` exit 0. No workflow change.

## D. What was built

### Contract surface (`contracts/v1/`)

Manifest `contracts/v1/manifest.json`: `contracts_version 1.0.0`, dialect Draft 2020-12,
`canonical[11]` in Confluence §17 order, `support[4]` each with a justification,
`shared_definitions[1]` (`common`), `problem_codes[4]` plus an explicit open-code policy.

| Kind | Names |
| --- | --- |
| Canonical (11) | analysis-run-request · measurement-record · website-evidence · business-context · business-intent-set · contextual-diagnosis · scorecard · product-diagnosis · internal-analysis-record · client-report-model · delivery-record |
| Support (4) | analysis-run-state · stage-execution-record · artifact-descriptor · problem |
| Shared | common (`$defs` only) |

16 schema files, **27 valid examples** (every contract ≥ 1; the missing-measurement, blocked-
input, failed-research, pending/failed-delivery, not-assessed-context and render-artifact
branches each have their own example), **94 targeted invalid fixtures** (every contract ≥ 1).
Full semantics: `contracts/README.md`.

### Executable domain (`src/pxapi/domain/`, stdlib only)

- `run_state.py` — `RunState` (19), `SUCCESS_PATH`, `FAILURE_STATES`, `ALLOWED_TRANSITIONS`
  (the single edge source), derived `LEGAL_TRANSITIONS` and `TERMINAL_STATES`,
  `transition()` / `can_transition()` / `is_terminal()` / `is_failure()`, `IllegalTransition`
  with `code = "ILLEGAL_RUN_TRANSITION"` and a message naming only the two states.
- `stage_execution.py` — `Stage` (10), `StageStatus` (5), `PASS_ONE_STAGES`,
  `FAILURE_STATE_FOR` (stage → coarse failure state; the contract's `failure_stage` rule),
  `StageExecution`, `project_pass_one()`, `InconsistentStageRecords`.

Exact transition set (27 edges): REQUESTED→{VERIFIED, BLOCKED_INPUT}; VERIFIED→
{COLLECTING_BASELINE, BLOCKED_INPUT}; COLLECTING_BASELINE→{BUSINESS_RESEARCH,
COLLECTING_TARGETED, FAILED_COLLECTION, FAILED_RESEARCH}; BUSINESS_RESEARCH→
{COLLECTING_TARGETED, FAILED_RESEARCH}; COLLECTING_TARGETED→{SYNTHESIZING, FAILED_COLLECTION};
SYNTHESIZING→{SCORING, FAILED_SYNTHESIS}; SCORING→{PRODUCT_DIAGNOSIS, FAILED_SYNTHESIS};
PRODUCT_DIAGNOSIS→{CUSTOMER_PROJECTING, FAILED_SYNTHESIS}; CUSTOMER_PROJECTING→{RENDERING,
FAILED_SYNTHESIS}; RENDERING→{VALIDATING, FAILED_VALIDATION}; VALIDATING→{READY,
FAILED_VALIDATION}; READY→{DELIVERED, DELIVERY_FAILED}; DELIVERY_FAILED→{READY}.

Derived counts (enumerated by `tests/domain/test_run_state_transitions.py`, cross-checked
against the literal figures): **19 states → 361 ordered pairs → 27 legal, 334 illegal** (of
which 19 self-loops). Terminal (derived: no outgoing edge): DELIVERED, BLOCKED_INPUT,
FAILED_COLLECTION, FAILED_RESEARCH, FAILED_SYNTHESIS, FAILED_VALIDATION. READY's incoming
edges are exactly {VALIDATING, DELIVERY_FAILED}.

Pass-1 projection (`project_pass_one`, record set → state, order-independent, absent record =
not started): baseline FAILED → FAILED_COLLECTION (checked first; both failed → canonical order
decides); research FAILED → FAILED_RESEARCH; baseline not SUCCEEDED → COLLECTING_BASELINE
(whatever research does, including SUCCEEDED first); baseline SUCCEEDED and research not
SUCCEEDED → BUSINESS_RESEARCH; both SUCCEEDED → COLLECTING_TARGETED. Fail-closed:
duplicate stage, a stage outside Pass 1, or CANCELLED without a FAILED sibling raise
`InconsistentStageRecords`. Every event interleaving (6 orderings × 4 outcome combinations)
walks only approved edges.

### A3 guard swap

`test_scaffold_declares_no_behavior` (A3, "to be replaced by the first real slice") is replaced
by `test_only_approved_a4_modules_are_executable`: an exact allowlist
`{domain/run_state.py, domain/stage_execution.py}` compared in both directions against an AST
walk, plus red proofs on throwaway copies of the real tree (scoring, measurement, synthesis,
rendering, a port, an adapter; a hollowed allowlisted module; a bare statement).

## E. Acceptance-criteria matrix (PXK-17)

| AC | Artefacts | Tests (names as collected) |
| --- | --- | --- |
| AC1 inventory covers all 11 | `manifest.json`, 11 `schemas/*.v1.json` | `test_manifest.py`: `…exactly_the_eleven_canonical_contracts_in_confluence_order`, `…exactly_the_four_support_contracts`, `…every_schema_file_on_disk_is_listed…` (16 files), `…contract_entry_points_at_existing_files_with_matching_ids[15]` |
| AC2 version, requiredness, valid example | `const "1.0.0"` in every schema; explicit `required`; 27 examples | `test_examples_valid.py` (29), `test_schema_meta.py`: `…closed_object_with_a_const_schema_version`, `…objects_are_closed_and_every_property_states_its_category[16]`, `…canonical_contract_requires_run_id` |
| AC3 invalid examples fail deterministically | 94 fixtures with `.expect.json` | `test_invalid_fixtures.py` (98: each case validated twice, expected `(pointer, keyword)` ⊆ actual; every contract covered) |
| AC4 legal/illegal transitions | `run_state.py`, `stage_execution.py` | `test_run_state_transitions.py` (398: 27 positive, 334 negative, terminal, READY/DELIVERED entry rules), `test_stage_execution.py` (63: 20 record sets, 24 interleavings, fail-closed inputs) |
| AC5 NOT_ASSESSED / UNKNOWN / provider failure ≠ negative finding | `if/then` invariants in measurement-record, website-evidence, business-context, scorecard, client-report-model | fixtures `measurement-record/{not-assessed-with-negative-value, unknown-with-zero-value, not-assessed-without-reason, unknown-without-reason, not-assessed-with-value_state, known-with-null-value}`, `website-evidence/{not-assessed-negative-polarity, unknown-negative-polarity, known-without-measurement-ref}`, `business-context/not-assessed-with-facts`, `scorecard/{not-scored-with-zero-value, partial-score-state, scored-without-evidence}`, `client-report-model/{score-partial-state, withheld-score-with-value}` |
| AC6 stable, client-readable errors | `problem.v1.json`, manifest `problem_codes`, `IllegalTransition.code`, producer rule in `contracts/README.md` | `test_versioning.py`: `…problem_built_from_hostile_validator_output_is_sanitised`, `…rendering_is_deterministic_and_order_independent`, `…unknown_future_problem_code_remains_consumable`, `…problem_carries_no_transport_binding`, `…wrong_version_maps_to_schema_version_unsupported[15]`; fixtures `problem/{extra-traceback-property, multiline-detail, code-lowercase, error-message-too-long}`; `test_illegal_transition_message_names_only_the_two_states` |
| AC7 no analysis intelligence | executable production modules = exactly the two domain files, stdlib only | `test_only_approved_a4_modules_are_executable` + 9 red proofs; `tests/architecture/**` unchanged and green |

Prompt test ids A–V map as: A→AC1 · B→AC2 · C,D,E,F,G→`test_versioning.py` (generic over the
manifest) + fixtures · H,I,J,K,L→AC5 fixtures + `website-evidence/known-without-measurement-ref`,
`contextual-diagnosis/{relevant-claim-without-evidence, verified-fact-without-refs}`,
`product-diagnosis/recommendation-without-claim` · M,N,O,P→AC4 · Q,R→`test_stage_execution.py`
· S,T→AC6 · U→AC7 · V→`tests/architecture` (23 + 3 tests unchanged, green).

## F. Test evidence (exact commands, Python 3.13.3 unless stated)

| Command | Result |
| --- | --- |
| `uv sync --locked` | exit 0 |
| `uv lock --check` | exit 0 ("Resolved 13 packages") |
| `uv run ruff check .` | exit 0, "All checks passed!" |
| `uv run ruff format --check .` | exit 0, "27 files already formatted" |
| `uv run pytest` (3.13.3) | exit 0, **963 passed**, 0 skipped |
| `uv run --python 3.14 pytest` (3.14.6) | exit 0, **963 passed**, 0 skipped |
| `uv run --python 3.14 ruff check .` / `ruff format --check .` | "All checks passed!" / "27 files already formatted" |

Collected per file: architecture 26 · contracts 453 (examples 29, invalid fixtures 98,
manifest 24, schema meta 41, versioning 254, parity 7) · domain 461 (transitions 398, stage
execution 63) · package scaffold 23.

## G. Counter-mutations (each executed, observed red, reverted; revert proven by an empty scoped `git diff --stat -- <file>`)

| # | Mutation | Red tests | Revert |
| --- | --- | --- | --- |
| 1 | drop `target_url` from analysis-run-request `required` | 1 (`missing-target_url` fixture) | empty |
| 2 | allow NEGATIVE polarity under NOT_ASSESSED (website-evidence) | 1 | empty |
| 3 | `additionalProperties: true` on client-report-model root | 4 (closed-object meta ×2, root-property test, `extra-internal-property` fixture) | empty |
| 4 | add `audit_coverage` property to client-report-model | 1 (leak walk) | empty |
| 5 | add READY to `ALLOWED_TRANSITIONS[FAILED_SYNTHESIS]` | 5 | empty |
| 6 | remove COLLECTING_BASELINE → COLLECTING_TARGETED | 5 | empty |
| 7 | rename DELIVERED in `common#/$defs/run_state` | 2 (parity + example) | empty |
| 8 | projection returns BUSINESS_RESEARCH while baseline still RUNNING | 9 | empty |
| 9 | map BUSINESS_RESEARCH failure to FAILED_COLLECTION | 10 | empty |
| 10 | let FAILED_RESEARCH name BASELINE_COLLECTION in the run-state contract | 1 (parity) | empty |
| 11 | widen `schema_version` to a `1.x.y` pattern | 122 | empty |
| 12 | make the timestamp `Z` optional | 1 (`…timestamps_are_rejected['2026-09-02T10:15:30']`) | empty |
| 13 | UNKNOWN no longer requires `unknown_reason` | 1 | empty |
| 14 | NOT_SCORED may carry a value | 2 | empty |
| 15 | add `src/pxapi/domain/scoring.py` with one `def` | 8 (guard names the module) | file removed, status empty |
| 16 | remove `run_state.py` from the guard allowlist | 10 | empty |
| 17 | `import jsonschema` inside `pxapi.domain.run_state` | 1 (`tests/architecture` — untouched) | empty |

Permanent red proofs that need no reversal: `tests/test_package_scaffold.py` (9 guard cases
on throwaway trees), `tests/architecture/test_boundaries_detect_violations.py` (unchanged),
`tests/contracts/test_schema_meta.py::test_leak_walk_sees_internal_vocabulary_where_it_exists`.

## H. Scope and preservation

| Check | Command | Result |
| --- | --- | --- |
| Oracle unchanged | `git diff b84a283 --stat -- oracle \| wc -l` | 0 |
| Architecture tests unchanged | `git diff b84a283 --stat -- tests/architecture \| wc -l` | 0 |
| Prior evidence, LICENSE, workflow, `.python-version`, `.gitignore` unchanged | `git diff b84a283 --stat -- docs/evidence/PXK-1{4,5,6}-*.md LICENSE .github .python-version .gitignore \| wc -l` | 0 |
| Root package and the other four layers unchanged | `git diff b84a283 --stat -- src/pxapi/__init__.py src/pxapi/py.typed src/pxapi/ports src/pxapi/application src/pxapi/adapters src/pxapi/config \| wc -l` | 0 |
| No FastAPI / SQLAlchemy / S3 / Pydantic / driver | `grep -rniE 'fastapi\|starlette\|sqlalchemy\|alembic\|boto3\|botocore\|s3\|pydantic\|psycopg' src pyproject.toml \| wc -l` | 0 |
| Runtime dependencies empty | `grep -n -A1 '^dependencies' pyproject.toml` | `dependencies = []` |
| Executable production modules | `executable_modules(SRC)` | `['domain/run_state.py', 'domain/stage_execution.py']` == allowlist |
| `src/` imports | `grep -rhE '^(import\|from) ' src \| sort -u` | stdlib + `pxapi.domain.run_state` only |

No implementation of any of the following exists in the diff (the only occurrences of such words are inside fixtures that prove their rejection, e.g. `artifact-descriptor/storage-key-property`): persistence, RunStore/ArtifactStore, SQLAlchemy, migrations,
S3, FastAPI, HTTP endpoints, CLI execution, Pydantic, API keys/scopes, idempotency, SSRF/URL
policy, collectors, SERP, LLM adapters, business research, score formulas, product-diagnosis
logic, customer-projection logic, PDF/SVG/WeasyPrint, CRM, e-mail, Docker/Coolify, workflows.
No Jira or Confluence mutation was performed.

## I. Decisions taken inside the authorised scope (for Orchestrator review)

1. `unknown_reason` and `not_scored_reason` are open codes (`common#/$defs/code`);
   `not_assessed_reason` is the closed six-value enum the prompt lists ("support at least" is
   satisfied exactly; widening it is a v2 change).
2. `analysis-run-state.stage_executions` embeds full `stage-execution-record` documents (one per
   started stage, may be empty); no ten-record pre-materialisation.
3. `failure.failure_stage` is required-nullable: null iff `BLOCKED_INPUT`, otherwise it must be a
   stage that maps to the failure state — the same mapping as `FAILURE_STATE_FOR`, parity-tested.
4. `analysis-run-state.transitions` is an audit log with a typed first entry (from nothing into
   REQUESTED), grounded in 40239107 §6 ("persists state, identities, transitions").
5. Score values are `number` on 0..100 (not integer), so a v1 producer is not forced to round.
6. `analysis-run-request.delivery_channels` (tokens, may be empty) is included: it is the
   request-side counterpart of `delivery-record.channel` and grounded in Confluence §15.
7. `confidence` on measurement records and evidence items is required-nullable, null iff
   NOT_ASSESSED, so a provider failure cannot be recorded as "confidence 0".
8. `text`/`short_text` reject whitespace-only strings; the test harness rejects the non-JSON
   constants `NaN`/`Infinity` at load time (a NaN score would otherwise pass `maximum`).
9. `manifest.problem_codes` is declared data vocabulary that may grow under 1.0.0 (prompt §10);
   this is recorded as an explicit carve-out from the frozen-v1 rule in `contracts/README.md`.

## J. Unresolved

- **PO sign-off wanted** on decision I.9 (problem codes may be registered without a contracts
  version bump) and I.6 (`delivery_channels` on the request).
- **CI at the exact head**: recorded in the PR once the `python-compat` run for the pushed head
  completes; until then the figures in §F are local runs.
- Not enforceable by schema (documented as consumer rules): cross-artifact existence of
  referenced ids; one record per stage inside `stage_executions`; "never an e-mail" for the
  opaque `*_ref` identifiers.
