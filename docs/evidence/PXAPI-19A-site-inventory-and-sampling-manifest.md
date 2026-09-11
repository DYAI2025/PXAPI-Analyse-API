# PXAPI-19.A — Site Inventory & Sampling Manifest Contracts

**Jira:** `PXAPI-19` — Acquisition Method, Site Inventory & Sampling Manifest v1 (`In Arbeit`)
**Increment:** `PXAPI-19.A` — Contract/Foundation. `19.B` is **not authorized** by this slice.
**Authorities:** Confluence `55050241` v2 (plan acceptance and 19.A contract closure),
`54362115` (target architecture), `39846055`, `54362137`, `55181314`, `52625409`.
**Binding PO decisions applied:** `D-PXAPI19-PO-004` … `D-PXAPI19-PO-007`.

This document records what was verified, by which command, with which exact result. It is not an
acceptance decision: merge authorisation, independent `R4M` and Jira/Confluence closeout remain
Orchestrator/Human authority.

## A0. The superseded candidate, and what this repair changed

An independent PO/architecture review of candidate `88879110d82493c527b5f40dbc730ff3bda699e4`
found **four material contract gaps**. They are contract defects, not test defects, so each was
repaired in the schema first and proved afterwards.

**`8887911` and every `IC` / `R2G` statement made about it are stale.** Its CI run
(`python-compat` `34542520428`, `success`) tested a tree whose two contracts no longer exist in
that shape. Nothing below is carried forward from that candidate except where this document says
so explicitly and labels it as historical.

| Finding | Defect on `8887911` | Repair |
| --- | --- | --- |
| 1 | `selection_complete=false` was admissible **bare** — no budget, no exclusion, no cause. AC9 requires it to stay structurally traceable to a technical runtime/safety/budget limitation. | new root `incompleteness` object, one closed `cause`; `false` requires it, `true` refuses it, a declared-budget cause additionally requires `budgets` |
| 2 | `sampling-manifest.selections[].stratum` was **optional**. AC4 requires every selected page to carry Page-Type/Stratum, a selection reason and a stable reference. | `stratum` required on every selection; the taxonomy stays open; a page the classification could not place uses the neutral `UNCLASSIFIED` token |
| 3 | Duplicate semantic keys were representable, and the digest projections sort by exactly those keys. `sorted` is stable, so a duplicate made a *canonical* digest depend on input order. | five semantic-key rules stated in the contracts and enforced by a new contract-semantic layer under `tests/`; the digest projections **fail closed** before ordering anything |
| 4 | `target_origin` referenced the generic page shape, so the canonical site authority accepted `https://example.com/a/b?x=1#y`. | new shared `public_origin` definition; `target_origin` uses it |
| — | The `CENSUS` description said the mode **means** every eligible candidate was selected, contradicting the valid `CENSUS` + `selection_complete=false` state. | the mode names an intent; completion is `selection_complete`'s statement; a test refuses the absolute phrasing returning |

### Preflight before any change was made

| Check | Expected | Measured | Command |
| --- | --- | --- | --- |
| remote | `https://github.com/DYAI2025/PXAPI-Analyse-API.git` | identical | `git remote -v` |
| PR `#14` head branch | `feat/pxapi-19a-site-inventory-sampling-manifest` | identical | `gh pr view 14 --json headRefName` |
| PR `#14` `headRefOid` | `88879110d82493c527b5f40dbc730ff3bda699e4` | identical | `gh pr view 14 --json headRefOid` |
| branch `HEAD` | `88879110d82493c527b5f40dbc730ff3bda699e4` | identical | `git rev-parse HEAD` |
| `origin/main` | `0d1c7833f1c28831b6eaa9f0dff2741469fae6dc` | identical | `git fetch origin && git rev-parse origin/main` |
| worktree | clean | empty output | `git status --porcelain` |

No mismatch, so the repair proceeded. PR `#5` was not read, modified or reused; no Jira and no
Confluence mutation was performed.

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
| `contracts/v1/schemas/acquisition.v1.json` | new shared-definitions file: `public_url`, **`public_origin`**, `url_key`, `digest` |
| `contracts/v1/schemas/site-inventory.v1.json` | the inventory contract |
| `contracts/v1/schemas/sampling-manifest.v1.json` | the manifest contract |
| `contracts/v1/manifest.json` | additive registration: one shared-definition entry, two contract entries |
| `contracts/v1/examples/site-inventory.*.example.json` (3) | rich multi-source discovery; **homepage-only / no further discovery**; every failure kind |
| `contracts/v1/examples/sampling-manifest.*.example.json` (3) | census; stratified sample; bounded census carrying `selection_complete=false` **and its technical cause** |
| `tests/contracts/fixtures/invalid/site-inventory/` (16 + index) | targeted structural proofs, each the smallest document carrying the rule it breaks |
| `tests/contracts/fixtures/invalid/sampling-manifest/` (15 + index) | the same for the manifest |
| `tests/acquisition/semantics.py` | **the contract-semantic layer**: the five semantic-key rules JSON Schema cannot state, and the fail-closed gate |
| `tests/acquisition/fixtures/semantic-invalid/` (6 + 2 indexes) | schema-**valid** counterexamples that are still ambiguous |
| `tests/acquisition/test_semantic_keys.py` | that the rules bite, that the schema does not cover them, and that the digest refuses rather than guessing |
| `tests/test_closed_vocabularies.py` | additive pins: every closed vocabulary the two contracts declare, as whole sets |
| `tests/acquisition/digests.py` | test-side reference implementation of the canonical serialisation and the digest projections |
| `tests/acquisition/test_digest_semantics.py` | the digest topology and the rules the digests declare |
| `tests/acquisition/test_acquisition_contract_semantics.py` | source-state authority, bootstrap truth, neutrality, provenance, sampling semantics, AC9 and AC4 |
| `contracts/README.md` | contract documentation, additive section |
| `docs/evidence/PXAPI-19A-…md` | this document |

60 files, 3 pre-existing files touched, **still 0 deleted lines in any pre-existing file** —
measured, not assumed: `git diff --no-ext-diff -U0 origin/main -- <file> | grep -c '^-[^-]'` is
`0` for `contracts/v1/manifest.json`, `contracts/README.md` and
`tests/test_closed_vocabularies.py`. The repair *does* rewrite paragraphs of the README's
acquisition section and one canary in the vocabulary pins, but every line it rewrote was a line
this branch added, so nothing that existed on `origin/main` is removed. No previously registered
schema, example, fixture or expectation index was modified or deleted.

### Compatibility classification

**Additive / backward compatible with respect to `origin/main`.** No previously registered schema,
example, fixture, expectation index or test was modified or deleted.
`test_the_pre_existing_contracts_are_untouched_by_the_addition` re-validates every previously
registered contract and its examples against the evolved registry, and the seven prior contracts
keep their `id`, `version` and meaning unchanged. No new dependency: `pyproject.toml` and
`uv.lock` are untouched and `uv lock --check` resolves 29 packages.

**Not backward compatible with the superseded candidate `8887911`, and deliberately so.** A
document that was valid against that candidate's `sampling-manifest.v1` can be invalid against
this one: it may carry `selection_complete=false` without a cause, or a selection without a
stratum. Both contracts stay at `1.0.0` because **neither has ever been released** — 19.A is the
slice that introduces them, `origin/main` has never carried either, and there is no consumer to
break. Had either been on `main`, this would be a new `$id` at a new version instead.

### Contract shape

```text
site-inventory.v1                          sampling-manifest.v1
  schema_version                             schema_version
  run_id  inventory_id  generated_at         run_id  sampling_manifest_id  generated_at
  target_origin  (public_origin;             inventory_ref
                  = the seed identity)       inventory_output_digest  (binds the exact inventory)
  discovery_method + _version                policy_id + policy_version
  classifier + _version                      budgets?  {integers only, minProperties 1}
  sources[]   source_id (open, unique)       mode                (closed: CENSUS|STRATIFIED_SAMPLE)
              outcome   (closed, 10)         selection_complete  (mandatory boolean)
              candidate_count                incompleteness{cause} (iff selection_complete false)
  candidates[] url_key (unique)              selections[] url_key         (unique)
               observed_forms[] (set)                     selection_rank  (unique + dense 1..n)
               provenance[]     (set)                     selection_reason (closed, 3)
               page_type?       (open)                    stratum         (open, required)
               eligibility{state, reason?}   exclusions[] reason (closed, 3, unique)
                                                          + candidate_count
  input_digest  output_digest                input_digest  output_digest
```

Key rules, each proved below: **no `content_digest`**; `sources[]` is the only root authority on
source state; a source that could not admit anything is pinned to `candidate_count: 0`;
`candidates` and `selections` are never empty; every URL-valued member excludes userinfo;
`target_origin` is an **origin**, not a page; no score, severity or polarity member exists
anywhere; no numeric census threshold is declared; an incomplete selection always names the
technical limitation that stopped it; every selected page carries a stratum.

The members marked `unique` / `dense` above are **not schema-enforced and are not claimed to be**
— `uniqueItems` compares whole items. They are enforced by `tests/acquisition/semantics.py`, which
the digest projections call before ordering anything, and producer-side enforcement is mandatory
in PXAPI-19.B.

## C. Verification

Every command was run from the repository root on the candidate tree.

| Gate | Command | Result |
| --- | --- | --- |
| PXAPI-19.A suite | `uv run pytest tests/acquisition -q` | `475 passed` |
| Contract + registry scope | `uv run pytest tests/acquisition tests/contracts tests/test_closed_vocabularies.py -q` | `1149 passed` |
| Full suite, Python 3.13 (primary) | `uv run pytest -q` | `2213 passed, 2 warnings` |
| Full suite, Python 3.14 (the CI compat matrix leg, run locally) | `uv run --python 3.14 pytest -q` | `2213 passed, 2 warnings` |
| Lockfile | `uv lock --check` | `Resolved 29 packages`, rc `0` |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | `72 files already formatted` |

**Warnings and skips are not hidden.** The two warnings are the pre-existing
`anyio.abc.BlockingPortal` deprecation raised twice from `starlette/testclient.py:53`; they exist
on `origin/main` and are unrelated to this slice. There are **zero skipped, xfailed or xpassed
tests**. The baseline at `origin/main` was `1603 passed`; this slice now adds `610` tests, of
which `152` are the repair (`2061 → 2213`).

### The repair was observed making the old shape fail

Before any test was touched, the four schema changes alone turned **exactly five** existing
assertions red — and no others:

```text
test_every_neutral_technical_condition_is_representable[sampling-manifest/bounded-selection]
test_selection_complete_is_neutral_in_both_values[False]
test_each_declared_selection_reason_is_representable[SEED]
test_each_declared_selection_reason_is_representable[CENSUS]
test_each_declared_selection_reason_is_representable[STRATUM_QUOTA]
```

`5 failed, 999 passed`. Each was a document the repaired contract now refuses — a bare
`selection_complete=false`, and three selections built without a stratum — so the failures are
the contract change biting rather than collateral damage, and each was then rebuilt in its
repaired shape.

### The 15 proofs the repair brief requires

Run as one explicit selection: `55 passed`, rc `0`.

| # | Proof | Expected | Where |
| --- | --- | --- | --- |
| 1 | `selection_complete=false` without a technical cause | RED | `test_an_incomplete_selection_without_a_technical_cause_is_refused`; fixture `incomplete-selection-without-cause` |
| 2 | `selection_complete=true` carrying a cause | RED | `test_a_complete_selection_may_not_claim_an_incompleteness_cause`; fixture `complete-selection-claiming-a-cause` |
| 3 | budget-exhaustion cause without the declared budget | RED | `test_a_budget_exhaustion_cause_requires_the_declared_budget`; fixture `budget-cause-without-declared-budget` |
| 4 | selected page without a stratum | RED | `test_a_selected_page_without_a_stratum_is_refused`; fixture `selection-without-stratum` |
| 5 | neutral `UNCLASSIFIED` stratum | GREEN | `test_a_selection_the_classifier_could_not_place_is_representable_and_neutral`, plus a verdict-refusal proof |
| 6 | duplicate inventory `source_id` | semantic RED | `semantic-invalid/site-inventory/duplicate-source-id` |
| 7 | duplicate candidate `url_key` | semantic RED | `semantic-invalid/site-inventory/duplicate-candidate-url-key` |
| 8 | duplicate selected `url_key` | semantic RED | `semantic-invalid/sampling-manifest/duplicate-selected-url-key` |
| 9 | duplicate `selection_rank` | semantic RED | `semantic-invalid/sampling-manifest/duplicate-selection-rank` |
| 10 | duplicate exclusion `reason` | semantic RED | `semantic-invalid/sampling-manifest/duplicate-exclusion-reason` |
| 11 | path / query / fragment in `target_origin` | RED | `test_a_target_origin_that_is_not_a_bare_origin_is_refused` (9 values); 2 fixtures |
| 12 | valid root public origin | GREEN | `test_a_root_public_origin_is_accepted` (5 values, incl. explicit port) |
| 13 | reordering valid order-independent collections | digest unchanged | `test_reordering_an_unambiguous_document_leaves_its_output_digest_unchanged`, `…_the_selections_of_an_unambiguous_manifest_…` |
| 14 | ambiguous duplicate-key input | digest refuses | `test_the_digest_refuses_an_ambiguous_document_rather_than_producing_a_value` **and** `test_an_ambiguous_document_would_digest_differently_under_two_serialisations` |
| 15 | `CENSUS` + `selection_complete=false` with structured evidence | GREEN | `test_a_bounded_census_is_valid_and_carries_its_technical_limitation` |

Proof 14 is the one that needed two tests. The first shows the gate raising; the second
reconstructs the **unguarded** ordering and shows it producing two different digests for two
serialisations of one document — without which "the gate raises" would prove only that a rule
exists, not that it was needed. Every counterexample in 6–10 is additionally asserted
**schema-valid** (`test_the_counterexample_satisfies_the_schema_completely`), which is the
evidence that `uniqueItems` does not cover these relationships.

**One modelling error in the repair's own tests was caught by that canary and is recorded rather
than quietly fixed.** The first version of proof 14 asserted that `duplicate-selected-url-key`
also makes the digest order-dependent. It does not: selections are ordered by `selection_rank`,
so one identity at two ranks creates no sort tie. The canary failed, and the *model* was
corrected, not the assertion — `TIE_CREATING_RULES` in `test_semantic_keys.py` now names only the
four rules whose duplicate lands on a sort key, `NON_TIE_RULES` names the two that protect
something else, and a test asserts every rule falls into exactly one group and that each
tie-creating rule names a collection the projections really sort.

The Python 3.14 run reproduces the command CI uses (`uv run pytest`) on the same interpreter
version as the compat matrix. It is a local run and is **not** a substitute for CI on the exact
candidate SHA — see section F.

### The gates were observed failing, not merely observed green

Two passes exist, and they are kept apart on purpose.

* **`M1`–`M27` was measured on the superseded candidate `8887911`.** That tree no longer exists.
  The table is retained below as the record of that pass and is **historical evidence about
  invariants, not a gate on this candidate**; it is not re-stated as if it had been re-measured.
* **`R0`–`R24` was measured on the repaired tree.** `R1`–`R15` cover every repaired invariant.
  `R16`–`R24` re-run nine of the `M` mutations that land in regions this repair rewrote, so the
  claim that the pre-existing guards still bite is measured rather than inferred.

Both passes used the same discipline: each mutation applied to the committed tree, the anchor
asserted to match exactly once, the mutated text asserted present on disk, `git diff` asserted
non-empty for the mutated file, the suite run against
`tests/acquisition tests/contracts tests/test_closed_vocabularies.py`, then `git checkout --` and
`git status --porcelain` asserted empty. Each run wrote its own output file, so one result cannot
be reported for another.

**The driver has its own canary.** `R0` rewords one schema description without changing a rule and
must produce rc `0` — it did. Every other mutation was required to produce rc `1`.

Control before the `R` pass: `1149 passed`, rc `0`. Control after: `1149 passed`, rc `0`, tree
clean.

#### `R0`–`R15` — the repaired invariants

| # | Mutation | rc | failed | guards that fired first |
| --- | --- | --- | --- | --- |
| R0 | *control* — reword a description, change no rule | `0` | 0 | — (expected) |
| R1 | drop the rule requiring `incompleteness` when `selection_complete` is false | `1` | 3 | the AC9 rule, the bounded-census rule, the fixture |
| R2 | drop the rule refusing `incompleteness` when it is true | `1` | 2 | the contradiction rule, the fixture |
| R3 | drop the rule requiring `budgets` for a budget-exhaustion cause | `1` | 3 | the budget rule, the fixture, the schema category rule |
| R4 | widen the incompleteness vocabulary with a website-quality token | `1` | 2 | the closed-vocabulary rule, the vocabulary pin |
| R5 | narrow it by dropping `SAFETY_LIMIT_REACHED` | `1` | 5 | the pin, the exhaustive cause matrix, the neutrality matrix |
| R6 | make `stratum` optional again | `1` | 3 | the AC4 rule, the fixture, the schema category rule |
| R7 | close the stratum taxonomy with an `enum` | `1` | 9 | the open-taxonomy rule, the token-shape rule, the `UNCLASSIFIED` neutrality rule, the pin-coverage rule |
| R8 | point `target_origin` back at the page shape | `1` | 10 | the origin-shape rule, the 9-value rejection matrix, both fixtures |
| R9 | widen `public_origin` to accept a path, query or fragment | `1` | 9 | the rejection matrix, both fixtures |
| R10 | remove the semantic gate from the inventory projection | `1` | 4 | the fail-closed proof, the order-dependence proof |
| R11 | remove it from the manifest projection | `1` | 6 | the same, on the manifest |
| R12 | delete the `unique_source_id` rule | `1` | 5 | the counterexample, the gate, the rule-coverage rule |
| R13 | delete the `dense_selection_rank` rule | `1` | 6 | the gap counterexample, the coverage rule, the violation-record rule |
| R14 | restore the old absolute `CENSUS` wording | `1` | 1 | the mode-description rule |
| R15 | drop `incompleteness` from the digest classification | `1` | 1 | the member-classification rule |

#### `R16`–`R24` — the pre-existing guards, re-measured on the repaired tree

| # | Mutation | rc | failed | guards that fired first |
| --- | --- | --- | --- | --- |
| R16 | add a third `content_digest` property to the inventory | `1` | 3 | the classification, the topology rule, the fixture |
| R17 | make the inventory `output_digest` optional | `1` | 3 | the topology rule, the fixture, the category rule |
| R18 | make `selection_complete` optional | `1` | 3 | the mandatory-method rule, the fixture, the category rule |
| R19 | let a manifest select nothing | `1` | 2 | the empty-selection rule and its fixture |
| R20 | stop sorting candidates in the output projection | `1` | 5 | the order-independence proofs and the recomputed example digests |
| R21 | read selections in array order instead of rank order | `1` | 2 | the array-reordering proofs, old and new |
| R22 | add `DUPLICATE_URL_KEY` to the exclusion vocabulary | `1` | 2 | the duplication rule, the vocabulary pin |
| R23 | let `url_key` use the userinfo-permitting URL shape | `1` | 3 | the credential matrix, the weaker-shape rule, the fixture |
| R24 | permit userinfo in `public_url` | `1` | 4 | the credential matrix on both contracts |

**A hole was found in the `R` driver and is recorded rather than quietly fixed.** `R16` inserts a
property, so the mutated text legitimately still contains the original anchor; the driver's
"anchor must be gone" assertion rejected the mutation as not having bitten. The mutation was
correct and the *check* was wrong for insertions — it is now conditioned on whether the
replacement text contains the anchor. The abort also left the mutated file on disk, which the
next run's pre-pass cleanliness assertion caught immediately; the file was restored with
`git checkout --` and the pass re-run from a verified-clean tree. Without those two assertions the
first result would have read as a genuine gap in the digest-topology guard.

#### `M1`–`M27` — historical, measured on the superseded candidate `8887911`

The pass below was run against a tree that this repair has replaced. It is **not** evidence about
the current candidate; `R16`–`R24` above is, for the nine mutations whose regions changed.

That pass had its own canary too: `M0` reworded one schema description without changing a rule and
produced rc `0`, which is what proved the driver capable of reporting GREEN rather than always red.
Every other mutation was required to produce rc `1`.

Control before that pass: `997 passed`, rc `0`. Control after: `997 passed`, rc `0`. **Both figures
describe the superseded tree.**

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

A document cannot state its own contribution to a diff without changing it, so the figure below
is measured **excluding `docs/evidence`** — the convention this repository already used for
PXK-61 — and this document's own size is given separately.

| Measurement | Command | Before repair | After repair |
| --- | --- | --- | --- |
| Diff size, everything except this document | `git diff --no-ext-diff --unified=0 origin/main...HEAD -- . ':!docs/evidence' \| wc -c` | `169594` | `264624` |
| Convention | Confluence `45907970` craftsmanship correction 6 | `< 140000` | `< 140000` |
| This document | `git diff --no-ext-diff --unified=0 origin/main...HEAD -- docs/evidence \| wc -c` | about `22000` | about `44000` |
| Files changed | `git diff --name-only origin/main...HEAD \| wc -l` | `43` | `60` |

**Excluding this document the diff is now about 89% over the ~140,000-byte reviewability
convention, against 21% before the repair. The repair roughly doubled the overrun, and that is
flagged rather than concealed.** The PO decision not to split PR `#14` was taken against the
`169594` figure; `264624` is a materially different number and the decision deserves to be
re-taken against it rather than assumed to carry over. Measured by group:

| Group | Bytes |
| --- | --- |
| the two pre-existing semantics suites | `71643` |
| the 31 schema-invalid fixtures and their two expectation indexes | `49645` |
| the two contract schemas | `40745` |
| the semantic-key layer and its suite | `32054` |
| the contracts README section | `17285` |
| examples, manifest registration, vocabulary pins | `22146` |
| the six semantic counterexamples and their two indexes | `13201` |
| the digest reference implementation | `12491` |
| the shared lexical definitions | `5414` |

Nothing was trimmed to flatter the figure, and nothing unrelated to the four findings was added.
The repair's own contribution is roughly `95 kB`: about `45 kB` of new proof (the semantic-key
layer, its suite, the AC9/AC4/origin proof sections), about `30 kB` of counterexamples (7 new
schema-invalid fixtures, 6 semantic counterexamples, 2 new indexes), about `9 kB` of schema text —
the descriptions that state what each new rule is for and, in three places, that JSON Schema does
**not** enforce the relationship — and the rest documentation.

**The concrete split point, if a Product Owner prefers two reviews:** `site-inventory.v1` with
`acquisition.v1.json` (both URL shapes and the origin narrowing), its examples, its 16 fixtures,
its two semantic counterexamples and the neutrality/bootstrap/provenance proofs first;
`sampling-manifest.v1` with its examples, its 15 fixtures, its four semantic counterexamples and
the sampling/AC9/AC4 proofs second. The digest apparatus and the semantic-key layer would go with
the first and be extended by the second. This was **not** done here because PO decision 2 of the
repair brief explicitly directs that PR `#14` is not split on reviewability grounds and that
19.A's authority scopes the two contracts together; a split remains an Orchestrator decision.

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
| the page-type and stratum taxonomies | `54362115` calls the taxonomy versioned contract work, so both stay open `code` tokens rather than a set invented here. Requiring `stratum` did **not** close it: the member declares no `enum`, and `UNCLASSIFIED` is a named neutral value inside an open set, not a vocabulary — a test asserts the token carries no rule of its own |
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
5. **The inventory's `page_type` is optional; the manifest's `stratum` is required.** The
   asymmetry is deliberate and is the one place the repair overturned an earlier decision of this
   slice. A candidate is a page discovery merely found, and whether the classifier reached it is
   a fact about the classifier — an absent member is structurally incapable of carrying a
   judgement, which is why `page_type` stays optional. A **selected** page is one this analysis
   committed to, and AC4 requires every one of them to carry Page-Type/Stratum, so the absent
   member is no longer available there: it would be read as "counted under no stratum" by one
   consumer and "nothing worth counting" by the next. The neutrality that absence used to provide
   is carried instead by the `UNCLASSIFIED` token, and it is structural rather than promised — no
   member of the contract keys on the token, and a test asserts it appears exactly once in the
   schema file, in the description that names it.
6. **Selection order is carried by `selection_rank`, not by array position.** This is what makes
   "deterministic ordering" checkable and makes re-serialisation unable to change a manifest's
   output digest.

### Decisions taken during the repair

7. **The incompleteness cause is a root object, not a conditional on `exclusions`.** The brief
   preferred reuse of the existing exclusion/budget model. It is not available: `SchemaWalk` in
   `tests/contracts/support.py` resets the property owner at `items`, so a root-level conditional
   cannot reach into an array item and `selection_complete` cannot be coupled to an exclusion
   entry. The brief's stated fallback — "the smallest explicit root-level technical incompleteness
   object" — was taken. **The schema harness was not weakened to make the conditional pass**;
   `test_objects_are_closed_and_every_property_states_its_category` is unchanged and fired during
   `R3` and `R6`.
8. **`SELECTION_BUDGET_EXHAUSTED` is deliberately one token in two vocabularies.** It is both an
   `exclusion_reason` (why individual candidates were not taken) and an `incompleteness.cause`
   (why the taking stopped). Those are different facts and the contract says so; giving the second
   a different spelling would have implied they were different events.
9. **`budgets` moves from `Optional` to `Conditional`.** It is required when the cause names a
   declared budget, so the schema category rule demands the change; the alternative — not
   requiring the budget — would leave a manifest asserting a bound nobody can read.
10. **The semantic-key rules live under `tests/` and add no `src/pxapi` module.** 19.A authorises
    no production validator. The consequence is stated in the contracts, the README and here:
    **a schema-valid document is not thereby unambiguous**, and producer-side enforcement is
    mandatory in 19.B.
11. **Both contracts stay at `1.0.0` despite a breaking shape change.** Neither has ever been on
    `origin/main`, so there is no consumer to break and no released version to supersede. Had
    either been released, this would be a new `$id` at a new version.

## F. Remaining truth

### Newly discovered work

* **Two rules are not expressible in JSON Schema and are enforced over the registered examples
  instead**, with the limit stated in the schema descriptions: (a) that a candidate's `url_key`
  equals `target_origin` for the seed — JSON Schema cannot compare two members of one document;
  (b) that a `CENSUS` manifest records no `STRATUM_QUOTA` selection — the walk rule in
  `tests/contracts/support.py::SchemaWalk` forbids a conditional that reaches into array items, so
  coupling a root member to an item is not available. Both are producer rules PXAPI-19.B must
  honour, and both would be enforced by a producer-side check in that slice.
* **The five semantic-key rules are enforced by a contract-semantic layer under `tests/`, not by
  the schemas.** This was the second Remaining-truth bullet before the repair and is no longer
  merely noted: `source_id`, candidate `url_key`, selected `url_key` and exclusion `reason` are
  unique, and `selection_rank` is unique and dense. `uniqueItems` compares whole items and covers
  none of them, and the contracts say so at the members that carry the rules rather than implying
  the schema handles it. The digest projections refuse to digest an ambiguous document.
  **Equivalent producer-side enforcement is mandatory in PXAPI-19.B** and is the single largest
  carried obligation from this slice: nothing here prevents a producer from emitting a
  schema-valid document no consumer can order.
* **`public_origin` is lexical only.** It refuses a path, query, fragment and userinfo, and it
  decides nothing about DNS, reachability, redirects, egress, loopback or private ranges. A valid
  `target_origin` is not an SSRF or target-policy verdict; those remain 19.B and runtime concerns.
* **The reviewability figure roughly doubled** (`169594` → `264624`, 89% over the convention) and
  needs a Product Owner call against the new number rather than the old one. PO decision 2 of the
  repair brief directs that PR `#14` is not split on this ground; the split point is named above.
* **The `M1`–`M27` counter-mutation pass was not re-run in full on the repaired tree.** Nine of
  its mutations whose regions this repair rewrote were re-run as `R16`–`R24` and all nine bit; the
  other eighteen touch invariants and guards this repair did not change, and their original
  results are labelled historical rather than restated as current.

### Unresolved findings carried, not resolved, by this slice

* `C-PXAPI-001` — PR `#5` remains open stale legacy drift. Untouched.
* `C-PXAPI-005` — the census/sampling threshold remains `MISSING`.
* The Jira metadata defect on issue link `11503` (PXAPI-20 shown as blocking PXAPI-19, the wrong
  direction) is unchanged: no Jira mutation was in scope.

### CI on the candidate

The previous candidate's CI (`python-compat` run `34542520428`, `success` on `8887911`) tested a
tree that no longer exists and **is not evidence about this one**.

CI for the repaired candidate is recorded in the packet that accompanies this document: workflow
name, run id, the exact SHA the run tested and its conclusion, read from GitHub Actions. If no run
exists for the exact repaired SHA, the state is `MISSING` and **GREEN is not inferred**. The local
Python 3.13 and 3.14 runs above are local evidence only.

Sourcery is not waited on and its earlier rate-limited review is not treated as evidence of code
quality, per PO decision 3 of the repair brief.

### Evidence ceiling

**PXAPI-19.A proves contract/foundation implementation only.** It proves that two versioned,
provider-neutral, contract-tested artifacts exist in this repository, that their structural truth,
neutrality, provenance, digest topology and deterministic semantics are enforced by tests that
were each observed failing when the invariant was violated and passing after restoration, and that
the seven previously registered contracts are unaffected.

It also does not prove the five semantic-key relationships **of any document a producer emits**.
That layer exists and is exercised here, but it is test code: a schema-valid document that was
never run through it can still be ambiguous, and closing that is 19.B's obligation.

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
