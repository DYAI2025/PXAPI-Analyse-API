# PXAPI-20.A — Static Page Evidence Foundation

**Slice:** `PXAPI-20.A`, the first of the two sequential PR candidates of Jira `PXAPI-20`
(`D-20-K` / `D-PXAPI20-PO-012`). **Neither this candidate's merge nor its green gates make
`PXAPI-20` Done.**

**Exact base:** `19a9a855d603384c216bbf9ab92e4e7cb0334bfb` — `origin/main`, read live before the
first mutation. `git rev-parse origin/main` and the branch point agree.

**Authority, all read live on 2026-09-19:**

| Source | What it bound |
| --- | --- |
| Jira `PXAPI-19` comment `16257` | PXAPI-19 final closeout: `Erledigt`, final SHA `19a9a855…`, post-merge `main` CI run `35414652333` success on both interpreters |
| Jira `PXAPI-20` comment `16258` | `PRE_IMPLEMENTATION` reconcile; canonical `main`; `PLAN_REQUIRED_STOP` before code |
| Jira `PXAPI-20` comment `16259` | Product Owner plan review: **APPROVED WITH BOUNDED AMENDMENTS**; `Delivery Ready = GREEN`; decisions `D-20-A` … `D-20-P` |
| Jira `PXAPI-20` status | `In Arbeit`, `Highest`, WIP = PXAPI-20 only |
| Confluence `54362115` | Acquisition / Site Intelligence target architecture, `ACCEPTED` |
| Confluence `55181314` | DRS gate semantics, `CURRENT` |

**DRS at this candidate:** `definition_state = DRS_DEFINITION_READY`; `IC` / `R2G` / `R4M` are
Orchestrator and Product Owner authority (`D-20-M`) and are **not** declared here. Nothing green
is inherited from PXAPI-19.

## 1. Start state

| Check | Measured |
| --- | --- |
| `origin/main` | `19a9a855d603384c216bbf9ab92e4e7cb0334bfb` |
| working tree before the first mutation | `git status --porcelain` → **0** lines |
| base vs. the previous implementation baseline `bfe06cc` | `git diff --quiet bfe06cc 19a9a855 -- src tests contracts/v1 pyproject.toml uv.lock .github` → **rc 0**; the six differing files are `contracts/README.md`, the three `docs/context/` files and the two PXAPI-19 closeout evidence artifacts |
| main CI on the base | run `35414652333`, `python-compat`, `push`, headSha `19a9a855…`, conclusion `success`; `py3.14` job `success` |
| suite on the base | **2876 passed, 1 skipped** on CPython 3.13.3 (the skip is the opt-in PXAPI-19 real-boundary smoke) |
| lint on the base | `ruff check` clean; `ruff format --check` clean on 102 files; `uv lock --check` clean |

No stop condition fired: `origin/main` matched the bound base, `PXAPI-20` was `In Arbeit`,
comment `16259` was present and is the most recent comment on the issue, no protected file had
to change, no contract version had to change, no dependency was needed, and the only other open
PR is the stale legacy `#5` (`C-PXAPI-001`), which this candidate neither merges nor rebases.

## 2. Governance reconcile — the first commit

`D-20-N` requires the reconcile as the branch's first commit rather than another docs-only PR.
Commit `3ae23166a2b353058a31dda68672ea42c9c23aa9`, documentation only.

- `docs/context/project-state.md`: execution mode, implementation baseline, code truth, the
  PXAPI-19 ticket-level closeout, a new *PXAPI-20 authorization and delivery shape* section, the
  delivery sequence, `AD-003`, the follow-up list (`F-4`, `F-5`) and the Jira focus.
- `docs/context/decision-ledger.md`: seventeen new rows — `D-PXAPI20-PO-001` (Delivery Ready) and
  `-002` … `-017` mapping one to one onto `D-20-A` … `D-20-P`, each citing comment `16259`.
  `D-PXAPI19-PO-011` and `-012` no longer say "not yet recorded in Jira"; comment `16257` is
  that record, and the prior state of both rows is preserved in the closing note.
- `docs/context/contradiction-ledger.md`: three new rows (`C-PXAPI-018` … `C-PXAPI-020`, section
  10), plus `C-PXAPI-001`, `C-PXAPI-007` and `C-PXAPI-008` re-scoped with their prior wording
  preserved verbatim.

**No historical evidence is rewritten and no row is deleted.** Every re-scoped statement keeps its
earlier text as *"Prior wording … preserved"*. The stale-claim sweep
(`grep -n "not authorized\|NOT AUTHORIZED\|not yet recorded in Jira" docs/context/*.md`) reports
**one** hit after the reconcile, and it is inside the sentence that records the discharged
condition set as history.

## 3. What the candidate built, and what it deliberately did not

| Built | Where |
| --- | --- |
| `page-acquisition-record.v1`: schema, 3 examples, registry entry, 14 invalid fixtures, 5 closed-vocabulary pins | `contracts/v1/**`, `tests/contracts/**`, `tests/test_closed_vocabularies.py` |
| The acquisition vocabulary, the contract-URL predicate, the body digest, the withhold rule, 11 producer invariants | `src/pxapi/domain/page_acquisition.py` |
| An isolated generic static-page observer | `src/pxapi/application/observe_static_page.py` |

Not built, deliberately: no `AnalyzeSite`, no iteration over manifest selections, no multi-page
fetching, no CLI, no HTTP endpoint, no composition wiring — **nothing calls the observer and no
page is fetched by any code on this branch**; no real-boundary multi-page smoke; no customer
report; no findings; no scoring; no browser or Crawl4AI; no queue or PostgreSQL; no ArtifactStore;
no concurrency; no retries; no automatic business synthesis. Those are `20.B` or later.

## 4. Contract reuse result

| Contract | Decision | Evidence |
| --- | --- | --- |
| `measurement-record.v1` | reused **unchanged** | `git diff --quiet 19a9a855 HEAD -- contracts/v1/schemas/measurement-record.v1.json` → rc 0 |
| `website-evidence.v1` | reused **unchanged** | same check, rc 0 |
| `site-inventory.v1`, `sampling-manifest.v1` | reused unchanged, consumed as bound input | same check, rc 0 |
| the other eight existing schema files | unchanged | same check over all twelve, rc 0 |
| `page-acquisition-record.v1` | **new, the only new contract** | registry entry +14 lines, 0 deletions |

**Net: 1 new contract, 0 new versions of an existing contract, 0 new shared definitions, 0 new
ports, 0 new dependencies.** `D-20-B` is satisfied without versioning either carrier of the
evidence chain: page identity is recovered by following `measurement_refs` in the other direction
— `website-evidence.measurement_refs → measurement_id → the one acquisition record naming it →
url_key, manifest ref and output digest, method and version, run`.

## 5. The contract

Twenty members, twelve always required, three root conditionals, root closed. The conditional
rules, the `observation_mode` vocabulary, the derived `100..999` status bounds, the never-emitted
`raw_artifact_ref` and the withhold rule are described in `contracts/README.md`, *The page
acquisition record*, which this document does not restate.

Three registered examples: `response-received` (registered **first**, because the generic
versioning matrix runs on the first example, and it carries every conditional member),
`timeout`, `measurements-withheld`. The withheld example carries a **real** instance of
`C-PXAPI-020` — a 2048-character `url_key` with a 250-character authority, valid as an acquisition
identity and refused by `common url` — rather than a shortened stand-in, and a test asserts exactly
that, so the example cannot quietly stop demonstrating the case it exists for.

No registered example carries a `raw_artifact_ref`, and a test enforces that. Its *permissibility*
on a received response is proved by a test that constructs one, so the later slice that does retain
an artifact needs no new contract version.

Fourteen focused invalid fixtures, one mutation each, each with a structural `(pointer, keyword)`
expectation: the response group in both directions, the digest pairing in both directions, the
withheld pairing in both directions, an unknown observation mode, a `BROKEN_PAGE` outcome, a status
of 1000, a credential-bearing `url_key`, a duplicated measurement reference, an inlined body with
headers, and a record carrying polarity, score and severity.

### 5.1 `F-20A-R4M-001` — contract authority drift, repaired

The first candidate declared `observation_mode` as `const: "STATIC_HTTP"` and said in prose that a
rendered observation would need a later contract version. The independent `R4M` review (Jira
`PXAPI-20` comment `16325`, 2026-09-20) found that this silently changed the accepted contract
topology, and re-reading the authority confirms it. Confluence `54362115` — version 1, created
2026-09-09, unchanged — states under §7 *TARGET new contracts*, for
`page-acquisition-record.v1`:

> `observation_mode = STATIC_HTTP | RENDERED_BROWSER`

and `D-PXAPI-ACQ-005` defines the two as separate observation modes with their own method and tool
provenance. §6 puts them on the *same* record: Pipeline C emits `PageAcquisitionRecord(STATIC_HTTP)`
and Pipeline D emits `PageAcquisitionRecord(RENDERED_BROWSER)`.

`D-20-C` (Jira comment `16259`) authorises the PXAPI-20 **producer** to support `STATIC_HTTP` and
forbids implementing `RENDERED_BROWSER`. It has no authority over the shared contract's vocabulary,
and the first candidate conflated the two.

**Repaired by separating them, and by proving they are separate:**

| Layer | After the repair |
| --- | --- |
| contract | `observation_mode` is an `enum` of exactly `STATIC_HTTP` and `RENDERED_BROWSER` — the authority's own set |
| producer | `record_declares_this_producer` still requires `observation_mode == STATIC_HTTP`, unchanged |
| proof | a record changed only to `RENDERED_BROWSER` validates against the registry **and** fires exactly that one producer rule |

No rendered transport member, no `RenderedPagePort`, no browser or Crawl4AI dependency, no provider
field and no new contract version were added: the minimum semantics the authority states are
sufficient for both modes at this architectural level, and the repair is confined to the vocabulary
and the wording around it.

RED before the schema changed: nine assertions, namely
`test_the_contract_admits_every_authoritative_observation_mode[RENDERED_BROWSER]`, five
`test_the_contract_refuses_a_mode_outside_the_authoritative_vocabulary[…]` cases (they reported
`const` where `enum` is now required), `test_the_contract_vocabulary_is_wider_than_what_this_producer_emits`,
`test_a_rendered_record_is_contract_valid_and_still_refused_by_this_producer` and
`test_this_producer_s_own_mode_is_one_the_contract_declares` (`KeyError: 'enum'`). The static half
of the first test was green throughout, which is the point: nothing about the producer changed.

The invalid fixture that proved a rendered mode was refused is replaced rather than deleted:
`observation-mode-rendered` becomes `observation-mode-unknown`, carrying `HEADLESS_BROWSER` and
expecting `('/observation_mode', 'enum')`, so the vocabulary still has a negative case. The
closed-vocabulary pin moves from `#/properties/observation_mode/const` to `…/enum` and is a
**literal** two-token list rather than a value derived from the Domain — deriving it would collapse
the very distinction the repair exists to keep, because the Domain holds what *this producer*
observes with and the second token has no producer at all.

`D-PXAPI20-PO-004` in the decision ledger keeps its prior wording as preserved text and records the
supersession. One neighbouring statement is deliberately **not** changed: `D-20-I` says a provider
member may be added in a future contract version if rendered or third-party acquisition proves it
necessary. That is about *provenance fields* and not about the mode vocabulary, it is the Product
Owner's own decision, and it remains true — §7 lists "method/tool/provider/version provenance"
while v1 carries method and version only, under that decision.

## 6. The static-page observer

A **separate path**, not an extraction: `D-20-E` keeps `AnalyzeHomepage` byte-identical and prefers
a small intentional duplication. The duplication is bounded to the observation logic; the metric
vocabulary, the text representability rule, the generic-noindex channels and the fetch port's
outcome shapes are all reused. A test parses the module's own AST and asserts it imports nothing
from `pxapi.application`.

Four deliberate differences from the homepage profile:

1. **Thirteen metrics, not fourteen.** `HOMEPAGE_GENERIC_NOINDEX_PRESENT` exists so a homepage
   finding rule can read one combined value; no page rule exists. A test asserts the page set is a
   *proper subset* of the homepage set and that the difference is exactly that one token. **No new
   metric id is invented.**
2. **A canonical link is resolved strictly.** A value the URL parser refuses and a value no
   measurement carrier can hold both become `UNKNOWN`, while `CANONICAL_PRESENT` stays `KNOWN true`
   — a page that declares a canonical did declare one. This contains the `C-PXAPI-018` input class
   **for pages** and makes no claim about the homepage path.
3. **A URL value is bounded by the URL contract, not by the text bound.** This is the one
   behavioural divergence the candidate introduces; it is measured in section 9.
4. **A page whose own identity or final URL is unrepresentable is withheld whole:** no
   measurements, no evidence, `document_status = WITHHELD`, reason stated.

## 7. Files changed

33 files: 3 modified governance documents (`docs/context/`), 2 modified documentation files
(`README.md`, `contracts/README.md`), 1 new evidence document, 5 new/modified contract files, 2 new
source modules, 3 new test modules, 15 new fixture files, 2 modified test modules.

```text
A contracts/v1/examples/page-acquisition-record.measurements-withheld.example.json
A contracts/v1/examples/page-acquisition-record.response-received.example.json
A contracts/v1/examples/page-acquisition-record.timeout.example.json
M contracts/v1/manifest.json
A contracts/v1/schemas/page-acquisition-record.v1.json
M contracts/README.md
M README.md
M docs/context/contradiction-ledger.md
M docs/context/decision-ledger.md
M docs/context/project-state.md
A docs/evidence/PXAPI-20A-static-page-evidence-foundation.md
A src/pxapi/application/observe_static_page.py
A src/pxapi/domain/page_acquisition.py
A tests/application/test_observe_static_page.py
A tests/contracts/test_page_acquisition_record.py
A tests/contracts/fixtures/invalid/page-acquisition-record/… (14 cases + expectations.json)
A tests/domain/test_page_acquisition.py
M tests/test_closed_vocabularies.py
M tests/test_package_scaffold.py
```

## 8. Protected-scope diff check

`git diff --quiet 19a9a855d603384c216bbf9ab92e4e7cb0334bfb HEAD -- <path>` for each path:

| Path | rc |
| --- | --- |
| `src/pxapi/application/analyze_homepage.py` | **0** |
| `src/pxapi/application/derive_findings.py` | **0** |
| `src/pxapi/application/discover_site.py` | **0** |
| `src/pxapi/adapters/web` | **0** |
| `src/pxapi/ports` | **0** |
| `src/pxapi/config` | **0** |
| `src/pxapi/adapters/contracts` | **0** |
| `src/pxapi/adapters/composition.py` | **0** |
| `src/pxapi/adapters/inbound` | **0** |
| `pyproject.toml` | **0** |
| `uv.lock` | **0** |
| `.github` | **0** |
| `oracle` | **0** |

`git diff --name-only 19a9a855 HEAD -- src/pxapi/domain` lists exactly one path, and it is the new
`page_acquisition.py`: no existing domain module changed. The twelve existing schema files are a
0-byte diff. **No fetch limit, discovery limit, homepage CLI, HTTP API, async or deployment
behaviour changed, and no scoring or findings logic exists to change.**

## 9. The one declared behavioural divergence

The homepage profile gates every observed value on the 500-character `single_line_text` bound, URL
values included. A `url_value` is carried by `common#/$defs/url`, whose bound is 2048.

Measured at this base through both shipped paths, on a 600-character canonical, both documents
validating against the merged registry:

| Path | `CANONICAL_URL` assessment | value |
| --- | --- | --- |
| `AnalyzeHomepage` | `OBSERVED` / **`UNKNOWN`** | none carried |
| `StaticPageObserver` | `OBSERVED` / **`KNOWN`** | 600 characters |

Recording `UNKNOWN` for a value the contract can hold is a *false* `UNKNOWN` — a statement that we
established nothing about a value we established perfectly well — which is the class of defect this
repository exists to prevent. The page path therefore takes the URL contract's own bound. The
divergence is **page-only**, the homepage path is byte-identical, and the test that pins it says so
in its docstring. It is declared here rather than left for a reviewer to discover.

## 10. New findings, none repaired here

Each was re-measured against this exact base rather than inherited from the plan that first
reported it, and each is ledgered rather than fixed.

| Ledger | Finding | Barred from repair by |
| --- | --- | --- |
| `C-PXAPI-018` / `F-4` | Site-controlled canonical and redirect input drives the shipped homepage producer into contract-invalid output or into a `ValueError` out of `run()`. Measured: `H1` (`href="/a b"`) 1 invalid document; `H3` (`HTTP://…` on an https page) 1; `H5` (final URL `…/x#a b`) **13 of 14** measurements and 25 of 32 envelope documents invalid; `H2` (`href="http://["`) raises `ValueError: Invalid IPv6 URL`. | `D-20-E` |
| `C-PXAPI-019` / `F-5` | `HTMLParser.close()` is quadratic on CPython 3.13.3: 64 KB of `"<a"` takes **4.3949 s** and 64 KB of `"<a b="` takes **23.8094 s**, against **0.0008 s** and **0.0051 s** on 3.14.6. | `D-20-L` |
| `C-PXAPI-020` | `acquisition#/$defs/public_url` and `common#/$defs/url` do not contain each other: a 2048-character `http` URL with a 250-character authority is a valid `url_key` that `common url` refuses. At exactly 2048 characters an `https` URL satisfies `common url` and an `http` URL does not. | contract-version question; contained per page by `measurements_withheld_reason` |

**One inherited claim did not survive re-measurement.** The plan listed an `H4`, "an http canonical
of exactly 2048 characters fails the common URL pattern". The pattern fact is real and is part of
`C-PXAPI-020`, but that input never reaches the pattern through `AnalyzeHomepage`: the
500-character `single_line_text` bound records it `UNKNOWN` first. `C-PXAPI-018` says so rather
than repeating the claim.

**One of this candidate's own first measurements was also wrong, and is recorded.** A first `H7`
probe appended `</body></html>` after the unresolved tag run; the trailing `>` resolves the run, so
it measured 0.0006 s and proved nothing. The figures above are from the corrected shapes.

## 11. RED evidence

Every new behavioural obligation was red before the code that answers it existed.

| RED | Exact output |
| --- | --- |
| the domain module | `ModuleNotFoundError: No module named 'pxapi.domain.page_acquisition'` on collection |
| the behaviour scope gate, before its allowlist entry | `test_only_authorised_modules_declare_behavior` → `['domain/page_acquisition.py']` |
| the contract, before registration | `test_every_schema_file_on_disk_is_registered` and `test_every_example_file_on_disk_is_registered` named all four new files |
| the closed-vocabulary gate, after registration and before the pins | `test_every_closed_vocabulary_in_the_registry_is_pinned_or_delegated` named **exactly** the five pointers this candidate pins |
| the observer module | `ModuleNotFoundError: No module named 'pxapi.application.observe_static_page'` on collection |
| the observation-mode vocabulary, before the `F-20A-R4M-001` repair | nine assertions red, listed in §5.1; the `STATIC_HTTP` half stayed green throughout |

Two tests were red on their **first** run against the finished code, and both were real defects in
the test rather than in the code:

- `test_no_outcome_token_describes_the_website` rejected `INVALID_REDIRECT`. The word list was too
  crude: that token is the fetcher's own inherited name for a `Location` header we would not
  follow, a fact about our handling of a transport artifact. The list now names page-quality words
  only, with a canary proving it still catches a planted `BROKEN_PAGE`.
- `test_the_status_bounds_…` asserted `begin()` accepts 100. It does not: `http.client` consumes a
  bare `100 Continue` and reads on, so the lowest status a fetcher can carry is 101. The bound
  stays `100..999` — the status line parser's own range, with `http.client.CONTINUE ==
  HTTP_STATUS_MIN` pinning the floor — as a deliberate superset, so no status line the standard
  library parses can be contract-invalid.

## 12. GREEN evidence, and the countermutation passes

A rule nobody can break proves nothing, so every rule this candidate adds was broken deliberately
and the break had to turn a **named** test red. **46 countermutations, 0 escaped.** Each pass
asserted that the mutation really reached the file, that the named test returned rc **1**, that
`git checkout --` restored the file **byte-identically**, and that the mutation's own marker was
gone afterwards; each pass ran an unmutated canary before and after and demanded rc 0 from both.

| Target | Mutations | Escaped |
| --- | --- | --- |
| `src/pxapi/domain/page_acquisition.py` | 15 | **0** |
| `contracts/v1/schemas/page-acquisition-record.v1.json` | 15 | **0** |
| `src/pxapi/application/observe_static_page.py` | 16 | **0** |

The domain and schema passes were re-run in full after the `F-20A-R4M-001` repair, with three
mutations added for the repaired rule: narrowing the observation mode back to a static-only const,
dropping the rendered token, and adding a third token the architecture does not define. The
observer's sixteen were not re-run and did not need to be: `observe_static_page.py` is
byte-identical to the head they were measured on, which `git diff --quiet` confirms.

Two driver defects were found by the drivers themselves and are recorded because either would have
produced a false "all caught":

- **Stale bytecode hid a same-size mutation.** `999 → 599` and `2048 → 4096` keep the file's byte
  length, and CPython's pyc validity check is `(mtime-seconds, size)`: when the write lands in the
  same second as the previous compile, the interpreter imports the **unmutated** bytecode. Two
  mutations read as escaped on the first pass. The driver now sets `PYTHONDONTWRITEBYTECODE=1` and
  removes every `__pycache__` under `src/` and `tests/` before starting.
- **Mutating an untracked file destroys it and reports nonsense.** `git diff --quiet` ignores an
  untracked path, so `applied` read `False`; `git checkout --` could not restore it, and every
  mutation stacked into the next. Measured on the new schema before it was committed: 13 of 13
  reported `ESCAPED` with `applied=False`, and the file ended carrying all 13 mutations at once.
  The schema was rewritten, all 13 markers verified absent, the whole contract suite re-run green,
  and the file committed before the pass was repeated. The driver now refuses to start unless
  `git ls-files --error-unmatch` succeeds on the target.

One genuinely tautological test was found by the first pass and replaced. The status-maximum pin
read `_status_read(HTTP_STATUS_MAX) == HTTP_STATUS_MAX`, which holds for whatever value the
constant carries, so narrowing the maximum to 599 left it green; its two companions (`600` and
`HTTP_STATUS_MIN + 1`) are independent of the constant and also could not fail. The pin is now
`_largest_status_returned() == HTTP_STATUS_MAX`, where the search knows nothing about the constant,
plus a canary proving the search can answer something other than 999.

## 13. Failure and neutrality evidence

| Property | How it is proved |
| --- | --- |
| every fetch failure kind is neutral | parametrised over **every** `FetchFailureKind`: the mapped `not_assessed_reason`, no `result`, no polarity, source URL at the selected identity, and every document valid through the merged registry |
| the failure mapping is total | `set(NOT_ASSESSED_FOR) == set(FetchFailureKind)`, with a canary that the port vocabulary is not empty |
| no emitted document carries a verdict | every document of a 503 page, a normal page and a timeout scanned for eleven verdict keys, with a canary proving the scan sees a planted `polarity` |
| no findings member exists at all | the observation's dataclass fields are asserted to be exactly `{measurements, evidence, document_status, withheld_reason}` |
| a non-document is `NOT_APPLICABLE`, not a defect | `application/pdf` → the six document metrics `NOT_APPLICABLE`, `HTTP_STATUS` still `KNOWN` |
| our own runtime never becomes absence | an undecodable body and a raising parser both → `RUNTIME_ERROR` for the document metrics, with the transport facts surviving; a spy proves an undecodable body is **never** handed to the parser (0 calls) |
| a truncated read is never a false absence | `PAGE_TITLE_PRESENT` `UNKNOWN` with no result, while a title the read *did* see is still reported, and a seen `noindex` directive still stands |
| a value beyond the text bound establishes nothing | a 501-character title → presence `KNOWN true`, value `UNKNOWN`, never a shortened value |
| site input never yields an invalid document | six canonical classes, each asserted through the real registry, with a canary that the table exercises both answers |
| our own defects stay visible | the eleven producer invariants fail **closed**: `require_emittable_acquisition` raises `ProducerInvariantViolated` and withholds the documents |

## 14. Determinism evidence

- One frozen input produces byte-identical measurements and evidence on two runs.
- Two runs with different identity factories produce an identical identity-free projection, and a
  canary proves that projection still carries the facts.
- The identity order — all thirteen measurements, then all thirteen evidence documents — is pinned,
  because it is part of what a frozen input reproduces.
- `body_digest` is asserted against `hashlib.sha256` vectors recomputed in the test, including the
  empty body, and is asserted to change on one differing byte and to differ from a digest over a
  JSON rendering or over the URL.
- The record order is the manifest's selection-rank order, not merely the same set: a swapped pair
  fires `one_record_per_selection`.

## 15. Full regression

| Gate | CPython 3.13.3 | CPython 3.14.6 |
| --- | --- | --- |
| `uv lock --check` | clean | clean |
| `uv run ruff check .` | **All checks passed** | **All checks passed** |
| `uv run ruff format --check .` | 107 files already formatted | 107 files already formatted |
| `uv run pytest` | **3122 passed, 1 skipped, 2 warnings** | **3122 passed, 1 skipped, 2 warnings** |

The base measured 2876 passed, so this candidate adds **246** tests. The one skip is the opt-in
PXAPI-19 real-boundary smoke (`PXAPI_REAL_BOUNDARY_SMOKE_URL` unset); it is unchanged by this
candidate and no multi-page smoke exists yet — that is `20.B`. The two warnings are the pre-existing
`anyio`/`starlette` typing warnings emitted on the base as well.

The 3.14 run used a separate project environment so the 3.13 environment was not re-synced
underneath it (`uv run` re-resolves the default interpreter otherwise); `sys.version` was printed
from inside each run and is recorded above.

## 16. Diff and reviewability — and where this candidate does **not** meet its own gate

Measured at `a822b01b7010e4ff0397bbcd373bb21f99543be4`, the `F-20A-R4M-001` repair commit. The
correction that wrote these figures into this document touches `docs/evidence` alone, so the
counted measure — which excludes that directory by the convention's own definition — is unchanged
by it; the full-diff figure rises by the size of the correction itself.

| Measure | Value |
| --- | --- |
| changed files | **33** |
| `git diff --shortstat` | 33 files changed, **3845** insertions, **30** deletions |
| counted diff (`--unified=0`, excluding `docs/evidence`) | **223,711 bytes** |
| full diff, as Sourcery counts it | **283,362 bytes** |
| `docs/evidence` alone (counted separately, not included above) | 33,184 bytes |

Per area (counted): `docs/context` 53,358 · `tests` 95,414 · `src` 44,029 · `contracts` 30,037 ·
`README.md` 873.

Per commit (counted):

| Commit | Bytes | Subject |
| --- | --- | --- |
| `3ae2316` | 51,112 | governance reconcile |
| `bc68464` | 42,978 | domain vocabulary and producer invariants |
| `5c5f1d6` | 1,864 | the status-maximum pin, de-tautologised |
| `b90aab7` | 65,330 | contract registration |
| `2e80e50` | 48,730 | the static-page observer |
| `f1ec015` | 36,170 | this evidence document and the two READMEs |
| `d6b167f` | 1,916 | the measured-diff correction |
| `a822b01` | 24,126 | the `F-20A-R4M-001` contract-authority repair |

**This is a finding, stated plainly: 20.A did not come in materially smaller than the monolithic
plan it replaced.** The single-PR option was projected at ≈190–250 kB counted, and this candidate
lands at 224 kB — inside that band rather than below it. It is the smallest slice since PXK-20.B1
against the same calibration (PXAPI-19.B 340,448 · PXAPI-19.A 274,275 · PXK-67 225,587 ·
PXK-20.B1 77,520), and it is above the repository's 140,000-byte reviewability convention and above
Sourcery's 150,000-character limit, so no bot review will run (`C-PXAPI-001` neighbourhood; `main`
carries no branch protection). `D-20-M` names the Product Owner / Orchestrator as the independent
`R4M` authority, which is the compensating control — and that review happened: Jira comment
`16325` records it, together with a Product Owner **one-time size exception for 20.A**. No resplit
is required, because the independently inspected production blast radius is two new source modules
plus one additive contract entry; the exception does not carry over to 20.B.

Nothing was hidden to reach the number: every fixture and every example is committed and listed,
and `docs/evidence` is excluded only by the convention's own definition, with its full-diff cost
stated above.

If the Product Owner prefers smaller candidates, the commits are already split along reviewable
seams and a resplit needs no rework:

- **A** governance reconcile — `3ae2316`, 51,112 B, documentation only, no production file;
- **B** domain + contract — `3ae2316..b90aab7`, 109,409 B, no runtime, nothing calls it;
- **C** the observer — `b90aab7..2e80e50`, 48,730 B, nothing calls it either;
- the evidence document and the READMEs — `f1ec015` + `d6b167f`, 38,086 B — travel with whichever
  candidate carries the code they describe, or split along the same seams;
- the `F-20A-R4M-001` repair — `a822b01`, 24,126 B — belongs with **B**.

The Product Owner has since waived the resplit for this candidate (comment `16325`); the seams stay
recorded because a later candidate may want them.

No further abstraction was added after this measurement.

## 17. Architecture scope reconciliation

| Dimension | EXPECTED (brief) | DECLARED (this candidate) | OBSERVED (measured) |
| --- | --- | --- | --- |
| new source modules | `domain/page_acquisition.py` + one isolated observer module | those two | exactly those two; `git diff --name-only … -- src` lists 2 paths |
| protected source | byte-identical | byte-identical | 13 protected paths, each `git diff --quiet` rc 0 |
| contracts | 1 new; no version of an existing one | 1 new, additive registry entry | +14 registry lines, 0 deletions; the twelve existing schema files rc 0 |
| dependencies | none | none | `pyproject.toml` and `uv.lock` rc 0; `uv lock --check` clean |
| runtime interfaces | none | none | no CLI, no endpoint, no composition change; `adapters/**` rc 0 |
| security boundary | unchanged | unchanged | `adapters/web/**`, `ports/**`, `config/**` rc 0; the application layer imports no `socket`/`ipaddress` (existing gate green); `is_public_address` still declared in exactly one module |
| homepage behaviour | unchanged | unchanged | `analyze_homepage.py` rc 0; its existing tests green; the 600-character canonical divergence is page-only and declared in section 9 |
| behaviour allowlist | only as required | +2 `PXAPI-20.A` entries | 2 entries, both earning their exemption and inside a declared layer |
| closed vocabularies | pinned | +5 pins | the gate named exactly those 5 pointers before they existed |

No protected-scope change, no undeclared source module, no new dependency, no new runtime
interface and no silent scope expansion. The one behavioural divergence is declared rather than
silent.

## 18. Evidence ceiling

This candidate proves a **contract and a reusable foundation**, offline. It does not prove that any
page was acquired, that a manifest was iterated, that a real site responds, that multi-page
evidence improves a diagnosis, or that a customer values the result. No real-boundary evidence is
claimed and none was produced: the AC8-class proof for PXAPI-20 is a `20.B` obligation. Every
number above was measured on one workstation on CPython 3.13.3 and 3.14.6; CI on the exact
candidate head is recorded on the pull request, not here.

Schema validity proves no gate. `IC`, `R2G` and `R4M` are declared by the Product Owner /
Orchestrator on the exact candidate head (`D-20-M`), and **merging this candidate does not make
`PXAPI-20` Done** (`D-20-K`).

## 19. Anti-drift

- WIP stayed `PXAPI-20` only; no other theme was touched.
- The base was re-read live before the first mutation and matched `19a9a855…` exactly.
- Three findings were ledgered rather than repaired, each barred by a named Product Owner decision.
- One inherited claim (`H4`) and one of this candidate's own measurements (the first `H7` probe)
  were corrected in writing rather than quietly dropped.
- Two countermutation-driver defects that would have produced a false "all caught" are recorded.
- The candidate's own oversize against the reviewability convention is reported, with a split point,
  rather than argued away.
- Nothing here upgrades any PXAPI-19 gate, and the historical PR #16 `R4M` stays `UNKNOWN`.
