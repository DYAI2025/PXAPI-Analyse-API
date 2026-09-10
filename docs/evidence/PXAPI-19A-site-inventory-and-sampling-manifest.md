# PXAPI-19.A — Site Inventory & Sampling Manifest Contracts

**Jira:** `PXAPI-19` — Acquisition Method, Site Inventory & Sampling Manifest v1 (`In Arbeit`)
**Increment:** `PXAPI-19.A` — Contract/Foundation. `19.B` is **not authorized** by this slice.
**Authorities:** Confluence `55050241` v2 (plan acceptance and 19.A contract closure),
`54362115` (target architecture), `39846055`, `54362137`, `55181314`, `52625409`.
**Binding PO decisions applied:** `D-PXAPI19-PO-004` … `D-PXAPI19-PO-007`.

This document records what was verified, by which command, with which exact result. It is not an
acceptance decision: merge authorisation, independent `R4M` and Jira/Confluence closeout remain
Orchestrator/Human authority.

## A. Source baseline

| Fact | Exact value | How verified |
| --- | --- | --- |
| Repository | `DYAI2025/PXAPI-Analyse-API` | `git remote -v` |
| Normalised `origin` | `https://github.com/DYAI2025/PXAPI-Analyse-API.git` | same |
| Fetched `origin/main` | `0d1c7833f1c28831b6eaa9f0dff2741469fae6dc` | `git fetch origin && git rev-parse origin/main` |
| Matches the pinned SHA | yes, character-identical | string comparison |
| Starting local `HEAD` | `0d1c7833f1c28831b6eaa9f0dff2741469fae6dc` | `git rev-parse HEAD` |
| Starting branch | detached `HEAD` at that commit | `git rev-parse --abbrev-ref HEAD` |
| Starting `git status --porcelain` | empty | `git status --porcelain` |
| Main CI for that SHA | `python-compat` run `34426867277`, `success` | supplied and independently re-read |
| Open PRs at start | only `#5` | `gh pr list --state open` |
| Existing PXAPI-19 branch or PR | none | `git branch -r`, `gh pr list --state all` |
| Branch created | `feat/pxapi-19a-site-inventory-sampling-manifest`, from exact `origin/main` | `git checkout -b … origin/main` |

PR `#5` was **not** read, modified, rebased, closed or reused. No Jira or Confluence mutation was
performed; Confluence `55050241` and `54362115` were read only.

## B. What this slice delivers

### Files

| File(s) | Why |
| --- | --- |
| `contracts/v1/schemas/acquisition.v1.json` | new shared-definitions file: `public_url`, `url_key`, `digest` — the only lexical primitives both new contracts reference |
| `contracts/v1/schemas/site-inventory.v1.json` | the inventory contract |
| `contracts/v1/schemas/sampling-manifest.v1.json` | the manifest contract |
| `contracts/v1/manifest.json` | additive registration: one shared-definition entry, two contract entries |
| `contracts/v1/examples/site-inventory.*.example.json` (3) | rich multi-source discovery; **homepage-only / no further discovery**; every failure kind |
| `contracts/v1/examples/sampling-manifest.*.example.json` (3) | census; stratified sample; bounded selection with `selection_complete=false` |
| `tests/contracts/fixtures/invalid/site-inventory/` (14 + index) | targeted structural proofs, each the smallest document carrying the rule it breaks |
| `tests/contracts/fixtures/invalid/sampling-manifest/` (10 + index) | the same for the manifest |
| `tests/test_closed_vocabularies.py` | additive pins: every closed vocabulary the two contracts declare, as whole sets |
| `tests/acquisition/digests.py` | test-side reference implementation of the canonical serialisation and the digest projections |
| `tests/acquisition/test_digest_semantics.py` | the digest topology and the rules the digests declare |
| `tests/acquisition/test_acquisition_contract_semantics.py` | source-state authority, bootstrap truth, neutrality, provenance, sampling semantics |
| `contracts/README.md` | contract documentation, additive section |
| `docs/evidence/PXAPI-19A-…md` | this document |

42 files, 3 pre-existing files touched, **0 deleted lines in any pre-existing file**
(`git diff -U0 … | grep -c '^-[^-]'` = `0` for `manifest.json`, `contracts/README.md` and
`tests/test_closed_vocabularies.py`).

### Compatibility classification

**Additive / backward compatible.** No existing schema, example, fixture, expectation index or
test was modified or deleted. `test_the_pre_existing_contracts_are_untouched_by_the_addition`
re-validates every previously registered contract and its examples against the evolved registry,
and the seven prior contracts keep their `id`, `version` and meaning unchanged. No new dependency:
`pyproject.toml` and `uv.lock` are untouched and `uv lock --check` resolves 29 packages.

### Contract shape

```text
site-inventory.v1                          sampling-manifest.v1
  schema_version                             schema_version
  run_id  inventory_id  generated_at         run_id  sampling_manifest_id  generated_at
  target_origin        (= the seed identity) inventory_ref
  discovery_method + _version                inventory_output_digest  (binds the exact inventory)
  classifier + _version                      policy_id + policy_version
  sources[]   source_id (open)               budgets?  {integers only, minProperties 1}
              outcome   (closed, 10)         mode                (closed: CENSUS|STRATIFIED_SAMPLE)
              candidate_count                selection_complete  (mandatory boolean)
  candidates[] url_key                       selections[] url_key
               observed_forms[] (set)                     selection_rank  (order authority)
               provenance[]     (set)                     selection_reason (closed, 3)
               page_type?       (open)                    stratum?        (open)
               eligibility{state, reason?}   exclusions[] reason (closed, 3) + candidate_count
  input_digest  output_digest                input_digest  output_digest
```

Key rules, each proved below: **no `content_digest`**; `sources[]` is the only root authority on
source state; a source that could not admit anything is pinned to `candidate_count: 0`;
`candidates` and `selections` are never empty; every URL-valued member excludes userinfo; no
score, severity or polarity member exists anywhere; no numeric census threshold is declared.

## C. Verification

Every command was run from the repository root on the candidate tree.

| Gate | Command | Result |
| --- | --- | --- |
| PXAPI-19.A suite | `uv run pytest tests/acquisition -q` | `343 passed` |
| Contract + registry scope | `uv run pytest tests/acquisition tests/contracts tests/test_closed_vocabularies.py -q` | `997 passed` |
| Full suite, Python 3.13 (primary) | `uv run pytest -q` | `2061 passed, 2 warnings` |
| Full suite, Python 3.14 (the CI compat matrix leg, run locally) | `uv run --python 3.14 pytest -q` | `2061 passed, 2 warnings` |
| Lockfile | `uv lock --check` | `Resolved 29 packages`, rc `0` |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | `70 files already formatted` |

**Warnings and skips are not hidden.** The two warnings are the pre-existing
`anyio.abc.BlockingPortal` deprecation raised twice from `starlette/testclient.py:53`; they exist
on `origin/main` and are unrelated to this slice. There are **zero skipped, xfailed or xpassed
tests**. The baseline at `origin/main` was `1603 passed`; this slice adds `458` tests.

The Python 3.14 run reproduces the command CI uses (`uv run pytest`) on the same interpreter
version as the compat matrix. It is a local run and is **not** a substitute for CI on the exact
candidate SHA — see section F.

### The gates were observed failing, not merely observed green

27 counter-mutations, each applied to the committed tree, verified present on disk, run against
`tests/acquisition tests/contracts tests/test_closed_vocabularies.py`, then restored with
`git checkout --` and asserted byte-identical to `HEAD`. The tree was verified clean before every
mutation and after every restore, and each run wrote its own output file so one result cannot be
reported for another.

**The driver has its own canary.** `M0` rewords one schema description without changing a rule and
must produce rc `0` — it did, which is what proves the driver is capable of reporting GREEN rather
than always red. Every other mutation was required to produce rc `1`.

Control before the pass: `997 passed`, rc `0`. Control after: `997 passed`, rc `0`.

| # | Mutation | rc | failed | guards that fired first |
| --- | --- | --- | --- | --- |
| M0 | *control* — reword a description, change no rule | `0` | 0 | — (expected) |
| M1 | widen the source-outcome vocabulary with an 11th token | `1` | 2 | the vocabulary pin, the unrecognised-token rule |
| M2 | narrow it by dropping `TIMEOUT` | `1` | 6 | the pin, the exhaustive outcome matrix, the neutrality matrix |
| M3 | let `ABSENT` escape the zero-admitted-count pin | `1` | 3 | the non-admitting matrix, the fixture, the derived-subset pin |
| M4 | drop the zero-admitted-count rule entirely | `1` | 11 | the non-admitting matrix over every affected outcome |
| M5 | add a third `content_digest` to the inventory | `1` | 3 | the member classification, the topology rule, the fixture |
| M6 | make the inventory `output_digest` optional | `1` | 3 | the topology rule, the fixture, the schema category rule |
| M7 | add a root `sitemap_state` beside `sources[]` | `1` | 4 | the second-authority rule, the parallel-state rejection, the classification |
| M8 | let the inventory be emitted with no candidate | `1` | 2 | the bootstrap rule and its fixture |
| M9 | give a source entry a website `polarity` member | `1` | 2 | the source-entry closure rule, the judgement-name scan |
| M10 | let `url_key` use the userinfo-permitting URL shape | `1` | 3 | the credential matrix, the weaker-shape rule, the fixture |
| M11 | add `DUPLICATE_URL_KEY` to the exclusion vocabulary | `1` | 2 | the duplication rule, the vocabulary pin |
| M12 | let an eligible candidate carry an exclusion reason | `1` | 6 | the eligibility exclusivity matrix |
| M13 | let a candidate carry a raw `anchor_label` | `1` | 2 | the transient-input scan, the fixture |
| M14 | drop `uniqueItems` from a candidate's provenance | `1` | 1 | the provenance-aggregation rule |
| M15 | accept upper-case hexadecimal in a digest | `1` | 4 | the canonical-digest-shape matrix |
| M16 | permit userinfo in `public_url` | `1` | 5 | the credential matrix on both contracts |
| M17 | make `selection_complete` optional | `1` | 3 | the mandatory-method rule, the fixture, the category rule |
| M18 | widen `mode` with a provider-owned token | `1` | 4 | the mode rule, the provider-token scan, the fixture |
| M19 | declare a numeric `census_threshold` | `1` | 5 | the threshold-name scan, the numeric-constant rule, the classification |
| M20 | let a manifest select nothing | `1` | 2 | the empty-selection rule and its fixture |
| M21 | let a `selection_rank` be zero | `1` | 1 | the rank rule |
| M22 | let a declared budget be a floating-point number | `1` | 2 | the budget rule, the no-float rule |
| M23 | let an exclusion entry account for no candidate | `1` | 1 | the exclusion-count rule |
| M24 | let a selection carry a `score` | `1` | 2 | the selection closure rule, the judgement-name scan |
| M25 | stop sorting candidates in the output projection | `1` | 4 | the order-independence proofs and the recomputed example digests |
| M26 | read selections in array order instead of rank order | `1` | 1 | the array-reordering proof |
| M27 | widen the *pinned* vocabulary instead of the schema | `1` | 4 | the exhaustive matrices and the authority-distinction rule |

**Two holes were found during this pass, in the driver rather than in the contracts, and both are
recorded here rather than quietly fixed.** The first attempts at `M9`, `M13` and `M24` inserted
the new member as a sibling of `required` — that is, as an *unknown schema keyword* on the object
rather than a declared property. JSON Schema ignores an unknown keyword, so the contract was
unchanged and rc `0` was the correct answer; the mutation, not the guard, was wrong. Re-anchored
inside `properties`, all three were caught. This is the reason the driver asserts the mutated text
is on disk *and* that the tree is clean after restore: without those two assertions the first
result would have read as three genuine gaps in the neutrality guards.

### Reviewability

| Measurement | Command | Value |
| --- | --- | --- |
| Diff size | `git diff --no-ext-diff --unified=0 origin/main...HEAD \| wc -c` | `169594` |
| Convention | Confluence `45907970` craftsmanship correction 6 | `< 140000` |
| Files changed | `git diff --name-only origin/main...HEAD \| wc -l` | `42` |

**This exceeds the ~140,000-byte reviewability convention by about 21%, and is flagged rather
than concealed.** The convention was measured against slices that register one contract; this
increment registers **two** contracts plus a shared-definitions file, because Confluence
`55050241` scopes 19.A as both. The largest contributors are the two semantics suites
(`55 kB` combined), the two schemas (`31 kB`) and the 24 fixtures with their two expectation
indexes (`38 kB`). Fixture bases were already minimised once during this slice, which removed
`7 kB`.

**The concrete split point, if a Product Owner prefers two reviews:** `site-inventory.v1` with
`acquisition.v1.json`, its examples, its 14 fixtures and the neutrality/bootstrap/provenance
proofs first; `sampling-manifest.v1` with its examples, its 10 fixtures and the sampling proofs
second. The digest apparatus would go with the first and be extended by the second. This was
**not** done here because the brief authorises exactly one bounded pull request for 19.A; a split
is an Orchestrator decision, not an implementation one.

## D. Scope

### Nothing under `src/` changed

```text
git diff --name-only origin/main...HEAD -- src/            0 files
git diff --name-only origin/main...HEAD -- .github/ oracle/ .gitignore .python-version   0 files
git diff --name-only origin/main...HEAD -- pyproject.toml uv.lock                        0 files
```

`tests/test_package_scaffold.py::test_only_authorised_modules_declare_behavior` and
`tests/contracts/test_dependency_isolation.py` needed no widening, because this slice adds no
module and no import to `src/pxapi`. `BEHAVIOR_ALLOWED` and the validator allowlist are unchanged.

### Explicit confirmation of what was NOT built

No `SiteDiscoveryPort`; no same-origin discovery runtime; no sitemap or robots fetch or parser; no
HTML link traversal; no NAV/anchor-label reader; no production canonicalisation; no production
deduplication; no `DeterministicSamplePlanner`; no benchmark execution and no selection-threshold
decision; no CLI or HTTP API change; no real-boundary discovery smoke; no static multi-page
acquisition; no `page-acquisition-record.v1`; no browser execution, Crawl4AI or `RenderedPagePort`;
no static/rendered reconciliation; no scoring or score weights; no Product Diagnosis, Business
Context, Synthesis or Customer Projection; no PDF or report rendering; no PostgreSQL, queue, lease
or worker; no CRM, ElevenLabs or Buyer-Intent work; no deployment or runtime configuration change;
no Jira, Confluence or GitHub-settings mutation.

### Contract semantics deliberately left open

| Left open | Why |
| --- | --- |
| the census-to-sampling threshold | `C-PXAPI-005` keeps it `MISSING` until benchmarked; a test asserts the only numeric constant either contract declares is the `0` pinning a non-admitting source's count |
| the page-type and stratum taxonomies | `54362115` calls the taxonomy versioned contract work, so both stay open `code` tokens rather than a set invented here |
| the discovery-observation input shape | `input_digest` binds it, but it is transient PXAPI-19.B input; the shape used to make the examples' digests reproducible is declared as illustrative test data and is not a contract |
| the `source_id` vocabulary | `D-PXAPI19-PO-005` explicitly permits an open stable token |

## E. Decisions taken inside the authorised scope

These were forced by the brief and are recorded so a reviewer can overturn them deliberately.

1. **`PROVIDER_FAILURE` and `RUNTIME_ERROR` are two tokens, not one.** `D-PXAPI19-PO-005` names
   "provider/runtime failure" as one required distinction. Splitting it mirrors
   `assessment#/$defs/not_assessed_reason`, which already keeps the two apart, and the decision
   says "at least". A merged token would have lost a distinction the rest of the registry makes.
2. **`candidate_count` is required on every source, with a zero pin, rather than refused outside
   the enumerated outcomes.** Refusing the member would have lost the count of a partially-read
   source (`BUDGET_EXHAUSTED`, `TIMEOUT`). Pinning every other outcome to `0` is lossless and is a
   stronger guarantee: an absent, malformed, undeclared, refused or failed source is structurally
   incapable of reporting that it contributed pages.
3. **`inventory_output_digest` is required, not optional.** `D-PXAPI19-PO-004` defines the
   manifest's `input_digest` as covering it; an absent binding would leave the input digest
   covering a population nobody can identify.
4. **`sampling-manifest.selections` has `minItems: 1`.** `D-PXAPI19-PO-006` states the rule for the
   inventory only. Applying the same rule to the manifest keeps an apparently successful
   zero-selection artifact unrepresentable. **This is the one contract rule in this slice that
   extends a PO decision by analogy rather than applying it literally, and it is the one to
   overturn first if the PO disagrees.**
5. **`page_type` is optional rather than an `UNCLASSIFIED` token.** The brief requires an
   unclassified page to be incapable of becoming a polarity; an absent member is structurally
   incapable of carrying one, whereas a token would need its own neutrality rule.
6. **Selection order is carried by `selection_rank`, not by array position.** This is what makes
   "deterministic ordering" checkable and makes re-serialisation unable to change a manifest's
   output digest.

## F. Remaining truth

### Newly discovered work

* **Two rules are not expressible in JSON Schema and are enforced over the registered examples
  instead**, with the limit stated in the schema descriptions: (a) that a candidate's `url_key`
  equals `target_origin` for the seed — JSON Schema cannot compare two members of one document;
  (b) that a `CENSUS` manifest records no `STRATUM_QUOTA` selection — the walk rule in
  `tests/contracts/support.py::SchemaWalk` forbids a conditional that reaches into array items, so
  coupling a root member to an item is not available. Both are producer rules PXAPI-19.B must
  honour, and both would be enforced by a producer-side check in that slice.
* **`selection_rank` uniqueness and `budgets`/`exclusions` key uniqueness are not schema-enforced.**
  `uniqueItems` compares whole items, so two selections with the same rank and different identities
  validate. Dense ascending ranks are asserted over every registered example; a producer-side check
  belongs to 19.B.
* The reviewability figure above is over the convention and needs a Product Owner call.

### Unresolved findings carried, not resolved, by this slice

* `C-PXAPI-001` — PR `#5` remains open stale legacy drift. Untouched.
* `C-PXAPI-005` — the census/sampling threshold remains `MISSING`.
* The Jira metadata defect on issue link `11503` (PXAPI-20 shown as blocking PXAPI-19, the wrong
  direction) is unchanged: no Jira mutation was in scope.

### CI on the candidate

`MISSING/PENDING` at the time of writing. The `python-compat` workflow triggers on push, so a run
will exist for the pushed candidate SHA; its workflow name, run id, tested SHA and conclusion must
be read from GitHub Actions and are **not** inferred here. The local Python 3.13 and 3.14 runs
above are local evidence only.

### Evidence ceiling

**PXAPI-19.A proves contract/foundation implementation only.** It proves that two versioned,
provider-neutral, contract-tested artifacts exist in this repository, that their structural truth,
neutrality, provenance, digest topology and deterministic semantics are enforced by tests that
were each observed failing when the invariant was violated and passing after restoration, and that
the seven previously registered contracts are unaffected.

It does **not** prove:

* Site Discovery runtime;
* same-origin traversal;
* sitemap or robots runtime;
* producer canonicalisation or deduplication;
* Sampling Planner runtime;
* a benchmark-based sampling threshold;
* real-boundary SiteInventory production;
* multi-page acquisition;
* PXAPI-20;
* browser execution or Crawl4AI;
* scoring;
* Customer Projection or PDF;
* persistence, queue or worker;
* deployment;
* production readiness;
* any customer or business outcome.

`IC` for 19.A is claimed for the bounded contract scope above. `R2G` and `R4M` remain `UNKNOWN`
until CI on the exact candidate SHA and an independent review say otherwise. Merge is not Done,
CI is not runtime, and this agent's report is not independent verification.
