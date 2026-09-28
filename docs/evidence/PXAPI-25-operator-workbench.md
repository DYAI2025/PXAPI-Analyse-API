# PXAPI-25 — Operator Workbench & Multi-Page Run Validation v1

**Slice:** Jira `PXAPI-25`, one bounded PR candidate. **This document does not declare `IC`,
`R2G`, `R4M`, a merge or `PXAPI-25` Done** — those are Orchestrator / Product Owner authority.

**Exact base:** `ce4de1820d2516f9b3bf73b11ad9441dbad941ba` (`main`, PXAPI-20.B merged; exact-SHA
`python-compat` run `36405179068` `success`), re-verified with `git ls-remote` before the branch
was created. **Branch:** `agent/pxapi25-operator-workbench`.

**Proven code head:** `32703a67b5af03f5b297e6ad18d996e9ab349d74`. Every executed figure below
names the SHA it was measured on. The commit that carries this document changes documentation
only; a commit cannot contain its own SHA, so that head is re-verified at its own exact SHA (CI
and the real-boundary proof) and those results are recorded on the PR and in Jira, not here.

**Authority:** Jira `PXAPI-25` (description, comments `16735`, `16747`) and the Product Owner's
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
| `INPUT_CONTRACT` | request missing / contract-invalid / bound to another run; manifest budget ≠ declared budget | — | request withheld by policy (credential target refused; the producer persists no request on purpose) |
| `ACQUISITION_COMPLETENESS` | run state unreadable; not terminal; failed by a producer defect (`*_NOT_EMITTABLE`, `SAMPLING_MANIFEST_NOT_ADMISSIBLE`); unclassified failure code; succeeded without manifest or records | run failed technically (target refused, unreachable, discovery provider/timeout/runtime); cancelled; `selection_complete` not `true`; a page with no response; a truncated or undecodable body | — |
| `CANONICAL_VALIDITY` | member missing / unexpected / wrong container; document contract violation (pointer + keyword); contract-semantic rule broken; inventory producer invariant broken | — | — |
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
4. `run_id` and the declared budget are inputs from the caller, not read from the documents under
   validation, so documents cannot vouch for their own binding.
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
second tab gets `409` while the first run is held; no horizontal page scroll at 1280×900 and
375×812.

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
  reload keeps the result; no horizontal scroll at 375 px. Verdict `PASS`, no problems.

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
