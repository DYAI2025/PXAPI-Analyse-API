# PXK-20.A — Actionable Diagnostic Finding Core v0

**Slice:** `PXK-20.A` — a bounded implementation slice of Jira `PXK-20`. `PXK-20.A` is **not** a
Jira key; the contract's `owner_slice` is therefore `PXK-20`.
**Date:** 2026-09-07
**Authority:** Confluence `49709119` — *PXAPI — Business-First Delivery Reconcile — Real
Functionality First — 2026-09-06*; architecture baseline Confluence `39846055`; Jira `PXK-20`.
**Status of every claim below:** `AGENT_REPORTED`. Each is re-derivable by the command printed
beside it; none has been confirmed by independent PO or GitHub review.

**No production readiness is claimed.** See section H for what this slice explicitly does not
prove.

---

## A. Source baseline

| Fact | Exact value | How verified |
| --- | --- | --- |
| Repository | `DYAI2025/PXAPI-Analyse-API` | `git remote get-url origin` |
| Base `main` | `b2442913d1c2612aad08f9ce2d72d630b17770de` | `git fetch origin main && git rev-parse origin/main` |
| Base tree | `da15858171183f7c7b67a789dd5bb32d56cd83f0` | `git rev-parse origin/main^{tree}` |
| Matches the brief's pinned SHA and tree | yes, character-identical | string comparison |
| Drift | none | no reconciliation needed, no STOP condition |
| Branch | `feat/pxk-20a-diagnostic-finding-core` | `git rev-parse --abbrev-ref HEAD` |
| Branch point | `origin/main`, not the previous working branch | `git switch --create … origin/main` |
| `git merge-base --is-ancestor origin/main HEAD` | rc `0` | run at branch creation |
| Baseline suite before any change | `1106 passed`, rc `0` | `uv run pytest -q` |
| Baseline `uv lock --check` | rc `0` | `uv lock --check` |

PR #5 was neither read as an implementation base, branched from, nor modified.

## B. Project-source cleanliness

`git status --porcelain` prints nothing after the final commit and after every countermutation
revert. `.claude/homunculus/` remains untracked and isolated through `.git/info/exclude`; no
`.gitignore` rule was added or changed.

## C. What this slice delivers

### The problem it solves

PXK-67 could measure a homepage but could say nothing about it: the envelope carried facts and
stopped. This slice adds the first document that is allowed to speak about a site in ordinary
language — a `diagnostic-finding` — and, more importantly, the structure that stops it from
saying more than the evidence supports.

### The chain, enforced in code

```text
DiagnosticFinding.evidence_refs
  -> WebsiteEvidence.evidence_id
    -> WebsiteEvidence.measurement_refs
      -> MeasurementRecord.measurement_id
```

`src/pxapi/application/derive_findings.py` emits a finding only where **all five** hold:

1. the evidence belongs to this run;
2. the evidence was itself established (performed assessment, `result_state == KNOWN`);
3. the decisive measurement record exists;
4. the evidence actually references it;
5. the measurement belongs to this run and established a value.

There is no code path from a raw measurement to a conclusion. `evidence_refs` is required,
`minItems: 1` and `uniqueItems: true`, so a finding that rests on nothing is not representable.

### The three authorised rules

| rule_id | rule_version | finding_class | decisive metric | fires when |
| --- | --- | --- | --- | --- |
| `HTTP_ERROR_RESPONSE` | `1.0.0` | `HOMEPAGE_HTTP_ERROR_STATUS` | `HTTP_STATUS` | `KNOWN`, INTEGER, `>= 400` |
| `NON_HTTPS_FINAL_TRANSPORT` | `1.0.0` | `HOMEPAGE_FINAL_TRANSPORT_NOT_HTTPS` | `TRANSPORT_IS_HTTPS` | `KNOWN`, BOOLEAN, exactly `false` |
| `MISSING_HOMEPAGE_TITLE` | `1.0.0` | `HOMEPAGE_TITLE_MISSING` | `PAGE_TITLE_PRESENT` | `KNOWN`, BOOLEAN, exactly `false` |

Emission order is pinned to that table order, not to the order documents were built in.

Each rule's four product texts are **constants, not templates**. There is no formatting step
anywhere in `derive_findings`, which is why a 418 and a 503 carry byte-identical texts while the
number stays in the contract-validated measurement record.

### Contract inventory change

| Fact | Value |
| --- | --- |
| Contracts before | 6 |
| Contracts after | 7 |
| Added | `diagnostic-finding` |
| Contract id | `urn:pxapi:schema:diagnostic-finding:1.0.0` |
| Version | `1.0.0` |
| Role / status | `core` / `active` |
| **`owner_slice`** | **`PXK-20`** (not `PXK-20.A`) |
| `manifest.json` diff | `14` additions, **`0` deletions** (`git diff --numstat`) |
| Existing entries changed | none |
| Shared definitions added | none — the contract reuses `common` only |

Not created and not registered: `product-diagnosis`, `contextual-diagnosis`, `scorecard`,
`score-model-definition`.

### Changed files

| File | Why |
| --- | --- |
| `contracts/v1/schemas/diagnostic-finding.v1.json` | the new contract |
| `contracts/v1/manifest.json` | registers it additively |
| `contracts/v1/examples/diagnostic-finding*.json` | one valid example per rule |
| `tests/contracts/fixtures/invalid/diagnostic-finding/*` | 11 targeted invalid cases + the expectation index |
| `tests/contracts/test_diagnostic_finding.py` | the contract-specific structural proofs |
| `src/pxapi/domain/findings.py` | the three rules: triggers plus fixed texts |
| `src/pxapi/application/derive_findings.py` | the chain, and everything that must break it |
| `src/pxapi/application/analyze_homepage.py` | derives findings and composes them into the envelope |
| `src/pxapi/adapters/inbound/http_api.py` | validates the new member on the way out |
| `tests/domain/test_findings.py` | rule triggers from both sides; texts are not templates |
| `tests/application/test_derive_findings.py` | neutrality matrix, chain integrity, determinism |
| `tests/application/test_analyze_homepage.py` | integration through the real use case |
| `tests/adapters/test_http_api.py` | the member crosses the boundary and is gated there |
| `tests/test_package_scaffold.py` | the behavior scope gate, narrowed for the two new modules |
| `README.md` | envelope membership, the rules, and what an empty list does not mean |
| `docs/evidence/PXK-20A-…md` | this record |

No dependency was added. `pyproject.toml` and `uv.lock` are untouched.

## D. Gates

Run on the final tree, after every countermutation had been reverted.

| Gate | Command | Result |
| --- | --- | --- |
| Lock | `uv lock --check` | rc `0` |
| Lint | `uv run ruff check .` | `All checks passed!`, rc `0` |
| Format | `uv run ruff format --check .` | `61 files already formatted`, rc `0` |
| Suite, Python 3.13 | `uv run pytest -q` | `1391 passed`, rc `0` |
| Suite, Python 3.14 | `uv run --python 3.14 pytest -q` | `1391 passed`, rc `0` |

Suite growth: `1106` → `1391` (`+285`).

## E. Countermutation evidence

Nine mutations, each applied to a clean tree, each reverted before the next. The driver refuses
to start when `git status --porcelain` is non-empty, asserts the edit landed on disk, asserts
the working tree differs from `HEAD`, and asserts the tree is clean again after the revert.

| # | Mutation | RED tests |
| --- | --- | --- |
| M1 | `status >= HTTP_ERROR_THRESHOLD` → `>` | `4` — incl. `test_the_r1_threshold_is_inclusive_at_four_hundred` |
| M2 | R2 `_boolean_value(result) is False` → `is True` | `7` — incl. `test_a_transport_observed_as_https_does_not_fire_r2` |
| M3 | R3 `_boolean_value(result) is False` → `is True` | `8` — incl. `test_an_overlong_but_present_title_is_not_a_missing_title` |
| M4 | evidence `_established` gate dropped | `27` — the whole evidence-side neutrality matrix |
| M5 | measurement `_established` gate dropped | `3` — `test_a_record_that_contradicts_itself_is_not_trusted_for_a_finding` |
| M6 | `evidence["measurement_refs"]` → every measurement in the run | `7` — incl. `test_evidence_that_references_a_different_measurement_produces_no_finding` |
| M7 | measurement run filter dropped | `3` — `test_a_finding_cannot_rest_on_a_measurement_from_another_run` |
| M8 | evidence run filter dropped | `3` — `test_evidence_from_another_run_cannot_carry_a_finding_into_this_one` |
| M9 | `rule.finding_summary` → `f"{rule.finding_summary} Observed: {result}"` | `1` — `test_a_teapot_and_an_unavailable_service_read_identically` |

M9 is the authoritative no-interpolation proof: the interpolated text still satisfies the
contract (single line, within the bound), so only the behavioural 418-vs-503 equality catches it.

**Two gates in the driver itself failed before they passed**, and are recorded because a gate
that has never failed is `not_run`, not `passed`:

* zsh does not word-split an unquoted parameter, so the first driver passed all nine mutation
  names as one argument and then passed both test paths as one path. `pytest` returned rc `4`
  (`no tests ran`) while the loop printed `reverted; tree clean`. Fixed with an explicit array
  and `${=var}`, and the driver now treats any rc other than `1` as a failure of the mutation.
* the first driver reused one `run.txt` and reported M3's result as M2's. Fixed with one output
  file per mutation; M3 re-run in isolation confirmed the R3 failure set.

Residue check after the pass: `git diff HEAD --stat` empty, and each mutation marker greps to
`0` occurrences under `src/`.

## F. Real-boundary smoke — **exploratory**

Live public-network requests. **Not a CI gate**, and no acceptance condition depends on them.

| Target | Observed | `diagnostic_findings` |
| --- | --- | --- |
| `http://www.python.org/` | 200, 1 redirect, final HTTPS, title present | `[]` |
| `https://www.python.org/pxk20-does-not-exist/` | 404, HTTPS, title present | `["HTTP_ERROR_RESPONSE"]` |
| `http://example.com/` | 200, plain HTTP, title present | `["NON_HTTPS_FINAL_TRANSPORT"]` |
| `http://neverssl.com/` | fetch timed out | `[]` |

The `neverssl.com` run was unplanned and is the most useful of the four: a real timeout produced
an empty finding list rather than any negative statement about the site.

The 404 run's chain, read out of the emitted JSON:

```text
finding_id     px-d734e30e872e4086bca8e85c9b6da915  HTTP_ERROR_RESPONSE 1.0.0 HOMEPAGE_HTTP_ERROR_STATUS
  evidence_id  px-e910a72882434b7d9c7fd9c4d26c49a4  {collection_mode: MEASURED, result_state: KNOWN}
    measurement_id px-8e5ea7931c54483790c65fdb2fb21f3d  HTTP_STATUS  {value_type: INTEGER, integer_value: 404}
```

The emitted `finding_summary` reads *“The analysis client received an HTTP status of 400 or
above for the analysed homepage.”* — the measured `404` appears nowhere in it.

R3 has no real-boundary run: no stable public homepage was used that lacks a title. It is proven
through the loopback integration server instead.

## G. Reviewability

| Fact | Value |
| --- | --- |
| Files changed vs `origin/main` | 29, this document included |
| Additions / deletions | `+2117` / `-11` |
| `manifest.json` deletions | `0` |
| Unexpected files | none — every path is under `contracts/`, `src/`, `tests/`, `README.md`, `docs/` |
| Dependency changes | none |
| Diff size | 120,436 bytes, measured with `git diff --cached origin/main` piped to `wc -c` |

## H. What this slice does **not** prove

* not a full Website Diagnosis;
* not full SEO quality — `MISSING_HOMEPAGE_TITLE` is one element of one page;
* not full Trust, Security or Privacy analysis — `NON_HTTPS_FINAL_TRANSPORT` observes one
  response's transport and establishes nothing about TLS configuration or certificate quality;
* not customer-ready reporting — there is no renderer, no projection and no delivery;
* not scoring completeness — there is no score, score model, severity, confidence, ranking or
  intervention level anywhere, deliberately;
* not production readiness — no authentication, authorisation, rate limiting, persistence,
  queueing or deployment.

**An empty `diagnostic_findings` means only that these three rules emitted nothing.** It never
means the website is good, complete, compliant or fully assessed. Each rule states its own bound
in its mandatory `limitation` member for the same reason.

## I. Commits

| SHA | Subject |
| --- | --- |
| `b0b3619` | `feat(pxk-20): turn established evidence into evidence-bound findings` |
| *(this document)* | `docs(pxk-20): record the finding chain, the countermutations and the smoke` |

CI status against the pushed head is **pending / unverified** at the time of writing; it is
reported in the PR only once actually observed.
