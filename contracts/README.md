# PXAPI contracts

The language-neutral contract surface of the Pixelkiez Website Analysis Platform: JSON Schema
(Draft 2020-12) documents under `contracts/v1/`, one manifest, and one valid example per
contract. Nothing under `src/` reads these files at runtime in slice A4; the tests under
`tests/contracts/` validate every example and every targeted invalid fixture against them.

```
contracts/v1/
├── manifest.json            inventory: canonical[11] · support[4] · shared_definitions[1] · problem_codes
├── schemas/
│   ├── common.v1.json       shared $defs — not a contract, no document validates against it
│   ├── <name>.v1.json       one file per contract, $id urn:pxapi:schema:<name>:1.0.0
└── examples/
    └── <name>[.<variant>].example.json
```

## Inventory

**Canonical (Confluence 39846055 §17, in that order):** `analysis-run-request`,
`measurement-record`, `website-evidence`, `business-context`, `business-intent-set`,
`contextual-diagnosis`, `scorecard`, `product-diagnosis`, `internal-analysis-record`,
`client-report-model`, `delivery-record`.

**Support (each carries its justification in the manifest):** `analysis-run-state`,
`stage-execution-record`, `artifact-descriptor`, `problem`.

**Shared definitions:** `common` — identifiers, timestamps, tokens, codes, the assessment /
value / score state vocabularies, the run-state and stage vocabularies, and small reusable
objects (`artifact_ref`, `producer_ref`, `subject`, `source_ref`, `failure`).

## Versioning and compatibility

- Every v1 document carries `"schema_version": "1.0.0"` (a `const`). The v1 set is
  **structurally frozen**: property sets and enums are closed where they are defined, and a v1
  validator accepts exactly `1.0.0` documents. No `1.x` forward compatibility is claimed — a
  validator built from these files rejects a document that carries a property they do not
  declare, whatever version that document claims.
- A structural or semantic change to any contract is a **new schema artifact** with a new
  version (`<name>.v2.json`, `"schema_version": "2.0.0"`, a new manifest entry). Descriptions
  and examples may be corrected in place when the correction does not change what validates.
- A wrong `schema_version` fails as an ordinary `const` violation at `/schema_version`; a
  missing one as `required` at the document root. The validator is looked up **by contract
  name only** — there is no second lookup keyed by version.
- `manifest.json › problem_codes` is *data vocabulary*, not schema structure: `problem.code` is
  an open token, so a later slice may register further codes there. Adding a code never alters
  the meaning of an existing one, and a client must handle an unknown code as a generic problem
  of the given `title`/`detail` rather than reject the document.

## Field categories

Every property belongs to exactly one category, and its description starts with the
category's label (a meta-test enforces this):

| Label                  | Meaning                                                                                                                  |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `Required.`            | present, never `null`                                                                                                    |
| `Required, nullable.`  | present; the description states exactly when `null` is the value                                                         |
| `Optional.`            | may be absent, never `null`; the description states what absence means — and absence is never a state or an unknown     |
| `Conditional.`         | present if and only if the stated condition holds (enforced by `if`/`then`); never `null`                                |

Optional-and-nullable does not occur.

## Lexical rules (from `common.v1.json`)

- **Identifiers** (`id`) are opaque, stable, non-empty strings of at most 128 characters
  without line breaks or leading/trailing whitespace. No identifier technology is prescribed.
- **Timestamps** are RFC 3339 instants in UTC with the mandatory `Z` designator, enforced by
  `pattern` — never by a `format` annotation, which the reference validator would not assert.
- **Tokens** (`token`) are opaque producer-defined vocabulary (channels, providers, source and
  artifact types); **codes** (`code`) are stable upper-snake-case machine codes (problem codes,
  failure codes, reason codes). Both are open sets.
- **Patterns** are fully anchored `^…(?!\n)$`, use no shorthand classes (`\d`, `\s`, `\w`) and
  no unescaped `.` outside a character class. Determinism is claimed for the Python
  `jsonschema` reference validator the tests run (Python `re`); the trailing lookahead closes
  the one known difference from ECMA-262 (`$` before a final newline).

## Missing measurement is not a website weakness

`measurement-record` and `website-evidence` items carry
`assessment_state = MEASURED | OBSERVED | NOT_ASSESSED`. For MEASURED/OBSERVED,
`value_state = KNOWN | UNKNOWN`:

- **KNOWN** — the value is present.
- **UNKNOWN** — the assessment ran but produced no value: `value` is `null`, `unknown_reason`
  (an open reason code) is required, and no zero, `false`, empty or negative substitute may
  stand in. An evidence item that is UNKNOWN has `polarity: NOT_APPLICABLE`.
- **NOT_ASSESSED** — nothing was assessed: `not_assessed_reason` is required (one of
  `PROVIDER_FAILURE`, `RUNTIME_ERROR`, `PERMISSION_DENIED`, `TIMEOUT`, `NOT_APPLICABLE`,
  `NOT_REQUESTED`), `value` and `confidence` are `null`, `value_state` is absent, and an
  evidence item has `polarity: NOT_APPLICABLE`. Every reason describes the analysis process,
  never the website.

**The absence of a record carries no meaning.** Neither UNKNOWN nor NOT_ASSESSED is ever
expressed by leaving a record out; both are explicit data.

The same rule reaches the scorecard: `score_state = SCORED | NOT_SCORED`; NOT_SCORED carries a
reason and a `null` value, never a zero, and there is no customer `PARTIAL_SCORE`. The overall
score is "optional" by being NOT_SCORED with a reason, never by absence.

## Analysis Run state

`analysis-run-state` carries exactly the nineteen states of Confluence §16. Which transitions
are legal is decided by `pxapi.domain.run_state` (27 approved edges over 361 ordered pairs;
`DELIVERY_FAILED → READY` is the only recovery edge and the only way any failure state leaves).
The contract adds a precise failure indication without new top-level states: for a failure
state, `failure.failure_stage` names the stage that failed and must map to that state
(`FAILED_COLLECTION` ← `BASELINE_COLLECTION`/`TARGETED_COLLECTION`, `FAILED_RESEARCH` ←
`BUSINESS_RESEARCH`, `FAILED_SYNTHESIS` ← `SYNTHESIS`/`SCORING`/`PRODUCT_DIAGNOSIS`/
`CUSTOMER_PROJECTION`, `FAILED_VALIDATION` ← `RENDERING`/`VALIDATION`, `DELIVERY_FAILED` ←
`DELIVERY`); `BLOCKED_INPUT` happens before any stage and has `failure_stage: null`.

`stage_executions` embeds one `stage-execution-record` per stage that has **started**; stages
that have not started are not pre-materialised. Pass 1 (Baseline Collection and Business
Research, concurrent) is projected onto the run state by `pxapi.domain.stage_execution`; from
`COLLECTING_TARGETED` onwards the run state machine is authoritative and stages are recorded,
not projected.

## Problem semantics

`problem` is transport-neutral: `code` (open token), `title`, `detail`, optional `run_id`,
`errors[] = {pointer, keyword, message}`. No HTTP status, no type URI, no transport binding.
Every text member is single-line and bounded. **Producer rule:** `detail` and every
`errors[].message` are rendered from fixed templates over `(contract, pointer, keyword)` only;
validator free text is never copied, which is what keeps tracebacks, filesystem paths, secrets
and raw exception messages out of the document by construction. Codes registered at 1.0.0:
`CONTRACT_VALIDATION_FAILED`, `CONTRACT_NOT_FOUND`, `SCHEMA_VERSION_UNSUPPORTED`,
`ILLEGAL_RUN_TRANSITION`.

## Consumer rules JSON Schema cannot express

1. An index the score model computes is listed in `scorecard.indices` as SCORED or NOT_SCORED;
   omission is not a state.
2. Every scorecard index is projected into `client-report-model.scores` as SHOWN or WITHHELD.
3. A validation the application knows about but did not execute is written as NOT_RUN in
   `internal-analysis-record.validations`; absence from the list carries no meaning.
4. Evidence ids referenced by claims and recommendations must exist in the referenced
   artifacts — a later application gate, not a schema rule.
5. `analysis-run-state.stage_executions` holds at most one record per stage, and every embedded
   record's `run_id` equals the parent's.
6. `analysis-run-state.transitions` is an ordered audit log whose last entry's `to_state` is
   the current `state`; repeated `READY → DELIVERY_FAILED → READY` pairs are legal and v1
   derives no attempt count or limit from them.
7. A run whose request carries no `delivery_channels` rests at `READY`; only a reported
   successful delivery action moves it to `DELIVERED` — no delivery is ever fabricated.
8. `requester_ref`, `contact_ref` and `recipient_ref` are opaque references held by adapters;
   an e-mail address is never written into a contract document.
