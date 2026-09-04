# PXK-17 — candidate reuse matrix for PR #5

**Slice:** PXK-59 (PXAPI PXK-17.1 — Rebaseline & Generic Contract Harness)
**Date:** 2026-09-04
**Authority:** Confluence `45907970`; Jira `PXK-59` (parent `PXK-8`, aggregate `PXK-17`)

## Frozen inputs

| Input | Exact value | How verified |
| --- | --- | --- |
| Base `main` | `b84a283a855cbad8c12e02b8a5273c3d141731d5` | `git rev-parse origin/main` after `git fetch origin --prune` |
| Candidate PR | #5, state `OPEN`, base `main` | `gh pr view 5 --json state,baseRefName` |
| Candidate head | `ed9814b96a96cb57ad4460709c50fed599727794` | `gh pr view 5 --json headRefOid` |
| Candidate size | 252 changed files vs `main` | `git diff --name-status origin/main...ed9814b` |

PR #5 is a **frozen reuse source**. It is not merged, not rebased, not force-pushed and not used
as a branch base. The PXK-59 branch starts from `main` at the SHA above.

## How to read this matrix

| Verdict | Meaning |
| --- | --- |
| `REUSE` | ported with no semantic change (formatting/imports may differ) |
| `REWRITE` | the pattern is kept, the content is rebuilt against the new registry model |
| `DROP` | not carried into PXK-59 at all |
| `DEFER` | out of PXK-59 scope; belongs to a named later slice |

Verdicts are per **file family**, and every one of the 252 changed files falls into exactly one
row below. Counts are `git diff --name-status origin/main...ed9814b` line counts per family.

## Matrix

### Harness and tests

| # | File family | Files | Verdict | Reason |
| --- | --- | --- | --- | --- |
| 1 | `tests/contracts/support.py` | 1 | `REWRITE` | The loader, the offline `referencing` registry, the `parse_constant` NaN guard, the pointer rendering and the sanitised producer are the most valuable work in PR #5 and are kept. Rebuilt because the module hard-coded the inventory: `CANONICAL_CONTRACT_NAMES` (11), `SUPPORT_CONTRACT_NAMES` (4) and a single global `CONTRACTS_VERSION` as the semantic authority for every contract. Replaced by a `ContractRoot` that reads a flat registry, plus per-contract versions. `Violation.message` is retained internally but can no longer influence ordering or output. |
| 2 | `tests/contracts/test_manifest.py` | 1 | `REWRITE` | Filename kept, because Jira and Confluence name it in the validation command. Content replaced: the PR #5 file asserted `len(names) == 11`, an exact support list, and `len(on_disk) == 16`. Those are exactly the frozen inventory PXK-59 must not ship. Now asserts entry shape, vocabulary membership, uniqueness and path resolution — all generic over the registry. |
| 3 | `tests/contracts/test_schema_meta.py` | 1 | `REWRITE` | The closed-object/property-category walker, the anchored-pattern rule, the no-`format` rule and the `$ref`-resolution walk are ported (the walker moved into `support.py` so the evolution proof can reuse it). Dropped from it: `CUSTOMER_LEAK_NAME` and the customer-projection leak tests (PXK-60+ semantics), `test_every_canonical_contract_requires_run_id` (slice semantics), and the magic-number canaries `seen > 50`, `conditionals >= 15`, `declaring >= 30`, replaced by canaries derived from registry data. |
| 4 | `tests/contracts/test_versioning.py` | 1 | `REWRITE` | Version-acceptance, closed-root and optional-not-nullable cases ported and made generic over per-contract versions. The shared-primitive vocabulary tests (timestamps, tokens, ids, urls, text) are `DEFER`red with the primitives they exercise. Problem-producer tests moved to their own module. |
| 5 | `tests/contracts/test_examples_valid.py` | 1 | `REWRITE` | Ported; the `len(CASES) >= 15` count canary is replaced by "every registered contract contributed an example", which is the same guarantee without pinning a number. |
| 6 | `tests/contracts/test_invalid_fixtures.py` | 1 | `REWRITE` | Ported, but the one-sidecar-per-case discovery is replaced by one `expectations.json` index per contract directory. Orphan detection is kept and strengthened: a case with no expectation and an expectation with no case are both reported. The `len(CASES) >= 45` canary is dropped. |
| 7 | `tests/contracts/test_vocabulary_parity.py` | 1 | `DROP` | Its entire purpose is keeping `common.v1.json` enums in parity with `pxapi.domain.run_state` and `pxapi.domain.stage_execution`. Both modules are out of PXK-59 scope, and `src/pxapi/**` stays byte-untouched. |
| 8 | `tests/contracts/__init__.py` | 1 | `REUSE` | Empty package marker. |
| 9 | `tests/domain/__init__.py`, `test_run_state_transitions.py`, `test_stage_execution.py` | 3 | `DEFER` → PXK-60 | Tests for the Run lifecycle and stage projection. |
| 10 | `tests/test_package_scaffold.py` (modified) | 1 | `DROP` | PR #5 modified it because it added behavior under `src/`. PXK-59 adds none, so the file stays byte-identical to `main`. |

### Contract data

| # | File family | Files | Verdict | Reason |
| --- | --- | --- | --- | --- |
| 11 | `contracts/v1/manifest.json` | 1 | `REWRITE` | The idea of a manifest is kept; the model is not. PR #5 splits the inventory into `canonical` (11) and `support` (4) arrays with a single `contracts_version`. Replaced by one flat `contracts` array where each entry carries `name`, `id`, `version`, `role`, `status`, `owner_slice`, `schema`, `examples`, plus a `registry` block holding the registry's own version, dialect, ID namespace and the role/status vocabularies. `problem_codes` and the open-code policy are kept; `ILLEGAL_RUN_TRANSITION` is removed (PXK-60). |
| 12 | `contracts/v1/schemas/common.v1.json` | 1 | `REWRITE` | The lexical-primitive idea and the anchored-pattern discipline are kept. Reduced to the six primitives PXK-59 artifacts actually consume: `single_line_text`, `single_line_label`, `id`, `code`, `json_pointer`, `schema_keyword`. Everything else is `DEFER`red — see row 13. The single-line rule is strengthened from `[^\r\n]` to rejecting all C0/C1 controls, DEL and U+2028/U+2029. The global `schema_version` const is removed: each contract pins its own version. |
| 13 | `common.v1.json` definitions not carried over: `timestamp`, `url`, `token`, `text`, `short_text`, `language`, `country`, `confidence`, `score_value`, `assessment_state`, `value_state`, `not_assessed_reason`, `unknown_reason`, `evidence_class`, `score_state`, `not_scored_reason`, `artifact_ref`, `producer_ref`, `subject`, `source_ref`, `contract_name`, `run_state`, `stage`, `stage_status`, `failure` | (24 defs) | `DEFER` | Each belongs with the contract that first consumes it. `run_state`/`stage`/`stage_status` → PXK-60. Assessment and evidence vocabulary → PXK-61+. Scoring vocabulary → the scoring slice. `contract_name` as a closed enum of 15 names is additionally `DROP`ped as a model: it duplicates the registry inventory in a schema, which is precisely the hard-coded-inventory failure PXK-59 exists to remove. |
| 14 | `contracts/v1/schemas/problem.v1.json` | 1 | `REWRITE` | Transport neutrality, the open `code` token and the bounded single-line text members are kept. Changed: `errors[].message` is removed (a free-text member is the leak channel); `errors` gains `maxItems`; `title`/`detail`/`pointer`/`keyword` move onto the strengthened shared primitives; `schema_version` pins this contract's own version. |
| 15 | `contracts/v1/examples/problem.example.json`, `problem.transition.example.json` | 2 | `REWRITE` | One example is rebuilt for the new shape; the second is rebuilt as a validation-failure example. `problem.transition.example.json` is dropped as such because it exercises `ILLEGAL_RUN_TRANSITION` (PXK-60). |
| 16 | `contracts/v1/schemas/analysis-run-request.v1.json`, `analysis-run-state.v1.json`, `stage-execution-record.v1.json` | 3 | `DEFER` → PXK-60 | Run lifecycle and stage execution. |
| 17 | `contracts/v1/schemas/measurement-record.v1.json`, `website-evidence.v1.json` | 2 | `DEFER` → PXK-61 | Measurement and website evidence. |
| 18 | `contracts/v1/schemas/artifact-descriptor.v1.json` | 1 | `DEFER` → artifact-safety slice | Digest/access/retention/redaction metadata. |
| 19 | `contracts/v1/schemas/scorecard.v1.json`, `product-diagnosis.v1.json` | 2 | `DEFER` → scoring/diagnosis slice | Scoring and product diagnosis. |
| 20 | `contracts/v1/schemas/business-context.v1.json`, `business-intent-set.v1.json` | 2 | `DEFER` → PXK-45 | Business context and intent. |
| 21 | `contracts/v1/schemas/contextual-diagnosis.v1.json` | 1 | `DEFER` → PXK-46 | Contextual search/competition diagnosis. |
| 22 | `contracts/v1/schemas/client-report-model.v1.json` | 1 | `DEFER` → PXK-44 | Client report model. |
| 23 | `contracts/v1/schemas/delivery-record.v1.json` | 1 | `DEFER` → V5/Post-MVP | Delivery record. |
| 24 | `contracts/v1/schemas/internal-analysis-record.v1.json` | 1 | `DEFER` → integration slice | Aggregating record; cannot precede what it aggregates. |
| 25 | `contracts/v1/examples/*.json` other than the two `problem` examples | 25 | `DEFER` | Each follows its schema's slice. |
| 26 | `tests/contracts/fixtures/invalid/problem/*` | 8 | `REWRITE` | The four PR #5 problem cases are rebuilt against the new shape and expressed in the expectation index; ten further cases are added, including the U+2028 separator case, the `errors[].message` rejection and the `maxItems` bound. |
| 27 | `tests/contracts/fixtures/invalid/<other contracts>/*` | 180 | `DEFER` | Each follows its contract's slice. |

### Source, configuration and documentation

| # | File family | Files | Verdict | Reason |
| --- | --- | --- | --- | --- |
| 28 | `src/pxapi/domain/run_state.py` | 1 | `DEFER` → PXK-60 | Run lifecycle. PR #5 implements 19 global states; the accepted model is six. |
| 29 | `src/pxapi/domain/stage_execution.py` | 1 | `DEFER` → PXK-60 | Stage projection. |
| 30 | `src/pxapi/domain/__init__.py` (modified) | 1 | `DROP` | PXK-59 adds no domain code; `src/pxapi/**` stays byte-untouched. |
| 31 | `pyproject.toml` (modified) | 1 | `REWRITE` | The dev-only `jsonschema` pin is reused. `referencing` is added explicitly, because the harness imports it directly and PR #5 relied on it only as a transitive dependency of `jsonschema`. `[project].dependencies` stays `[]`. |
| 32 | `uv.lock` (modified) | 1 | `REWRITE` | Regenerated from the amended dev group rather than copied. |
| 33 | `README.md` (modified) | 1 | `REWRITE` | Contract section rewritten for the registry model; the A3 scaffold text is preserved. |
| 34 | `contracts/README.md` | 1 | `REWRITE` | Registry model, per-contract versioning, consumer compatibility rules and the Problem producer rule. The 11+4 inventory narrative is removed. |
| 35 | `docs/evidence/PXK-17-contracts-v1.md` | 1 | `DROP` | Evidence for a candidate that is not being merged. PXK-59 writes its own evidence document; PR #5 stays referenceable at its frozen head. |

### Totals

| Verdict | Files |
| --- | --- |
| `REUSE` | 1 |
| `REWRITE` | 23 |
| `DROP` | 4 |
| `DEFER` | 224 |
| **Total** | **252** |

Row 13 lists definitions inside `common.v1.json`, not files, so it contributes no file to this
table; its file is counted once in row 12. The totals are machine-derived: every one of the 252
paths in `git diff --name-only origin/main...ed9814b` matches exactly one row, with no path
unmatched and none double-counted.

## What this matrix does not claim

* It does not claim PR #5 is wrong. It classifies each family against **PXK-59's** scope.
* It does not evaluate the deferred schemas' content. A `DEFER` verdict is a scope statement,
  not an approval of the deferred file.
* The reuse decisions were taken by reading the candidate files at head `ed9814b`. They are
  `VERIFIED` as to what the candidate contains and `DERIVED` as to the scope boundary, which
  comes from Confluence `45907970` and the accepted PXK-59 brief.
