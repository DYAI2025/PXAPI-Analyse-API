# PXK-20.B1 — Homepage Indexability Evidence Core v0

**Slice:** `PXK-20.B1` — a bounded implementation slice of Jira `PXK-20`. `PXK-20.B1` is **not**
a Jira key.
**Date:** 2026-09-08
**Authority:** the approved `PXK-20.B` split, of which only **B1** is authorised. B2 —
robots.txt and Sitemap — is **not** implemented and was **not** started.
**Revision — repair round, 2026-09-08.** Independent review accepted the B1 architecture and
raised exactly one material finding: the `X-Robots-Tag` parser treated *every* leading token
containing `:` as unresolvable, which withheld the generic verdict on well-formed field values
such as `unavailable_after: 2026-06-30, noindex` and `max-snippet: 20, none`, and on clearly
crawler-scoped rule lists such as `googlebot: follow, noindex`. That finding is repaired in
commit `b081c7d`; the sections it made stale (C, D, E, F, G, H, I, K) are re-measured below
rather than carried forward. Everything the finding did not touch is unchanged.

**Status of every claim below:** `VERIFIED_BY_AGENT_EXECUTION` unless a row says
`NOT_PROVEN`. Each verified claim is re-derivable by the command printed beside it; none has
been confirmed by independent PO or GitHub review.

**No production readiness is claimed.** No SEO diagnosis, no current Google index status, no
business-impact measurement and no customer-report readiness are claimed. See section J.

---

## A. Source baseline

| Fact | Exact value | How verified |
| --- | --- | --- |
| Repository | `DYAI2025/PXAPI-Analyse-API` | `git remote get-url origin` |
| Base `main` | `ca4d5ef514942ae52cd4f514a21aa8d3e1c8047e` | `git fetch origin main && git rev-parse origin/main` |
| Base tree | `f351e560340c8bb8cc6e855288a938b044bbfbdc` | `git rev-parse origin/main^{tree}` |
| Matches the brief's pinned SHA and tree | yes, character-identical | string comparison |
| Drift | none | no STOP condition triggered |
| Branch | `feat/pxk-20b1-homepage-indexability` | `git rev-parse --abbrev-ref HEAD` |
| Branch point | freshly verified `origin/main` | `git checkout -b … origin/main` |
| `HEAD == origin/main` at branch creation | proven, both `ca4d5ef…` | string comparison at creation |
| Baseline suite before any change | `1391 passed`, rc `0` | `uv run pytest -q` |
| `origin/main` re-checked before push | still `ca4d5ef…` | `git fetch origin main && git rev-parse origin/main` |

PR #5 was neither read as an implementation base, branched from, nor modified. The previous
`feat/pxk-20a-…` branch was not reused.

## B. Project-source cleanliness

`git status --porcelain` prints nothing after the final commit and after **every**
countermutation revert (section G). No `.gitignore` rule was added or changed.

## C. What this slice delivers

### The observable outcome

The existing single-homepage Analysis Run can now establish whether the analysed response
carried a **generically applicable `noindex` directive**, on the two channels one response can
carry it, and derives one evidence-bound finding when — and only when — that was actually
established. **No additional network request is introduced.**

The product statement is deliberately narrow:

> PXAPI can establish that a generically applicable noindex directive was observed in the
> analysed homepage response.

It does **not** claim universal real-world index status.

### Generic means "not addressed to a named crawler"

* `<meta name="robots">` is generic. `<meta name="googlebot">` is a different declaration and
  is **not collected at all**.
* An unscoped `X-Robots-Tag: noindex` is generic. `X-Robots-Tag: googlebot: noindex` is
  outside the generic verdict.

**Outside the generic verdict is a decided answer, not an unknown one.** A named-agent-only
directive makes the generic result `KNOWN false`. Nothing in this slice infers how any named
crawler behaves.

### How an `X-Robots-Tag` colon is placed

`X-Robots-Tag` uses `:` both to address a crawler and to give a rule its own value. The colon is
placed by **the name in front of it**, read against the bounded vocabulary rule version `1.0.0`
carries. For one physical field value:

| The first rule of the field value | Reading | Verdict |
| --- | --- | --- |
| carries no colon — `noindex, nofollow` | every rule is generic | `PRESENT` if any bare `noindex`/`none`, else `ABSENT` |
| names a rule in `VALUE_BEARING_RULES` — `max-snippet: 20, noindex` | the colon is that rule's own value; nobody is addressed, so the rules after it stay generic | `PRESENT` if any *subsequent* bare `noindex`/`none`, else `ABSENT` |
| names a rule in `NOINDEX_DIRECTIVES` — `noindex: yes`, `none: 1` | a rule modelled as taking no value was handed one: malformed under both readings | `INDETERMINATE` |
| has a colon with nothing before it — `: noindex` | names nobody and is no rule either | `INDETERMINATE` |
| names anything else — `googlebot: follow, noindex` | that name addresses a crawler and scopes the whole rule list on this physical value to it | `ABSENT` |

`VALUE_BEARING_RULES` is exactly `unavailable_after`, `max-snippet`, `max-image-preview`,
`max-video-preview`, compared case-insensitively and pinned as a whole set by
`test_the_value_bearing_rule_vocabulary_is_exactly_these_four_names`. It is the whole syntax
knowledge needed to place a colon — it models no rule's *meaning*, scores nothing, and is not
the beginning of a robots directive registry.

A crawler-scoped list is **outside** the generic verdict, so it makes that verdict `KNOWN false`
and infers nothing about how the named crawler behaves. `INDETERMINATE` is reserved for syntax
that genuinely is unresolvable, and is never rendered as an absence.

**The boundary of the vocabulary is a real limit, stated rather than hidden.** A colon-valued
rule this version does not know — a future `max-audio-preview: 5, noindex`, say — is read as a
crawler name and answers `ABSENT`. Teaching the parser a new rule name is version work, not
something it may guess at run time. See section K.

### Combined truth rule

| Rule | Result |
| --- | --- |
| any channel established the directive | `KNOWN true` |
| else any channel established nothing, or could not be assessed | `UNKNOWN` |
| else at least one applicable channel was assessed and found none | `KNOWN false` |
| else no channel applied | `NOT_APPLICABLE` |

A channel that **does not apply** (an HTML declaration in a response that is not a document)
does not hold the result open; a channel we **could not assess** does. That distinction is what
keeps a non-HTML response carrying a readable `X-Robots-Tag` representable without inventing an
HTML observation nobody made.

## D. Changed files, and why each changed

| File | Δ | Reason |
| --- | --- | --- |
| `src/pxapi/domain/indexability.py` | +208 / −0 | **New.** The whole noindex semantics: per-channel verdicts, the `X-Robots-Tag` colon-placement vocabulary, and the combiner. Stdlib only. |
| `src/pxapi/domain/observations.py` | +11 / −0 | The three new `Metric` members. |
| `src/pxapi/domain/findings.py` | +39 / −1 | The fourth rule, its class, its trigger and its four fixed texts. |
| `src/pxapi/ports/page_fetch.py` | +10 / −0 | `PageFetchOutcome.x_robots_tag`: a narrow, immutable tuple of field values. |
| `src/pxapi/ports/html_observation.py` | +9 / −0 | `HtmlObservations.robots_meta_contents`: the generic robots declarations. |
| `src/pxapi/adapters/web/page_fetcher.py` | +6 / −0 | Populates `x_robots_tag` from `headers.get_all`, unfolded. |
| `src/pxapi/adapters/web/html_observations.py` | +15 / −4 | Collects every generic robots meta; the description branch is restructured, not changed in behaviour. |
| `src/pxapi/application/analyze_homepage.py` | +74 / −0 | Records the three metrics, and owns the truncation rule for the document channel. |
| `README.md` | +26 / −4 | The rule set is four, not three; how indexability is observed; and how a colon is placed. |
| `tests/domain/test_indexability.py` | +353 / −0 | **New.** 99 tests over the two channels, the colon-placement vocabulary and the combiner. |
| `tests/domain/test_findings.py` | +58 / −2 | R4 pinned into the rule set, its metric, class and exact v1 texts. |
| `tests/application/test_derive_findings.py` | +98 / −1 | R4 derivation, and R4 added to the exhaustive neutrality matrix. |
| `tests/application/test_analyze_homepage.py` | +447 / −0 | The whole path, on real sockets: both channels, every combined case, the finding and its chain. |
| `tests/adapters/test_html_observations.py` | +63 / −3 | The reader's robots-meta behaviour. |
| `tests/adapters/test_page_fetcher.py` | +81 / −0 | Repeated header lines surviving a real HTTP exchange. |
| `tests/adapters/http_test_server.py` | +6 / −0 | `Route.repeated_headers` — a dict cannot express a repeated field name. |
| `tests/test_package_scaffold.py` | +1 / −0 | `domain/indexability.py` added to `BEHAVIOR_ALLOWED`, attributed to `PXK-20.B1`. |

| `docs/evidence/PXK-20B1-…-evidence-core.md` | this file | **New.** This evidence document. |

**Unexpected files: none.** Three files added (`indexability.py`, its test module and this
document), fifteen modified. Verify with `git diff --numstat ca4d5ef...HEAD`.

## E. Exact metric IDs, rule identity and semantics

### Metrics — all `MeasurementRecord` documents under the existing contract

| `metric_id` | Semantics |
| --- | --- |
| `META_ROBOTS_GENERIC_NOINDEX_PRESENT` | `BOOLEAN`. A generic noindex directive was observed in the document's `<meta name="robots">` declarations. `UNKNOWN` when the read was truncated without one; `NOT_APPLICABLE` when the response is not a document; `NOT_ASSESSED / RUNTIME_ERROR` when we could not decode or parse it. |
| `X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT` | `BOOLEAN`. The same, on the response's `X-Robots-Tag` field values. `UNKNOWN` only where the syntax is genuinely unresolvable — a colon with no name before it, or `noindex`/`none` handed a value. A crawler-scoped rule list is `KNOWN false`; a generic rule carrying its own value leaves the rules after it generic. |
| `HOMEPAGE_GENERIC_NOINDEX_PRESENT` | `BOOLEAN`. The combined result, by the rule in section C. The only metric R4 reads. |

### Rule

| Field | Value |
| --- | --- |
| `rule_id` | `HOMEPAGE_EXPLICIT_NOINDEX` |
| `rule_version` | `1.0.0` |
| `finding_class` | `HOMEPAGE_GENERIC_NOINDEX_DIRECTIVE` |
| decisive metric | `HOMEPAGE_GENERIC_NOINDEX_PRESENT` |
| trigger | performed, `result_state == KNOWN`, `value_type == BOOLEAN`, `boolean_value is True` |

### No contract change was needed

`metric_id`, `rule_id` and `finding_class` are open `code` tokens
(`^[A-Z][A-Z0-9_]+(?!\n)$`, `maxLength` 64). All five new tokens and all four product texts
were checked against the registered schemas before implementation: the longest token is 36
characters and the longest text 192 of the 500 `single_line_text` characters. **No schema, no
manifest and no dependency change** — verified as an empty diff over `contracts/`,
`pyproject.toml` and `uv.lock` (section H).

## F. Evidence chain, and representative examples

Produced by running the real analyzer against a controlled loopback server. Contract validation
of each emitted finding through the production registry: `PASS`.

### Example A — HTML generic noindex (`<meta name="robots" content="noindex">`)

```text
META_ROBOTS_GENERIC_NOINDEX_PRESENT    KNOWN     value=True
X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT   KNOWN     value=False
HOMEPAGE_GENERIC_NOINDEX_PRESENT       KNOWN     value=True

finding_id   id-0030   rule=HOMEPAGE_EXPLICIT_NOINDEX v1.0.0
  -> evidence_id     id-0028   (KNOWN)
    -> measurement_id  id-0014   metric=HOMEPAGE_GENERIC_NOINDEX_PRESENT
       result_state    KNOWN
       value           {"value_type": "BOOLEAN", "boolean_value": true}
       source_url      http://127.0.0.1:57085/
```

### Example B — unscoped `X-Robots-Tag: noindex`

```text
META_ROBOTS_GENERIC_NOINDEX_PRESENT    KNOWN     value=False
X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT   KNOWN     value=True
HOMEPAGE_GENERIC_NOINDEX_PRESENT       KNOWN     value=True
finding: HOMEPAGE_EXPLICIT_NOINDEX, texts byte-identical to Example A
```

The directive arrived on a different channel and the four product texts are **byte-identical**.
That is the no-interpolation property, asserted in
`test_two_different_declarations_produce_byte_identical_finding_texts`.

### Example C — named-agent-only counterexample (`X-Robots-Tag: googlebot: noindex`)

```text
META_ROBOTS_GENERIC_NOINDEX_PRESENT    KNOWN     value=False
X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT   KNOWN     value=False
HOMEPAGE_GENERIC_NOINDEX_PRESENT       KNOWN     value=False
finding: (none emitted)
```

`KNOWN false`, **not** `UNKNOWN`. This is the correction the brief required.

### Example D — unresolvable syntax (`X-Robots-Tag: noindex: yes`)

```text
META_ROBOTS_GENERIC_NOINDEX_PRESENT    KNOWN     value=False
X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT   UNKNOWN   value=(no result member)
HOMEPAGE_GENERIC_NOINDEX_PRESENT       UNKNOWN   value=(no result member)
finding: (none emitted)
```

`false + unknown` is `unknown`. Nothing is claimed about the site. `noindex` takes no value, so
this is malformed however it is read — and it must not quietly become a crawler named `noindex`.

### Example E — a generic rule carrying its own value (`X-Robots-Tag: max-snippet: 20, noindex`)

```text
META_ROBOTS_GENERIC_NOINDEX_PRESENT    KNOWN     value=False
X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT   KNOWN     value=True
HOMEPAGE_GENERIC_NOINDEX_PRESENT       KNOWN     value=True
finding_id   id-0030   rule=HOMEPAGE_EXPLICIT_NOINDEX v1.0.0
  -> evidence_id     id-0028   (KNOWN)
    -> measurement_id  id-0014   metric=HOMEPAGE_GENERIC_NOINDEX_PRESENT
       result_state    KNOWN
       value           {'value_type': 'BOOLEAN', 'boolean_value': True}
       source_url      http://127.0.0.1:51704/
```

This is the repaired case: the field value is well formed, `max-snippet` addresses no crawler,
and the `noindex` beside it is generically applicable. Before the repair all three records read
`UNKNOWN` and no finding was emitted.

### Example F — a crawler-scoped rule list (`X-Robots-Tag: googlebot: follow, noindex`)

```text
META_ROBOTS_GENERIC_NOINDEX_PRESENT    KNOWN     value=False
X_ROBOTS_TAG_GENERIC_NOINDEX_PRESENT   KNOWN     value=False
HOMEPAGE_GENERIC_NOINDEX_PRESENT       KNOWN     value=False
finding: (none emitted)
```

`KNOWN false`, not `UNKNOWN`: the whole list is addressed to `googlebot`, so this response
declared nothing *generic*. Before the repair the header channel read `UNKNOWN`. Nothing is
inferred about how `googlebot` actually behaves.

### Failure counterexample

For every one of the seven `FetchFailureKind` values, all three indexability records carry
`{"not_assessed_reason": …}` and **no** `result` member, and no finding is emitted —
`test_a_fetch_failure_makes_no_claim_about_indexing_at_all`. A technical failure never becomes
a negative website fact.

## G. Countermutations

Each mutation was applied alone, its presence verified with `grep` before the run, the full
suite run, and the file reverted with `git checkout --` before the next. After every revert all
markers were re-counted at **0 files**, the mutated file's `sha256` was compared against the
pre-mutation value, and `git status --porcelain` was **empty** — so no mutation stacked on
another, none left residue, and no revert silently failed.

Mutations **1a–1d** were re-run against the *repaired* parser, because the repair changed
exactly the seam mutation 1 covered; carrying the pre-repair row forward would have cited test
names that no longer exist. Mutations 2–5 were **not** re-run: the repair touched only
`domain/indexability.py`, `README.md` and two test modules
(`git diff --name-only b081c7d^..b081c7d`), so the combiner, truncation, trigger, evidence-chain
and no-interpolation seams they cover are byte-identical to what those rows measured.

| # | Mutation | Site | rc | Representative tests that turned RED |
| --- | --- | --- | --- | --- |
| 1a | **The repair undone**: the pre-repair "every colon is ambiguous" reading restored — the two readings are compared instead of being placed by name | `domain/indexability.py` | 1 | 9 of `test_a_generic_rule_carrying_a_value_leaves_the_rules_after_it_generic` (`unavailable_after: 2026-06-30, noindex`, `max-snippet: 20, noindex`, `max-image-preview: large, none`, `max-video-preview: -1, noindex`, `max-snippet: 20, none`, and the case variants); 5 named-agent rule lists in `test_a_field_value_with_no_generic_noindex_establishes_its_absence` (`googlebot: follow, noindex`, `otherbot: follow, none`, `googlebot: nosnippet, noarchive, none`, `GoogleBot: Follow, NoIndex`, `googlebot: unavailable_after: 2026-06-30, noindex`); `test_an_unrecognised_name_before_a_colon_is_read_as_a_crawler_scope`; `test_joining_repeated_headers_destroys_an_established_directive[lines0-ABSENT]`; `test_a_generic_rule_carrying_a_value_reaches_the_finding_end_to_end`; `test_a_rule_list_scoped_to_one_named_crawler_is_a_decided_absence_end_to_end` (**18 failed, 1585 passed**) |
| 1b | The named-crawler branch removed, so every unknown name before a colon is read as a value-bearing rule | `domain/indexability.py` | 1 | the same 5 named-agent rule lists; `test_an_unrecognised_name_before_a_colon_is_read_as_a_crawler_scope`; `test_joining_repeated_headers_destroys_an_established_directive[lines0-ABSENT]`; `test_a_rule_list_scoped_to_one_named_crawler_is_a_decided_absence_end_to_end`; `test_nothing_short_of_an_established_directive_emits_the_finding[named-agent-rule-list]` (**9 failed, 1594 passed**) |
| 1c | The malformed-known-directive branch dropped, so `noindex: yes` silently becomes a crawler named `noindex` | `domain/indexability.py` | 1 | the 6 malformed-known-directive `test_genuinely_unresolvable_syntax_establishes_nothing` cases; `test_an_ambiguous_line_beside_a_clear_one_does_not_erase_the_clear_one`; `test_joining_repeated_headers_destroys_an_established_directive[lines1-INDETERMINATE]`; `test_an_ambiguous_header_establishes_nothing_rather_than_an_absence`; `test_an_established_directive_outweighs_an_ambiguous_channel` (**10 failed, 1593 passed**) |
| 1d | The empty-scope branch dropped, so `: noindex` becomes a crawler with no name | `domain/indexability.py` | 1 | `test_genuinely_unresolvable_syntax_establishes_nothing[: noindex]` and `[:noindex]` (**2 failed, 1601 passed**) |
| 2a | The combiner's blind-channel rule dropped, so `UNKNOWN`/`UNASSESSED` falls through to an absence | `domain/indexability.py` | 1 | `test_a_channel_our_process_could_not_assess_never_becomes_an_absence`; `test_a_body_we_could_not_decode_leaves_the_document_channel_unassessed`; `test_a_parser_failure_leaves_the_document_channel_unassessed`; `test_a_truncated_read_never_establishes_the_absence_of_a_declaration` |
| 2b | The truncation rule dropped, so a read stopped at our byte bound reports an absence | `application/analyze_homepage.py` | 1 | `test_a_truncated_read_never_establishes_the_absence_of_a_declaration` (1 failed, 1577 passed) |
| 3 | R4's trigger inverted (`is True` → `is False`) | `domain/findings.py` | 1 | `test_a_generic_noindex_observed_as_present_fires_r4`; `test_an_observed_generic_noindex_becomes_exactly_one_finding`; `test_nothing_short_of_an_established_directive_emits_the_finding[no-declaration, index-follow, named-agent-only, not-a-document]`; `test_a_healthy_https_response_produces_no_finding_at_all` |
| 4 | The evidence chain bypassed: any evidence reaches any measurement in the run | `application/derive_findings.py` | 1 | `test_a_finding_cannot_rest_on_a_dangling_measurement_reference[generic-noindex]` and its 3 siblings; `test_evidence_that_references_a_different_measurement_produces_no_finding[generic-noindex]` and its 3 siblings; `test_the_noindex_finding_resolves_back_to_the_combined_measurement` (15 failed) |
| 5 | The decisive value and observation context interpolated into `finding_summary` | `application/derive_findings.py` | 1 | `test_two_different_declarations_produce_byte_identical_finding_texts`; `test_a_teapot_and_an_unavailable_service_read_identically` (2 failed) |

Mutation 2 was split into **2a** (the combiner) and **2b** (the truncation rule) because a
single mutation would have left one of the two branches unproven. Mutation 1 was split into
**1a–1d** for the same reason: the repaired `_field_value_generic_noindex` has four decision
branches after a colon is found, and 1a alone would have left 1c's and 1d's unproven — 1a
happens to keep `: noindex` and `noindex: yes` at `INDETERMINATE` by a different route.

**Which branches these four mutations cover.** `_field_value_generic_noindex` has six branches;
1a–1d mutate the four that decide what a colon means — value-bearing rule, malformed known
directive, empty scope, and crawler scope. The two the repair did not change — no colon at all,
and a field value with no directive in it — were **not** re-mutated in this round; they are
asserted by `test_an_unscoped_noindex_field_value_establishes_the_generic_directive` and by
`test_a_field_value_with_no_generic_noindex_establishes_its_absence["", "   ", ",,,"]`.

## H. Gates

| Gate | Command | Result |
| --- | --- | --- |
| Lockfile | `uv lock --check` | rc `0`, `Resolved 29 packages` |
| Lint | `uv run ruff check .` | rc `0`, `All checks passed!` |
| Format | `uv run ruff format --check .` | rc `0`, `63 files already formatted` |
| Full suite, Python **3.13.3** | `uv run --python 3.13 --frozen pytest -q` | **`1603 passed`**, rc `0` |
| Full suite, Python **3.14.6** | `uv run --python 3.14 --frozen pytest -q` | **`1603 passed`**, rc `0` |
| Architecture + scope gates | `uv run pytest tests/architecture tests/test_package_scaffold.py tests/test_closed_vocabularies.py tests/contracts -q` | `631 passed`, rc `0` |
| Dependency diff | `git diff --stat origin/main...HEAD -- pyproject.toml uv.lock` | empty |
| Contract diff | `git diff --stat origin/main...HEAD -- contracts/` | empty |
| CI-config diff | `git diff --stat origin/main...HEAD -- .github/` | empty |

Baseline `1391` → `1578` before the repair → **`1603`** after it: **+212 tests**, of which the
repair round added **+25**. No warning was suppressed and no failing exit code was hidden; the
two `pytest` warnings are the pre-existing Starlette/anyio deprecations inherited from `main`,
both raised inside `.venv/…/fastapi/testclient.py` and `.venv/…/starlette/testclient.py` and
neither introduced by this slice.

### Gates this slice tripped, and how each was widened

Each is the scope gate working, and each was widened as a reviewable edit rather than bypassed:

* `test_only_authorised_modules_declare_behavior` — `domain/indexability.py` added to
  `BEHAVIOR_ALLOWED`, attributed to `PXK-20.B1`.
* `test_the_rule_set_is_exactly_the_…_rules_in_the_pinned_order`, `EXPECTED_METRIC`,
  `EXPECTED_CLASS`, `EXPECTED_TEXTS` — R4 pinned, with its four texts quoted verbatim.
* `test_the_neutrality_matrix_is_not_empty` — `len(RULES) == 3` → `== 4`.
* `test_every_rule_emits_a_finding_that_satisfies_the_registered_contract` — the new
  triggering fact added to `TRIGGERING_FACTS`, so the exhaustive neutrality matrix now covers
  R4 across every `not_assessed_reason` and every non-`KNOWN` result state.
* `test_a_healthy_https_response_produces_no_finding_at_all` — `x_robots_tag` is required on
  `PageFetchOutcome` on purpose: a default of `()` would let a construction site that forgot it
  silently state that the site declared nothing.

`tests/test_closed_vocabularies.py` needed **no** edit: this slice declares no new closed
vocabulary in any schema.

## I. Reviewability

| Measure | Value |
| --- | --- |
| Changed files | 18 (3 added, 15 modified) |
| Insertions / deletions | +1822 / −15 |
| Diff size, excluding this document | **87,097 bytes** (`git diff ca4d5ef...HEAD -- . ':(exclude)docs/evidence' \| wc -c`) |
| Diff size, including this document | **107,059 bytes** (`git diff ca4d5ef...HEAD \| wc -c`) |
| Source vs. test split | 372 source lines, 1,107 test lines, 26 README lines |

The pre-repair rows read 17 files / +1357 / 79,280 bytes; that byte count excluded this
document, which had not yet been committed when it was measured. The comparable figure after
the repair is the 87,097-byte row.

Substantially smaller than the combined B1+B2 slice that was split for exceeding the
reviewability budget. B1 absorbed no robots.txt or Sitemap work.

## J. Scope boundaries — verified, not merely asserted

| Out of scope | Verification |
| --- | --- |
| robots.txt, `/robots` URL construction, robots parser, user-agent group evaluation | `grep -rniE "robots\.txt\|/robots\|user-agent group\|crawl-delay\|disallow" src/ tests/` → **no match** |
| Sitemap extraction, fetching, retention limit | `grep -rni "sitemap" src/ tests/` → **no match** |
| A second network request | `grep -rn "\.fetch(" src/` → exactly **one** call site, `analyze_homepage.py:182`; connections are opened only in `page_fetcher.py` |
| New contract family, schema, manifest change | `git diff --stat origin/main...HEAD -- contracts/` → empty |
| New dependency | `pyproject.toml` and `uv.lock` diffs empty |
| Score, ProductDiagnosis, ContextualDiagnosis, Business Context, LLM, SERP, performance, accessibility, persistence, queue, deployment | no such module, metric or rule exists; `test_only_authorised_modules_declare_behavior` would fail if one appeared |
| Jira / Confluence mutation, deployment, secrets | none performed |
| PR #5 | not read as a base, not branched from, not modified, not closed |

**B2 was not started.** No robots.txt or Sitemap abstraction was pre-built, and no B2 metric
was pre-created "for later".

## K. What this slice does not prove — `NOT_PROVEN`

* **Current index status.** A directive observed in one response is not evidence that any
  search engine has excluded, will exclude, or has ever indexed the page.
* **Crawler behaviour.** Whether any crawler respects the directive is not observed anywhere in
  this chain, and named-crawler behaviour is deliberately not inferred.
* **Business impact.** No revenue, traffic, ranking or conversion effect is measured.
* **Full robots semantics.** Only `noindex` and `none` are *modelled*. Four further names are
  known as syntax only — `unavailable_after`, `max-snippet`, `max-image-preview`,
  `max-video-preview` — solely so a colon can be placed; their meanings are not modelled, and
  `nofollow`, `noarchive`, `nosnippet` and the rest are parsed as directives and then ignored.
* **A colon-valued rule outside that vocabulary is read as a crawler name.** This is the
  bounded vocabulary's cost, and it is a *false absence* rather than a withheld verdict: a
  future `max-audio-preview: 5, noindex` would answer `KNOWN false`, not `UNKNOWN`. Accepted
  deliberately for rule version `1.0.0` — the alternative, treating every unknown colon as
  unresolvable, is the finding this round repaired. Adding a name is version work, and
  `test_the_value_bearing_rule_vocabulary_is_exactly_these_four_names` makes it visible.
  `test_an_unrecognised_name_before_a_colon_is_read_as_a_crawler_scope` asserts the limit.
* **A malformed non-noindex directive is read as a crawler name.** `nofollow: yes, noindex`
  answers `ABSENT`, because only `noindex` and `none` are known as taking no value. Widening
  that set would be the robots ontology this slice does not build.
* **Doubly-nested scoping.** `googlebot: unavailable_after: <date>, noindex` answers `ABSENT`:
  the first name addresses a crawler, so the whole list is scoped. Nothing is inferred about
  that crawler.
* **Real-internet behaviour.** Every test in this slice runs against a controlled loopback
  server. No live smoke against a public site carrying a real `X-Robots-Tag` was run.
* **CI.** Not observed at the time of writing; see the PR for the run bound to its head SHA.
* **Review.** No PO, reviewer or GitHub check has confirmed anything above.

### Observed, unresolved

A transient `Traceback` was printed once to stderr by the loopback test server during a
combined adapter run. It did not reappear in three subsequent runs of that same selection, nor
in three runs of the fetcher file alone; it failed no assertion and the exit code stayed `0`. It is consistent with a client closing a
socket mid-write — the fetcher sends `Connection: close` and reads only to its byte bound —
and is **not** claimed to be fixed or fully diagnosed.
