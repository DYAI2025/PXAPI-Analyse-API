# PXAPI-25 — Operator Workbench & Multi-Page Run Validation v1

**Slice:** Jira `PXAPI-25`, one bounded PR candidate. **This document does not declare `IC`,
`R2G`, `R4M`, a merge or `PXAPI-25` Done** — those are Orchestrator / Product Owner authority.

**Exact base:** `ce4de1820d2516f9b3bf73b11ad9441dbad941ba` (`main`, PXAPI-20.B merged; exact-SHA
`python-compat` run `36405179068` `success`), re-verified with `git ls-remote` before the branch
was created. **Branch:** `agent/pxapi25-operator-workbench`.

**Code head:** `53c98bfbaeaabdc928821a4f7a4d32bb87d0680c` — the target-binding repair (§11,
`F-25-R4M-003`) on top of `e0b0f3a57cb3c27f1d23e48c82919a1b56c599e6`, the final validation repair
(§10), on top of the earlier proven head `32703a67b5af03f5b297e6ad18d996e9ab349d74`. Exact-head CI,
the real-boundary proof and review of `53c98bf` are still to be run; the real-boundary proof in
§10 is of `f524a8c` and does not cover §11. Sections 1–9
record the state at `32703a6` and say so where a figure was measured there. Every executed figure
below names the SHA it was measured on. The commit that carries this document changes documentation
only; a commit cannot contain its own SHA, so that head is re-verified at its own exact SHA (CI
and the real-boundary proof) and those results are recorded on the PR and in Jira, not here.

**Authority:** Jira `PXAPI-25` (description, comments `16735`, `16747`; for §10–§11 also
`16813`, `16817`, `16819`) and the Product Owner's
acceptance of the PRE_IMPLEMENTATION plan with amendments (2026-09-28); Confluence `71991298` v3,
`54362115` v1, `55181314` v1.

## 1. What this candidate builds

`Operator (browser) → Workbench adapter → build_request → request contract → SelectionBudgets →
build_site_acquisition → AcquireSelectedPages (unchanged) → canonical documents → artifact bundle →
read-back → ValidateAnalysisRun → analysis-validation-receipt.v1 → result page + downloads`.

| Module / file | Layer | Change |
| --- | --- | --- |
| `contracts/v1/schemas/analysis-validation-receipt.v1.json` + 4 examples | contract | new, registered (owner slice `PXAPI-25`) |
| `src/pxapi/domain/run_validation.py` | domain | new: gate families, states, closed reason vocabulary with one effect each, derived gate state, precedence, receipt rules |
| `src/pxapi/ports/contract_validation.py` | ports | new: narrow validation port; `ContractRegistry` satisfies it structurally (no wrapper) |
| `src/pxapi/application/validate_analysis_run.py` | application | new: the seven gates over produced documents and the published bundle |
| `src/pxapi/application/run_lifecycle.py` | application | new in the repair (§10): the stage history and members the multi-page orchestration emits per outcome |
| `src/pxapi/adapters/inbound/workbench.py` | adapter | new: FastAPI routes, one-run guard, execution, bundle, downloads |
| `src/pxapi/adapters/inbound/workbench_views.py` + `workbench.css` | adapter | new: server-side HTML, escaping by construction, one local stylesheet, no script |
| `pyproject.toml`, `uv.lock` | build | additive `browser` dependency group (Playwright); no runtime dependency added |
| `.github/workflows/workbench-browser.yml` | CI | new, separate from `python-compat` |
| `tools/pxapi25_workbench_real_boundary_proof.py` | proof | new, not product code |
| tests | tests | new domain, application, contract, adapter, view, browser and tool tests; additive pins in `tests/test_closed_vocabularies.py` and allowlist entries in `tests/test_package_scaffold.py` |

## 2. Architecture scope — expected, declared, observed

**Expected / declared** (accepted plan): new contract + application validator + optional narrow
port + FastAPI Workbench adapter + minimal presentation + tests + allowlist changes + bounded
CI/proof + docs. Protected modules behaviourally unchanged.

**Observed** (`git diff ce4de18 32703a6`, measured 2026-09-29): 50 files, **8184 insertions, 0
deletions**.

- `git diff --name-status --diff-filter=MDR ce4de18 32703a6` lists only `contracts/README.md`
  (+58), `contracts/v1/manifest.json` (+15, one new entry), `pyproject.toml` (+8, the group),
  `tests/test_closed_vocabularies.py` (+75, pins), `tests/test_package_scaffold.py` (+5,
  allowlist) and `uv.lock` (+72, only the three browser-group packages). **No existing `src/`
  file, schema or example is modified.**
- `git diff --stat ce4de18 32703a6 -- <protected paths>` over `analyze_homepage.py`,
  `acquire_selected_pages.py`, `discover_site.py`, `observe_static_page.py`, `adapters/web/**`,
  `http_api.py`, `cli.py`, `acquire_cli.py`, `discover_cli.py`, `composition.py`,
  `adapters/contracts/**`, `config/**`, the three existing ports, `.agent-proofs.json` and
  `python-compat.yml` is **empty**.

**Core reuse.** The Workbench obtains the analysis only through `build_site_acquisition`
(production passes it itself; a test asserts `workbench.acquisition is build_site_acquisition`)
and imports no discovery, fetcher, observer or acquisition module and no `subprocess` (an AST test
enforces both). It reuses `build_request` and `REQUEST_CONTRACT` (`cli.py`), `page_budget` and
`invalid_documents` (`acquire_cli.py`) and the Domain's `site_identity.refuse`. The validator
reuses `admission_violations`, `acquisition_violations`, `inventory_producer_violations`, the
contract-semantic `violations_of` and `digest_of` rather than restating any rule; its member
table and serialisation are pinned byte for byte against `acquire_cli`.

## 3. Run validation — the gates as implemented

| Gate | FAIL (defect of this service) | BLOCKED (evidence missing / incomplete / unavailable) | NOT_APPLICABLE |
| --- | --- | --- | --- |
| `INPUT_CONTRACT` | request missing / contract-invalid / not the submitted request (another run, another target, or any other member differing — since §10); manifest budget ≠ declared budget | — | request withheld by policy (credential target refused; the producer persists no request on purpose) — since §10 only when the *submitted* target carried credentials |
| `ACQUISITION_COMPLETENESS` | run state unreadable; not terminal; failed by a producer defect (`*_NOT_EMITTABLE`, `SAMPLING_MANIFEST_NOT_ADMISSIBLE`); unclassified failure code; succeeded without manifest or records | run failed technically (target refused, unreachable, discovery provider/timeout/runtime); cancelled; `selection_complete` not `true`; a page with no response; a truncated or undecodable body | — |
| `CANONICAL_VALIDITY` | member missing / unexpected / wrong container; document contract violation (pointer + keyword); contract-semantic rule broken; inventory producer invariant broken; since §10 the run's stage history or member set contradicts how it ended (`PRODUCER_INVARIANT_BROKEN`, rules `stage_history_follows_run_outcome` / `member_follows_run_outcome`) | — | — |
| `PROVENANCE_LINKAGE` | document bound to another run; linked document missing; manifest–inventory binding, manifest producer rule or digest reproduction broken; acquisition linkage rule broken; duplicated measurement or evidence id | — | — |
| `EVIDENCE_COVERAGE` | only if the documents cannot be evaluated | measurements withheld; a page with NOT_ASSESSED or UNKNOWN assessments; a measurement no evidence names | the run did not succeed, so it emitted no page documents |
| `UNRESOLVED_CONFLICTS_LIMITATIONS` | only if the documents cannot be evaluated | a CONFLICT assessment; a discovery source `BUDGET_EXHAUSTED`, `TARGET_POLICY_REFUSED`, `PROVIDER_FAILURE`, `RUNTIME_ERROR`, `TIMEOUT` or `MALFORMED` | as above |
| `ARTIFACT_BUNDLE_VALIDITY` | file missing / unexpected (a receipt included) / not JSON / not byte-identical to the canonical serialisation | — | — |

Any gate whose evaluation raises reports `VALIDATION_NOT_EVALUABLE` (FAIL) instead of a partial
result. A scenario catalog in `tests/application/test_validate_analysis_run.py` makes the
validator actually produce each of the 39 reason codes, and every produced receipt is checked
against its contract and the receipt rules.

Implementation decisions taken inside the accepted plan, for review:

1. `selection_complete = false` blocks — it is a declared bound, not a site fact, but a site
   release over an incomplete selection cannot be established. A run whose budget covers the site
   can PASS.
2. The two page-evidence gates are `NOT_APPLICABLE` when the run did not succeed: there is no page
   evidence to evaluate, and `ACQUISITION_COMPLETENESS` already states why the run is not
   releasable. No failed run can PASS (tested for every bootstrap failure and every
   non-SUCCEEDED state, and stated in the schema as a conditional).
3. A non-2xx page is a received response (acquisition complete) whose document facts are
   NOT_ASSESSED (`UNSUPPORTED`) — missing evidence, `BLOCKED`.
4. The submitted request and the declared budget are inputs from the caller, not read from the
   documents under validation, so documents cannot vouch for their own binding. (Until §10 only
   the submitted `run_id` was handed in; the target was not bound — see §10, Finding A.)
5. The bundle is validated as published: written as a deterministic zip, read back, validated;
   **that same archive, byte for byte, is what `artifacts.zip` serves**, holding the canonical
   documents only. The receipt is built afterwards, pins the bundle by `artifact_bundle_digest`,
   and is its own download — no receipt ever sits inside the bundle it validates.

## 4. Workbench adapter decisions

- A separate ASGI app (`pxapi.adapters.inbound.workbench:app`), so `http_api.py` is untouched; no
  OpenAPI, docs or `/v1` route.
- Form parsing with the standard library (`parse_qs`) — no `python-multipart` dependency. The body
  is bounded before it is buffered: a declared `Content-Length` over 16 KiB is refused unread, an
  undeclared body is read chunk by chunk and abandoned at the bound.
- The run executes in the threadpool (`run_in_threadpool`), so the event loop keeps serving the
  `409` guard and other pages while a run is in progress.
- `Content-Security-Policy: default-src 'none'; style-src 'self'; img-src 'self'; form-action
  'self'; frame-ancestors 'none'; base-uri 'none'`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store` on every
  response.
- Host allowlist `127.0.0.1`, `localhost` (Starlette `TrustedHostMiddleware`): a DNS-rebinding
  page is same-origin with the attacker's name, so only the Host tells it apart. Serving the
  Workbench under another name needs a code change — it is an internal loopback tool in V1.
- Cross-site form posts are refused by the browser's `Sec-Fetch-Site`, with `Origin` as fallback.
  **Found by the real-browser journey, not by the HTTP tests:** under `Referrer-Policy:
  no-referrer`, Chrome 154 sends `Origin: null` on the page's own form post, so the first origin
  check refused every browser run (403). Root cause measured with Playwright; RED test added; fixed
  in `7e5572d`.
- Credential targets: any `@` in the authority is refused as userinfo, independent of which
  identity rule `site_identity.refuse` reports first, and a refused URL containing `@` is never
  echoed back into the form.
- A run whose own canonical documents fail their contracts is withheld: the result page answers
  `500`, explains the defect, offers the receipt (with `CANONICAL_VALIDITY` FAIL) and no bundle.

## 5. Independent adversarial review (read-only, 2026-09-29)

Five review lenses (security, validation semantics, architecture, test integrity, runtime/UI) over
`ce4de18..7e5572d`, each finding checked by a separate refuting verifier: 20 findings, 13
confirmed — 10 distinct after merging the ones two or three lenses found independently. All were
fixed in `32703a6`, each with a RED test first:

| Finding (confirmed) | Severity | Disposition |
| --- | --- | --- |
| Credential URL with a second defect (backslash, NBSP, bracket, space, ftp, over-length) admitted — secret on the result page and in `analysis-run-request.json` — or echoed into the form | medium | fixed (authority `@` check; no echo); 9 URL shapes tested |
| Inventory producer invariants never re-checked: an inventory hiding a cut-short source validated PASS | medium | fixed: new FAIL reason `PRODUCER_INVARIANT_BROKEN` |
| State assertions satisfied by static help text (a colour-only or wrong badge could not fail a test) | medium | fixed: gate rows, overall badge and run-state badge asserted on their elements, in HTTP and browser tests |
| Served zip carried the receipt, contradicting "no receipt inside the bundle it validates" | low | fixed: served archive = validated archive |
| Credential refusal by policy validated FAIL (request withheld on purpose) | low | fixed: `INPUT_CONTRACT` NOT_APPLICABLE (`REQUEST_WITHHELD_BY_POLICY`), overall BLOCKED |
| No Host allowlist (DNS rebinding) | low | fixed: loopback allowlist |
| Body buffered before the size check | low | fixed: bounded read |
| Withheld page navigation linked to sections it does not render | low | fixed: navigation names rendered sections; every `#anchor` resolves (tested) |
| "Every reason code exercised" meta-test satisfied by mentions and an exclusion list | low | replaced by the producing scenario catalog |
| A "concurrency harness canary" tested only `threading.Event` | low | removed |

Unconfirmed findings (verifier `real=false`) were not treated as defects; one of them — only
`TIMEOUT` was tested among the limiting discovery outcomes — was cheap to close and now has a
test per outcome. A pre-existing defect of the same
credential class on `main` — the multi-page command line persists a credential when the URL also
breaks an earlier identity rule — is outside PXAPI-25's protected scope and recorded as
`C-PXAPI-026`.

**Mutation evidence at the fixed tree:** eleven deliberate mutants — badge without its word,
credential check back to `refuse()` only, inventory producer rules skipped, precedence
BLOCKED-over-FAIL, incomplete selection escalated to FAIL, receipt back inside the served zip, no
Host allowlist, body buffered whole, views not escaping, policy-withheld request counted as
missing, full navigation on the withheld page — were each **killed** by the targeted tests, and
the sources were restored and re-checked afterwards.

## 6. Tests

Commands (worktree venv, Python 3.13.3, `uv sync --locked --group browser`):

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && uv lock --check
PXAPI_BROWSER_TESTS=required PXAPI_BROWSER_CHANNEL=chrome .venv/bin/python -m pytest -q -p no:cacheprovider
```

| Measured on | Result |
| --- | --- |
| base `ce4de18`, local | `3399 passed, 2 skipped` (rc 0), Ruff clean |
| checkpoint `7b2e14f` (contract + validation), local | `3658 passed, 2 skipped` (rc 0) |
| checkpoint `5bef309` (Workbench), local | `3737 passed, 2 skipped` (rc 0) |
| `7e5572d` (browser journey), local, browser tests on Chrome 154 | `3755 passed, 2 skipped` (rc 0) |
| `32703a6` (review fixes), local, browser tests on Chrome 154 | `3823 passed, 2 skipped` (rc 0), Ruff and lock check clean |

Browser-gate mechanics, measured with Playwright made unimportable: without the variable the
module is skipped (`1 skipped`); with `PXAPI_BROWSER_TESTS=required` collection fails (rc 2), so
the browser job cannot pass by skipping.

**Negative and XSS evidence.** Over HTTP: missing URL, missing budget, missing budget field,
budgets `0 -1 abc 1.5 " 3" ٣ +3` and 5000 digits, five invalid URLs, a credential URL plus nine
credential URLs with a second defect (never echoed, nothing run), duplicated fields, a private
target through the shipped policy (loopback refused before any connection, run FAILED,
validation BLOCKED), cross-site posts (six header combinations), foreign Host names (three),
wrong media type (415), oversized bodies (413, declared and streamed), unknown and
traversal-shaped run ids (404), a run with contract-invalid documents (withheld, 500), an
internal exception (500, message not leaked, slot released). XSS: a page title written as
`&lt;script&gt;alert(1)&lt;/script&gt; Kanzlei` and a meta description decoding to
`<img src=x onerror=alert(2)> "quoted"` render as text only — no `script` or `img` element, no
`on*` attribute, no URL attribute outside `#…` and `/operator…`; a hostile target URL is escaped
on the result page and the refused form. The view sweep replaces **every** string of a real run's
envelope (more than 200 paths) and receipt, one at a time, with
`"><script>alert(9)</script><img src=x onerror=alert(8)>` and asserts the page stays inert. In the
browser: `page.locator("script").count() == 0` and no dialog opened.

**Browser journey** (`tests/browser`, deterministic fake ports, real uvicorn, real browser):
URL + budget → result → gate states read from the gate table → Evidence Inspector opened →
bundle and receipt downloaded through the browser and read back; keyboard-only path with a
visible focus ring on every step; reload, back and forward never resubmit (one run started); a
second tab gets `409` while the first run is held; the *document* does not scroll sideways at
1280×900 and 375×812 (`scrollWidth <= clientWidth` of the root element). At 375 px the wide
technical tables do scroll sideways inside their own `.table-wrap` region — that is the design,
and §10 adds the test that every cell there stays reachable.

## 7. Real-boundary browser proof

`tools/pxapi25_workbench_real_boundary_proof.py --channel chrome`, clean tracked tree, `pxapi`
imported from this checkout's `src/pxapi`, served acquisition `build_site_acquisition`
(production wiring), Python 3.13.3, Chrome 154.0.8037.58 headless, target
`https://www.rfc-editor.org/`, budget 3.

**At `32703a67b5af03f5b297e6ad18d996e9ab349d74`** (2026-09-28T22:51:33Z):

- run `px-d9866b9c1a664be8894741ed6dd1ad3f` `SUCCEEDED` in 2.8 s;
- inventory: 506 candidates; sources `CANONICAL_SEED` USED 1, `ROBOTS_DECLARATION` USED 0,
  `SAME_ORIGIN_PAGE_LINKS` USED 19, `SITEMAP` `BUDGET_EXHAUSTED` 500;
- manifest: `selection_complete = false`, `SELECTION_BUDGET_EXHAUSTED`, budget
  `max_selected_pages = 3`, 503 candidates excluded by budget;
- pages: `/`, `/about/contact/`, `/about/rfc-editor/` — all `RESPONSE_RECEIVED` HTTP 200, 13
  measurements each; 39 measurements, 39 evidence records; all three opened in the Evidence
  Inspector;
- validation `BLOCKED`: `ACQUISITION_COMPLETENESS` (`SELECTION_INCOMPLETE`),
  `UNRESOLVED_CONFLICTS_LIMITATIONS` (`DISCOVERY_SOURCE_LIMITED` — the sitemap source hit this
  service's own 500-entry bound); the other five gates `PASS`; `artifact_bundle_digest`
  `sha256:c057dfd44e7bed6bb569c5d95aa181a95bcf994338604fb59b96248bafe84c5d`;
- the bundle (12015 bytes, exactly the eight canonical files) and the receipt downloaded through
  the browser; independent read-back: every canonical document contract-valid, producer
  invariants hold, the bundle digest recomputed over the downloaded files equals the receipt's,
  receipt contract-valid and rule-clean; no script element, no handler attribute, no dialog;
  reload keeps the result; no horizontal scroll *of the page* at 375 px (the tool measured the
  root element only; tables scrolled inside their own region, unmeasured then — see §10).
  Verdict `PASS`, no problems.

**Earlier, at `7e5572d`** (before the review fixes; the bundle then still carried the receipt):
run `px-d6dd4079f5444116b89b52e695356792` `SUCCEEDED` in 3.8 s, the same three pages and counts,
the same gate states, `artifact_bundle_digest`
`sha256:f4bb71af6697e8d3473960b5372f9e1cd32d358ffd452b23014611602b0d4c2d`, bundle 12796 bytes,
verdict `PASS`. Kept as history.

## 8. CI

| Head | Workflow | Run / job | Result |
| --- | --- | --- | --- |
| `7e5572d` | `python-compat` py3.13 (CPython 3.13.15) | `36491581508` / `109161199800` | success, `3748 passed, 3 skipped` |
| `7e5572d` | `python-compat` py3.14 (CPython 3.14.7) | `36491581508` / `109161199999` | success, `3748 passed, 3 skipped` |
| `7e5572d` | `workbench-browser` | `36491581520` | success, `7 passed`; screenshots artifact `11001404440` |
| `32703a6` | `python-compat` py3.13 (CPython 3.13.15) | `36494804515` / `109171757273` | success, `3816 passed, 3 skipped` |
| `32703a6` | `python-compat` py3.14 (CPython 3.14.7) | `36494804515` / `109171756932` | success, `3816 passed, 3 skipped` |
| `32703a6` | `workbench-browser` (Playwright Chromium) | `36494804385` / `109171756313` | success, `7 passed` |

The one extra skip in each compatibility job is the browser module, skipped by design there;
`3816 + 7 = 3823`, the local count.

## 9. What this does not prove

- No durability: a restart loses the latest run; there is no run history, no queue, no
  idempotency or async run identity (PXAPI-15..18 own those).
- No authentication, rate limiting or deployment: the Workbench is an internal tool that answers
  only to loopback host names. Nothing here is a public or partner claim.
- No business diagnosis, strategic lever, score, customer report or PDF; the receipt is not a
  customer-release decision and says nothing about website quality.
- No browser/rendered acquisition: the browser in this slice operates the GUI; acquisition stays
  `STATIC_HTTP`.
- One real-boundary run of one public origin at one point in time; no claim about other sites,
  larger budgets (a large budget runs synchronously and can take minutes), or future refetch
  determinism.
- Accessibility is checked for labels, landmarks, heading order, resolving in-page links,
  keyboard operation, visible focus and not-colour-only states; no full WCAG audit or
  screen-reader test was run.
- The validator validates every document against its contract a second time after the command
  line's own check; its cost on very large runs was not measured.
- The pre-existing command-line credential defect (`C-PXAPI-026`) is recorded, not repaired.

## 10. Final validation repair (2026-09-29)

**Old head:** `73d1d7b3ff6ffcbec5c62a0d4ee9b6cddd7a7901` (PR #22 head at handoff, base
`ce4de18`, re-verified open and unchanged with `gh pr view 22` and `git ls-remote` before any
edit). **Repaired code head:** `e0b0f3a57cb3c27f1d23e48c82919a1b56c599e6` — `4ac9d5c` (fix),
`f524a8c` (tests) and `e0b0f3a` (a timing fix in one browser test, below). `git diff f524a8c
e0b0f3a` outside this document touches only `tests/browser/test_workbench_journey.py`. The
commit that carries this section changes documentation only.

`git diff --stat 73d1d7b f524a8c`: 10 files, 741 insertions, 30 deletions. The same diff over
every protected path of §2 plus `contracts/`, `src/pxapi/ports/` and `.github/` is **empty**. No
reason code, schema, example or manifest entry is added or changed.

### Finding A — the receipt was not bound to the submitted target

`ValidateAnalysisRun.run` received `run_id` and the declared budget, not the submitted target.
Pre-fix, measured at `73d1d7b` over a genuine run whose canonical request was changed to
`target_url = https://b.example/` (submitted `https://example.com/`, same run id, same budget):
**overall `PASS`, `INPUT_CONTRACT` `PASS`.**

*Oracle.* The multi-page producer copies the submitted request into the envelope unchanged
(`DiscoverSite.run` emits `"analysis_run_request": request`; `AcquireSelectedPages` passes it
on). The only request it can emit is therefore the submitted document itself. The binding is
that identity, member for member — no URL normalisation is invented, so a spelling nobody
submitted (upper-case host, missing slash, explicit default port) is not the submitted request
either.

*Repair.* `run(envelope, bundle, *, submitted_request, declared_budget)`; the run id is taken from
the submitted request. `INPUT_CONTRACT` compares every member of the canonical request with the
submission (values compared in the canonical serialisation) and reports each differing member as
`REQUEST_NOT_BOUND_TO_RUN` at `/analysis_run_request/<member>`; the reason's fixed meaning now
reads "not the request submitted for the run validated". The receipt never carries the submitted
value. The credential exemption `REQUEST_WITHHELD_BY_POLICY` now also requires that the
*submitted* target carried credentials (same `site_identity.refuse` rule the producer uses): pre-
fix, a clean submission whose documents claimed the refusal and withheld the request validated
`INPUT_CONTRACT` `NOT_APPLICABLE`. The Workbench passes the request it admitted.

### Finding B — lifecycle and artifact coherence were not validated

*Oracle.* `contracts/README.md` makes a `FAILED` stage beside a `SUCCEEDED` run contract-valid
and leaves stage fatality to "orchestration policy, which no contract here decides". The
multi-page orchestration has decided it in code, and that code is the authority used:
`DiscoverSite._failed` / `AcquireSelectedPages._failed` / the success return. Per outcome:

| Run outcome | Stage history (`stage_id`, `status`) | Members beyond request, state, stages |
| --- | --- | --- |
| `SUCCEEDED` | SITE_DISCOVERY ✓, SAMPLING_PLAN ✓, PAGE_ACQUISITION ✓ | inventory, manifest, the three page members |
| `FAILED` bootstrap codes, `SITE_DISCOVERY_BOOTSTRAP_FAILED`, `SITE_INVENTORY_NOT_EMITTABLE` | SITE_DISCOVERY ✗ | none |
| `FAILED` `TARGET_NOT_PERMITTED` | SITE_DISCOVERY ✗ | none; the request is optional (withheld for a credential target only) |
| `FAILED` `SAMPLING_MANIFEST_NOT_EMITTABLE` | SITE_DISCOVERY ✓, SAMPLING_PLAN ✗ | inventory |
| `FAILED` `SAMPLING_MANIFEST_NOT_ADMISSIBLE` | SITE_DISCOVERY ✓, SAMPLING_PLAN ✓, PAGE_ACQUISITION ✗ | inventory |
| `FAILED` `PAGE_ACQUISITION_NOT_EMITTABLE` | as above | inventory, manifest |
| `CANCELLED` | not stated — no producer of this slice emits it | no page members (the one fact every non-succeeded outcome shares) |

No reusable invariant existed, so the table is new: `src/pxapi/application/run_lifecycle.py`,
importing every stage token and failure code from the module that emits it; the run-state edges
stay in `domain/run_state.py`. It is pinned against the producer, not asserted: a test runs every
genuine producer path (success, budget-limited success, success with a page timeout, each of the
five bootstrap failures, credential refusal, inventory withheld, manifest withheld, selection not
admissible, acquisition withheld) and requires zero lifecycle violations, and two more pin the
table's member set to the validator's and its failure codes to exactly the producers' codes.

Pre-fix, measured at `73d1d7b` over genuine runs with one change each:

| Counterexample | Overall before | After |
| --- | --- | --- |
| `SUCCEEDED`, `stage_executions = []` | `PASS` | `FAIL` (`stage_history_follows_run_outcome`) |
| `SUCCEEDED`, PAGE_ACQUISITION stage `FAILED` | `PASS` | `FAIL` |
| `SUCCEEDED`, SAMPLING_PLAN stage `CANCELLED` | `PASS` | `FAIL` |
| `FAILED` (discovery `TIMEOUT`) + a succeeded run's inventory, manifest and page documents | `BLOCKED`, `EVIDENCE_COVERAGE` claiming `RUN_EMITTED_NO_PAGE_DOCUMENTS` | `FAIL` (`member_follows_run_outcome` at each foreign member) |
| `CANCELLED` + page documents | `BLOCKED` | `FAIL` |

Further RED cases: missing, reversed and duplicated stage entries; an acquisition failure whose
stage claims success; a plan failure still carrying a manifest. `CANONICAL_VALIDITY` reports each
contradiction as the existing `PRODUCER_INVARIANT_BROKEN` (FAIL) with its rule name; a required
member that is simply absent stays `CANONICAL_MEMBER_MISSING`, not reported twice.

**Failure neutrality.** Every genuine technical outcome still validates without a single FAIL
reason (per bootstrap failure: overall `BLOCKED`, `CANONICAL_VALIDITY` `PASS`); a page timeout or
incomplete selection stays `BLOCKED`. Only a document set this producer cannot have emitted
becomes `FAIL`.

### RED → GREEN and counter-mutation

At `73d1d7b` plus the new tests only: **18 failed, 9 passed** in
`tests/application/test_validation_binding_and_lifecycle.py` and the new Workbench test, each on
its intended assertion (e.g. `assert 'PASS' == 'FAIL'`, `assert ['REQUEST_WITHHELD_BY_POLICY'] ==
['REQUEST_MISSING']`; the table-pin test on the absent module). The nine passing were the
positive and neutrality controls. After the repair all pass.

Counter-mutation at `4ac9d5c` (driver asserts each target file is tracked, purges `__pycache__`
with `PYTHONDONTWRITEBYTECODE=1`, restores with `git checkout` and re-checks a clean diff; canary
unmutated `29 passed` before and after):

| Mutant | Result |
| --- | --- |
| request binding compares `run_id` only | killed (rc 1) |
| credential exemption ignores the submission | killed |
| validator skips the lifecycle check | killed |
| no stage-history check | killed |
| no page-member check for a run that did not succeed | killed |
| no member-set check | killed |
| Workbench validates against the request the documents carry | killed |

### Finding C — the 375 px claim

Observed (Chrome 154.0.8037.58 headless, deterministic journey, every Evidence Inspector entry
open): the root element is 375 px wide with no overflow; all eight `.table-wrap` tables are wider
than their container (content 544–802 px in 317–343 px) and scroll sideways inside it; no cell lies
outside the scrollable extent, the last column comes fully into view when scrolled to the end, and
nothing is clipped vertically. Tab reached all eight regions (probe), and the arrow keys scroll the validation table's region (tested). The
real-boundary screenshot shows the Validation *Reasons* column continuing past the right edge
inside its table region; the same BLOCKED reasons are also written out in full in the Limitations
section.

The implementation is usable as it stands, so **no CSS or view changed**. What changed is the
evidence: `test_at_375_px_wide_tables_scroll_inside_their_region_and_nothing_is_cut_off` asserts
all of the above (plus the validation, page-outcome and evidence texts), and was counter-mutated —
`.table-wrap { overflow: hidden }` and a `max-height` clip each turn it red. **The supported claim
is now:** at 375 px the page itself never scrolls sideways; wide technical tables scroll sideways
inside their own region, where every cell stays reachable by pointer and — in Chromium — by
keyboard. The earlier wording "no horizontal scroll at 375 px" meant the page only (§6, §7 are
annotated accordingly).

### Regression at `f524a8c`

| Command | Interpreter | Result |
| --- | --- | --- |
| `uv lock --check` | — | rc 0 |
| `uv run ruff check src tests tools` / `ruff format --check` | — | rc 0 / rc 0 (126 files) |
| `PXAPI_BROWSER_TESTS=required PXAPI_BROWSER_CHANNEL=chrome uv run pytest -q -p no:cacheprovider` | CPython 3.13.3 | rc 0, `3859 passed, 2 skipped` (the two opt-in real-boundary smokes); 8 browser tests ran |
| `uv run --python 3.14 pytest -q -p no:cacheprovider` (separate environment) | CPython 3.14.6 | rc 0, `3851 passed, 3 skipped` (browser module skipped by design: no browser group there) |

The first full run surfaced `test_only_authorised_modules_declare_behavior`: the new module needed
its `BEHAVIOR_ALLOWED` entry (`application/run_lifecycle.py: PXAPI-25`), added in `f524a8c`.

**A race found after these runs.** Re-running the 3.13 suite at the docs commit on top of
`f524a8c` failed the new narrow-table test once (`scrollLeft` still 0 after the arrow keys). In
isolation it then failed 11 of 12 runs: Chrome animates keyboard scrolling (measured 5, 80, then
201 px over ~200 ms) and the test read the position once, immediately. The green full-suite runs
above had won that race by timing. `e0b0f3a` waits for the region to move (5 s bound): 15 of 15
isolated runs pass, and the `overflow: hidden` mutant is still killed. The product code did not
change; final-head figures are on the PR.

### Real-boundary browser proof at `f524a8c`

`tools/pxapi25_workbench_real_boundary_proof.py --channel chrome`, clean tracked tree, production
wiring (`build_site_acquisition`), CPython 3.13.3, Chrome 154.0.8037.58 headless,
`https://www.rfc-editor.org/`, budget 3, 2026-09-29T11:42:49Z:

- run `px-9f65dfe813754092b1671949205f2d19` `SUCCEEDED` in 2.4 s; stages SITE_DISCOVERY,
  SAMPLING_PLAN, PAGE_ACQUISITION all `SUCCEEDED`; lifecycle violations over the downloaded
  documents: none;
- `selection_complete = false` (`SELECTION_BUDGET_EXHAUSTED`); pages `/`, `/about/contact/`,
  `/about/rfc-editor/`, each `RESPONSE_RECEIVED` HTTP 200 with 13 measurements; 39 measurements,
  39 evidence records; all three opened in the Evidence Inspector;
- validation `BLOCKED`: `ACQUISITION_COMPLETENESS` (`SELECTION_INCOMPLETE`),
  `UNRESOLVED_CONFLICTS_LIMITATIONS` (`DISCOVERY_SOURCE_LIMITED`); `INPUT_CONTRACT` and the other
  four gates `PASS`;
- bundle `artifacts.zip` 11984 bytes, SHA-256 `3ab33f24e6d20840da9620952ebac3454f916f3af91b15a5f1f4111350373706`;
  `artifact_bundle_digest` `sha256:cd7bcaca85eb1fd3fd01d758895c3e1aeeb5266b08bf38bc55477e719de73ec0`,
  recomputed over the downloaded files: equal; the downloaded request's `target_url` equals the
  submitted target; receipt contract-valid and rule-clean; no script, handler or dialog; page not
  scrolling sideways at 375 px. Verdict `PASS`.

Screenshots of this head (not committed): the proof's `result-normal.png`, `result-narrow.png`,
and the deterministic suite's `start-{normal,narrow}.png`, `result-{normal,narrow}.png`,
`journey-normal-result.png`, `result-narrow-tables.png`.

### What the repair does not prove

- The binding is document identity with the submitted request. It proves that the documents are
  *this* submission's; it does not prove that the site analysed is the one the target names
  beyond what discovery already records (the inventory's `target_origin`).
- The lifecycle table describes the multi-page orchestration of this slice only. A new stage or
  failure code needs the table extended — the pin tests go red first. `CANCELLED` has no stated
  stage history, because nothing emits it yet.
- Stage timestamps are not cross-checked against the run's `entered_at` / `finished_at`.
- Keyboard scrolling of the table regions relies on Chromium making scroll containers focusable;
  the regions carry no `tabindex`, role or accessible name, so Safari/Firefox keyboard reach and
  screen-reader announcement were not verified. With overlay scrollbars nothing but the cut-off
  column signals that a table scrolls.
- One real-boundary run of one origin at one point in time, as in §9.

## 11. Target-binding repair — `F-25-R4M-003` (2026-09-30)

**Old head:** `dfb15abfc637b67c5da1a247a0b3495cc7a8336e` (PR #22 head, base `ce4de18`; branch,
HEAD, `origin` and `gh pr view 22` re-verified equal before any edit; Jira comments `16813`,
`16817`, `16819` read). **Repair commit:** `53c98bfbaeaabdc928821a4f7a4d32bb87d0680c`.
`git diff --stat dfb15ab 53c98bf`: 2 files, 141 insertions, 6 deletions —
`src/pxapi/adapters/inbound/workbench.py` and `tests/adapters/test_workbench.py`. Every other
path, including `contracts/`, `src/pxapi/application/`, `src/pxapi/domain/`, `src/pxapi/ports/`,
the views and `.github/`, has an empty diff. No reason code, gate, schema or view changes.

### The defect

§10 closed Finding A with "The Workbench passes the request it admitted" — true, but it passed the
*same object* twice. `Workbench.execute()` handed one mutable request `dict` to the producer
(`self.acquisition(...).run(request)`), then to `ValidateAnalysisRun.run(...,
submitted_request=request)`, and read `request["target_url"]` again for the result page. A
producer that rewrote its input in place therefore rewrote the submission it was validated
against. §10's binding tests did not reach this: they changed a separate copy
(`dict(request, target_url=...)`) or the canonical envelope after the run.

Measured at `dfb15ab` with the new test double (`InPlaceRewritingAcquisitions`: the genuine fake-port
runtime, preceded by `request[member] = value` on the object it was handed), submitted target
`https://example.com/`, budget 4, through `POST /operator/runs`:

| Producer rewrites its input to | Overall before | `INPUT_CONTRACT` before | Target shown before | After |
| --- | --- | --- | --- | --- |
| `https://b.example/` | **`PASS`** | `PASS`, no reasons | `https://b.example/` | `FAIL`: `REQUEST_NOT_BOUND_TO_RUN` at `/analysis_run_request/target_url`; shows `https://example.com/` |
| a credential URL (discovery then refuses it and withholds the request, as it does for such a target) | `BLOCKED` | `NOT_APPLICABLE`, `REQUEST_WITHHELD_BY_POLICY` | the credential URL, secret included | `FAIL`: `REQUEST_MISSING`; shows `https://example.com/` |

### The repair

Before any producer code runs, `execute()` snapshots the admitted request —
`MappingProxyType(copy.deepcopy(request))`, a read-only view of a deep copy nothing else holds —
and hands the producer `copy.deepcopy(dict(snapshot))`, an input of its own. Validation
(`submitted_request=`), the run id and the displayed target are read from the snapshot. The
caller's object is no longer handed to the producer at all. `ValidateAnalysisRun` already takes a
`Mapping`; it needed no change.

Preserved, and tested at the Workbench boundary: a *submitted* credential target driven through
`Workbench.execute` still validates `INPUT_CONTRACT` with exactly `REQUEST_WITHHELD_BY_POLICY`
(over HTTP, admission refuses such a target before any run, unchanged). Lifecycle validation,
failure neutrality, the bundle/receipt split and every view are untouched by the diff.

### RED → GREEN and counter-mutation

At `dfb15ab` plus the new tests only: **6 failed, 1 passed** (the passed one is the preserved
credential-exemption control). The A→B test failed on `assert 'PASS' == 'FAIL'` (the
`INPUT_CONTRACT` state); the credential test on `'REQUEST_WITHHELD_BY_POLICY' not in
{'REQUEST_WITHHELD_BY_POLICY'}`; the four parametrised own-copy tests (`target_url`, `run_id`,
`request_id`, `requested_at`) on `handed is not request`. At `53c98bf` all 7 pass.

Counter-mutation of `53c98bf` (driver writes each mutant, purges `__pycache__` with
`PYTHONDONTWRITEBYTECODE=1`, restores the original bytes and compares them; restore identical):

| Mutant | Result |
| --- | --- |
| producer handed the caller's object (snapshot kept for validation) | killed (rc 1) |
| validation bound to the producer's copy | killed |
| displayed target read from the producer's copy | killed |
| no snapshot at all (the `dfb15ab` aliasing) | killed |

### Regression of the working tree committed as `53c98bf`

| Command | Interpreter | Result |
| --- | --- | --- |
| `uv lock --check`, `uv run ruff check .`, `uv run ruff format --check .` | CPython 3.13.3 | rc 0; `All checks passed!`; `131 files already formatted` |
| `uv run pytest -q -p no:cacheprovider` (`uv sync --locked`, no browser group) | CPython 3.13.3 | `3858 passed, 3 skipped` (two opt-in smokes, the browser module) |
| the same, separate environment, `UV_PYTHON=3.14` | CPython 3.14.6 | `3858 passed, 3 skipped` |
| `PXAPI_BROWSER_TESTS=required PXAPI_BROWSER_CHANNEL=chrome uv run --no-sync pytest tests/browser` | CPython 3.13.3, Chrome | `8 passed` |

These are local runs. Exact-head CI is recorded on the PR, not here.

### What this repair does not prove

- The snapshot protects the submission from the producer it is handed to; it does not make the
  producer correct. A producer that emits another target is now *detected* (`FAIL`), not prevented.
- No real-boundary proof, visual evidence or independent review exists for `53c98bf` yet; §10's
  proof is of `f524a8c`. The browser journey above is the deterministic suite of §6, not a
  real-boundary run.
- The snapshot is read-only at its top level; its values are plain strings today. A future
  request member holding a nested object would be protected by the deep copy (nothing else holds
  it), not by the read-only view.
