# PXAPI-19.B — Discovery Correctness Repair (AD-007 / C-PXAPI-013…016)

**Jira:** `PXAPI-19` — Acquisition Method, Site Inventory & Sampling Manifest v1 (`In Arbeit`)
**Theme:** PXAPI-19 discovery correctness repair. One bounded bug-fix theme inside the already
authorised PXAPI-19.B discovery/canonicalisation boundary. **`PXAPI-20` is not authorised by this
slice and nothing here authorises it.**
**Decision authorities:** Jira `PXAPI-19` comment `16044` (historical `R4M` governance
exception), comment `16045` (implementation repair required); Confluence `55181314` (current DRS
semantics), `54362115` (current acquisition / site-intelligence architecture).
**Implementation base:** `aa75d6b52fe060b76a7cf900617ad5f990901183`, verified before any change.
**Candidate:** `fix/pxapi-19-discovery-correctness`, four commits on top of the base:
`9f19db1b7a8263e355ee9913e4f85a53d10e66b3` (the repair and its tests),
`179107b2a9bdc68a0ec4d26175ae03acdec65082` (three guards the countermutation pass found
asleep), `94939ade509d5b104688d63ee005a153e73cb9b3` (this document) and the commit carrying
the code-review answer of §10, which is the candidate head. A commit cannot record its own
identity, so the exact head SHA is stated on PR #18 and by `git rev-parse HEAD`.

This document records what was verified, by which command, with which result. **It is not an
acceptance decision.** `IC`, `R2G` and `R4M` on this candidate remain Orchestrator authority and
none of the three is declared here. The historical `R4M` for PR #16 stays `UNKNOWN` and is neither
reconstructed nor rewritten. `AD-006` / `AC8` is **not** closed by this slice.

A claim is **VERIFIED** when the author re-derived it with the command shown, in this repository,
on this branch. Every claim below is VERIFIED; nothing here is AGENT_REPORTED.

---

## 1. Start state

Measured before any file was changed.

| Check | Expected | Measured | Command |
| --- | --- | --- | --- |
| working directory | the PXAPI repository | `/Users/benjaminpoersch/pxk-api/PXAPI-Analyse-API` | `pwd` |
| fetched `origin/main` | `aa75d6b52fe060b76a7cf900617ad5f990901183` | identical | `git fetch origin --prune && git rev-parse origin/main` |
| starting `HEAD` | — | `7e5d67eb95f85216eff32d99ff82227cb5786efc` (`feat/pxapi-19b-site-discovery-runtime`) | `git rev-parse HEAD` |
| worktree | clean | `git status --porcelain` printed nothing | `git status --porcelain` |
| main CI run `35284324065` | success on `aa75d6b…` | `event push`, `head aa75d6b…`, `status completed`, `conclusion success`, jobs `py3.13 success` / `py3.14 success` | `gh run view 35284324065 --json …` |
| current mutating PXAPI-19 PR | none | none; the only open PR is legacy `#5` (`feat/pxk-17-contracts-v1`), untouched | `gh pr list --state open` |
| branch `fix/pxapi-19-discovery-correctness` | does not exist | absent locally and on `origin` | `git ls-remote --heads origin …`, `git branch --list …` |
| branch created at | exactly `aa75d6b…` | `git rev-parse HEAD` → `aa75d6b52fe060b76a7cf900617ad5f990901183` | `git checkout -b fix/pxapi-19-discovery-correctness aa75d6b…` |

Twelve `.claude/worktrees/wf_*` entries from an earlier workflow session are present in
`git worktree list`. They are untracked in the main tree, are excluded via `.git/info/exclude`,
and contributed nothing to this candidate: `git status --porcelain` is empty throughout.

---

## 2. Finding reproduction

Each finding was reproduced — or shown not to reproduce — **against the exact base**, before any
source file was touched. The RED counts below were re-derived afterwards in a detached worktree
pinned to `aa75d6b…` carrying the candidate's `tests/` and the base's `src/`
(`git worktree add --detach … aa75d6b…`, then `git checkout 179107b -- tests/`; the worktree
printed `HEAD=aa75d6b…` and `git diff --name-only aa75d6b… -- src/` printed `0`).

### C-PXAPI-013 — malformed-link isolation → **REPRODUCED**

`read_links()` guarded parsing and decoding inside a `try`, but resolved its targets outside it:
`_base_for(...)` and the per-link `urljoin(base, target)` both sat after the block.

Counterexample, at the unit boundary:

```python
read_links(b'<a href="/a">A</a><a href="http://[::1">B</a><a href="/c">C</a>',
           "https://example.com/", None, 120)
```

| Position of the malformed value | Base result |
| --- | --- |
| `href` between two valid siblings | `ValueError: Invalid IPv6 URL` — **both valid links lost** |
| `<base href>` with two valid links | `ValueError: Invalid IPv6 URL` — **both valid links lost** |
| document URL | `ValueError: Invalid IPv6 URL` |
| control: two good links | `n=2`, both resolved |

The raised `ValueError` is not `HtmlUnreadable`, so it passed straight through the
`except HtmlUnreadable` clause in `HttpSiteDiscovery._links` and was caught only by `_guarded`.
End-to-end against a real loopback server, base result:

```
outcomes["SAME_ORIGIN_PAGE_LINKS"] == "RUNTIME_ERROR"   (expected "USED")
forms(report, "SAME_ORIGIN_PAGE_LINKS") == []           (expected two same-origin links)
```

One `<a href="http://[::1">` therefore cost the page every other link it carried, under an
outcome that asserted **our** runtime had failed on a document it had in fact read perfectly.

**Affected authority/semantics:** `SourceOutcome.RUNTIME_ERROR` is defined as "our own runtime"
(`site-inventory.v1` `sources[].outcome`); reporting it here was a false statement about this
analysis, and `RUNTIME_ERROR` is non-admitting, so the admitted population was pinned to zero.

**RED:** 17 failures — `test_a_malformed_href_never_discards_its_valid_siblings` (4),
`test_an_unusable_base_href_falls_back_to_the_document_it_cannot_replace` (4),
`test_an_unusable_document_url_loses_its_links_and_not_our_runtime` (4),
`test_a_malformed_href_is_dropped_rather_than_admitted_unresolved`,
`test_isolating_a_malformed_link_leaves_its_label_bounding_untouched`,
`test_one_unresolvable_href_does_not_cost_the_page_its_other_links`,
`test_an_unusable_base_href_does_not_make_the_documents_links_disappear`,
`test_an_unresolvable_href_is_never_admitted_merely_to_preserve_its_siblings`.

### C-PXAPI-014 — fragment canonicalisation → **REPRODUCED**

Rule 6 of `URL_CANONICAL_BASELINE 1.0.0` states that the fragment is *dropped without being
examined*. `_canonicalise` scanned the complete written form for forbidden characters first.

| Written form | Base key | Base refusal | `is_persistable_form` | `is_admissible` |
| --- | --- | --- | --- | --- |
| `…/leistungen#unsere leistungen` | `None` | `FORBIDDEN_CHARACTER` | `False` | `False` |
| `…/leistungen#unsere\u00a0leistungen` | `None` | `FORBIDDEN_CHARACTER` | **`True`** | `False` |
| `…/leistungen#unsere\u2003leistungen` | `None` | `FORBIDDEN_CHARACTER` | **`True`** | `False` |
| `…/leistungen#a\b` | `None` | `FORBIDDEN_CHARACTER` | **`True`** | `False` |
| `…/leistungen#a%zz` | `…/leistungen` | — | `True` | `True` |
| `…/leistungen#kontakt` | `…/leistungen` | — | `True` | `True` |
| control: `…/leistungen` | `…/leistungen` | — | `True` | `True` |

Two facts matter here. The malformed-escape row shows the rule *already* held where `urlsplit`
did the dropping, which is what makes the character scan the sole defect. And the three rows
marked **`True`** are forms `acquisition#/$defs/public_url` permits: a no-break space, an em
space and a backslash are all outside the schema's excluded set
(`\u0000-\u0020\u007F-\u009F\u2028\u2029`). For those, the page was not merely mis-keyed — it was
**admissible and was lost**, because `is_admissible` requires a canonical identity and there was
none.

**Affected authority/semantics:** `canonical_url_key`'s own rule 6, and through it
`DISCOVERY_METHOD_VERSION` (bound to `CANONICALISATION_VERSION`), `canonical_origin`,
`origin_of_key` and `is_same_origin`, all of which route through `_canonicalise`.

**RED:** 21 failures — `test_a_fragment_is_dropped_without_being_examined` (10),
`test_a_key_from_a_fragmented_form_is_still_idempotent_and_contract_shaped` (10),
`test_an_origin_survives_a_fragment_the_rules_no_longer_examine`.

### C-PXAPI-015 — canonical-seed source truth → **REPRODUCED AS DESCRIBED, BUT NOT REPAIRABLE: CONTRACT CONFLICT**

The described behaviour is present. Measured end-to-end against a real loopback server:

| Seed status | `CANONICAL_SEED` outcome | `SAME_ORIGIN_PAGE_LINKS` outcome | `_status_outcome(status)` |
| --- | --- | --- | --- |
| 200 | `USED` | `USED` | `None` (2xx) |
| 404 / 410 | `USED` | `ABSENT` | `ABSENT` |
| 500 / 503 / 403 | `USED` | `PROVIDER_FAILURE` | `PROVIDER_FAILURE` |
| 204 | `USED` | `EMPTY` | `None` (2xx) |

`CANONICAL_SEED` is initialised as `SourceOutcome.USED` without consulting `seed.status_code`.

**The requested repair produces a document the contract refuses.** Measured by handing the real
use case a report exactly as a status-deriving provider would emit it — no source was mutated:

| Seed outcome | Run state | Failure code | Inventory emitted |
| --- | --- | --- | --- |
| `USED` | `SUCCEEDED` | — | yes |
| `BUDGET_EXHAUSTED` | `SUCCEEDED` | — | yes |
| `TIMEOUT` | `SUCCEEDED` | — | yes |
| **`ABSENT`** | `FAILED` | `SITE_INVENTORY_NOT_EMITTABLE` | **no** |
| **`PROVIDER_FAILURE`** | `FAILED` | `SITE_INVENTORY_NOT_EMITTABLE` | **no** |
| `EMPTY` / `RUNTIME_ERROR` | `FAILED` | `SITE_INVENTORY_NOT_EMITTABLE` | no |

The exact violation, for both:

```
inventory_producer_violations(doc) → ['admitting_outcome_for_contributed_source']
require_emittable_inventory(doc)   → ProducerInvariantViolated:
    site-inventory: producer invariant violated: /sources/0
    [admitting_outcome_for_contributed_source]
```

The conflict is forced by three rules that are all contract authority, not producer choice:

1. **`site-inventory.v1` schema**, `sources[].allOf[0]`: any outcome outside
   `["USED","BUDGET_EXHAUSTED","TIMEOUT"]` pins `candidate_count` to `const: 0`.
2. **`site-inventory.v1` schema**, `candidates`: `minItems: 1`, whose own description states
   "At least one is required and it is the canonical target seed, whose `url_key` equals
   `target_origin`".
3. **`inventory_producer_violations`**: `seed_candidate_present` requires that candidate to exist
   and to name `CANONICAL_SEED` in its provenance; `candidate_count_matches_provenance` then
   forces `CANONICAL_SEED.candidate_count >= 1`.

(2)+(3) make `CANONICAL_SEED`'s count always ≥ 1, and (1) therefore restricts its outcome to
`{USED, BUDGET_EXHAUSTED, TIMEOUT}` in every emittable inventory. `_status_outcome` can return
only `ABSENT` or `PROVIDER_FAILURE` for a non-2xx status — **neither is reachable.**

The second route out, withholding the seed observation so nothing is contributed, was measured
too and is closed by (2) and (3) together:

| Seed outcome | Seed observation emitted | Run state | Failure code |
| --- | --- | --- | --- |
| `ABSENT` | yes / no | `FAILED` | `SITE_INVENTORY_NOT_EMITTABLE` |
| `PROVIDER_FAILURE` | yes / no | `FAILED` | `SITE_INVENTORY_NOT_EMITTABLE` |
| control `USED` | yes | `SUCCEEDED` | — |

Suspending *either* authority alone leaves the other standing; suspending **both** lets the
seedless document through, which is how the pair was proved jointly load-bearing (§6).

Three further pieces of evidence point the same way:

- **All three registered contract examples** carry `CANONICAL_SEED / USED / candidate_count 1` —
  including `site-inventory.discovery-unavailable.example.json`, the example written to exercise
  every *failing* source state (`ROBOTS_DECLARATION MALFORMED`, `SITEMAP TIMEOUT`,
  `SITEMAP_INDEX PROVIDER_FAILURE`, `RENDERED_PAGE_LINKS RUNTIME_ERROR`). Even there the seed is
  `USED`.
- **`SourceId.CANONICAL_SEED` is defined as "the origin the bootstrap established"**, not as the
  seed HTTP document. The origin *was* established and *was* used; the status of the document is
  a different fact.
- **The repository already declares where that status is reported.** The pre-existing test
  `test_a_seed_that_is_not_a_readable_page_still_establishes_the_origin` pins a 404, a 500 and a
  non-HTML seed to `SAME_ORIGIN_PAGE_LINKS` outcomes of `ABSENT`, `PROVIDER_FAILURE` and
  `MALFORMED` respectively, with the origin still established.

**Verdict: NON_MATERIAL as an implementation defect / CONTRACT CONFLICT.** Implementing
C-PXAPI-015 as written would turn every site whose homepage answers 404, 403 or 500 from "an
inventory with one candidate and honest neutral source outcomes" into "no inventory at all, under
a failure code that names *our* producer as defective". That is strictly worse and factually
wrong. **No code change was manufactured.** Per the brief, this finding is returned for Product
Owner review: closing it needs either a contract change or a new `SourceOutcome`, and neither is
authorised here.

**RED: none — 0 of 65 tests in `tests/application/test_discover_site.py` failed against the base.**
The seven tests added for this finding are **locks**, green before and after.

### C-PXAPI-016 — declared discovery bounds → **NON_MATERIAL / DOCUMENTATION-SEMANTICS MISMATCH (both subclaims)**

The materiality gate was answered by measurement against each bound's own wording, before any
code was considered. See §4.

**RED: none — 0 of 18 tests in `tests/adapters/test_discovery_bounds.py` failed against the base.**
The four tests added for this finding are **locks**, green before and after.

---

## 3. Implementation

Only the two reproduced findings produced code.

### C-PXAPI-013 — `src/pxapi/adapters/web/html_links.py`

**Change.** Two narrow `except ValueError` guards, one in `_base_for` and one around the per-link
`urljoin`.

- `_base_for`: a `<base href>` the URL parser will not read is ignored and the document's own URL
  is used — which is exactly what the function already did for every other unusable base
  (`javascript:` among them). The declared rule is unchanged; only its totality is.
- the link loop: an `href` the parser will not read is dropped, and the loop continues.

**Why it is sufficient.** These are the only two call sites that were outside the existing
failure-isolation block. The `_LinkReader` feed, `decode_body` and the parser stay inside the
original `try`, so a document-wide failure is still `HtmlUnreadable` → `RUNTIME_ERROR`.

**Why `ValueError` and not `Exception`.** `urljoin` and `urlsplit` were fuzzed over **2 705 652
calls** — 1 884 exhaustive short strings over a URL alphabet plus 300 000 random strings under
three scheme prefixes, each put through `urlsplit`, `urljoin(v, "/x")` and
`urljoin("https://e.test/", v)` — and raised **`ValueError` and nothing else**. That is
901 884 distinct input strings through three functions; the source comments cite the input
count (`~900k inputs`) and this document the call count, and the two are the same measurement. A wider guard would swallow a defect of ours that has nothing to do with a URL and
present it as a website that linked nowhere. `test_the_link_guard_is_narrow_and_does_not_swallow_a_defect_of_ours`
pins this directly: a `RuntimeError` from that line must still propagate.

**Security / neutrality effect.** Nothing is widened. An unreadable form names no target, so
there is nothing to admit; the Domain refuses such a form as `MALFORMED` in any case, so the
admitted population is identical to what a resolve-then-refuse path would produce. The origin
scope, the target policy and every fetch bound are untouched. The neutrality effect is a
correction: the run no longer claims `RUNTIME_ERROR` — a statement about *our* runtime — for a
document it read successfully.

**Preserved neighbouring behaviour.** All-good resolution, document order, the base-href
precedence rule, label normalisation, the label bound (dropped, never truncated), the
`aria-label`/`title` fallback, `<area>` handling, nested-anchor closing, empty-href handling, and
`HtmlUnreadable` on a decode or parser failure. All **11** pre-existing tests in
`tests/adapters/test_html_links.py` pass unchanged (of the 16 added, 14 were RED and 2 — the
guard-narrowness lock and the decode-failure lock — were green against the base as well).

**One measured consequence, stated plainly.** A document whose *only* anchor names an unreadable
target now reports `EMPTY` where it previously reported `RUNTIME_ERROR`. Both are non-admitting
outcomes pinned to zero candidates, so no inventory changes; what changes is that the run stops
asserting our runtime failed. Which of the two zero-admitting states best fits that narrow case is
not what C-PXAPI-013 names, and the existing `USED`/`EMPTY` rule was left to decide it.
`test_an_unresolvable_href_is_never_admitted_merely_to_preserve_its_siblings` records this.

### C-PXAPI-014 — `src/pxapi/domain/site_identity.py`

**Change.** In `_canonicalise`, the fragment is split off with `value.partition("#")[0]` *before*
the forbidden-character scan, and `urlsplit` is given that addressing part.

**Why it is sufficient.** It is the single point where rule 6 was contradicted. `urlsplit` already
discarded the fragment and `urlunsplit` already emitted an empty one; only the scan ran too early.
Splitting lexically on the first `#` is the same boundary `urlsplit` itself uses. For any value
this function does not refuse, the pre-`#` portion is byte-identical to what `urlsplit` would have
parsed, because `urlsplit`'s removal of `\t`, `\r` and `\n` cannot move the `#` and any such
character *before* it is refused by the scan.

**Why the length bound did not move.** Rule 12 says a written form already longer than the bound
is refused before any other rule runs, and a producer would have to persist the written form,
fragment included. `test_a_written_form_over_the_bound_is_still_refused_before_any_other_rule`
pins both halves, and the countermutation that moves the bound behind the split kills it.

**Security / neutrality effect.** No refusal was narrowed. The same character in a path, a query
or an authority is still `FORBIDDEN_CHARACTER`; credentials are still `CREDENTIALS_PRESENT`; a
malformed authority and a malformed percent escape in path or query are still `MALFORMED`; a
non-http(s) scheme is still `NOT_ABSOLUTE_HTTP`. 21 negative controls cover this and were green
before the repair as well as after — they are regression locks, not new behaviour. The WHATWG
backslash rule is unchanged **where it decides a destination**: `…/a\b` is refused, and only
`…/leistungen#a\b` — where the backslash decides nothing — now keys onto the page it names.

**Preserved neighbouring behaviour.** Totality, determinism and idempotence are re-proved over
every fragment case, and every produced key is validated against the contract's own
`acquisition#/$defs/public_url` validator. All **129** pre-existing tests in
`tests/domain/test_site_identity.py` and all **4** property tests in `test_site_identity_fuzz.py`
pass unchanged; of the 49 added, 21 were RED and 28 — the negative controls and the length-bound
lock — were green against the base as well. `CANONICALISATION_VERSION` was **not** bumped: see §9.

---

## 4. Materiality decisions

### C-PXAPI-016 A — off-origin sitemap declarations

**What the configured limit promises**, verbatim from `src/pxapi/config/discovery_limits.py`:

> `max_sitemap_documents` — "Sitemap documents one discovery may **read**, index documents
> included."

**What the implementation actually bounds.** Measured with `HttpSiteDiscovery._read_sitemap`
instrumented to record every URL actually fetched, and `site_identity._canonicalise` counted:

| Input | Documents read | `canonical_url_key` calls | `SITEMAP` | `REFUSED_SITEMAP` | Wall clock |
| --- | --- | --- | --- | --- | --- |
| 20 000 **off-origin** declarations, `max_sitemap_documents=5` | `['…/sitemap.xml']` — 1 | 40 004 | `ABSENT` | `TARGET_POLICY_REFUSED` | 700 ms |
| 20 000 **same-origin** declarations, `max_sitemap_documents=5` | ≤ 5 | 18 | `BUDGET_EXHAUSTED` | — | 91 ms |

The finding's observation is factually correct and the asymmetry is real: an off-origin
declaration is refused before the queue, so it never fills the queue, so the
`if budget_cut: break` in the declaration loop never fires. The work is **strictly linear** in the
declaration count — measured 5.00–5.03 `_canonicalise` calls per declaration at n = 500, 1 000,
2 000 and 4 000 — never superlinear.

**Is the declared limit violated?** No. Zero declared documents are read; only the conventional
`/sitemap.xml` fallback is fetched. `max_sitemap_documents` bounds documents **read**, and reading
is exactly what an off-origin declaration never causes.

**Can a site force work materially beyond what the limit promises?** The worst case is bounded by
the outer `FetchLimits.max_response_bytes`, measured at the cap:

```
robots.txt body : 2 097 144 bytes / cap 2 097 152  →  99 864 declarations
wall clock      : 2.108 s      (DiscoveryLimits.total_deadline_seconds = 60.0)
within deadline : True
SITEMAP         : ABSENT        REFUSED_SITEMAP : TARGET_POLICY_REFUSED
observations    : 1 (the seed)  sitemap observations : 0
```

**Verdict: NON_MATERIAL / DOCUMENTATION-SEMANTICS MISMATCH.** The declared bound is honoured; the
persisted population is unaffected (zero candidates); the disputed path is already bounded by the
outer response-byte cap at 2.1 s against a 60 s declared deadline. **No code change was made.**
Changing `max_sitemap_documents` to bound declarations rather than documents would be a
reinterpretation of the setting, which the materiality gate forbids.

### C-PXAPI-016 B — `max_page_links` and label multiplication

**What the configured limit promises**, verbatim:

> `max_page_links` — "Distinct written same-origin link **targets** admitted from the seed
> document. A target a menu and a footer both link to counts once."

**What the implementation actually bounds.** Measured with `max_page_links=5`:

| Input | Observations | Distinct written targets | Candidates from this source | Outcome |
| --- | --- | --- | --- | --- |
| one href × 300 distinct labels | 300 | **1** | **1** | `USED` |
| 100 distinct hrefs (control) | 5 | **5** | **5** | `BUDGET_EXHAUSTED` |

The multiplication the finding names is real: 300 `DiscoveryObservation` values carry one target.
But `max_page_links` bounds `forms`, the set of distinct written hrefs, which is precisely what it
says it bounds — and `assemble_candidates` folds observations onto canonical identities, so the
**persisted** population is bounded too. The control row proves the bound genuinely bites rather
than never being reached.

**Are candidate counts bounded even when transient observations exceed the target count?** Yes.
End-to-end through the whole use case — inventory, census manifest and both digest pairs — with a
seed document filled to the outer byte cap:

```
seed document   : 2 097 191 bytes, 84 331 anchors, 1 distinct href, 84 331 distinct labels
wall clock      : 10.443 s   (deadline 60.0 s) → within: True
peak memory     : 65.5 MiB
run state       : SUCCEEDED
candidates      : 2          (max_page_links = 200)
sources         : CANONICAL_SEED/USED/1, ROBOTS_DECLARATION/ABSENT/0,
                  SAME_ORIGIN_PAGE_LINKS/BUDGET_EXHAUSTED/1, SITEMAP/ABSENT/0
```

The transient observations are a classification signal — the label is what lets a menu entry
reading "Kontakt" place a page whose path says nothing — and `site-inventory.v1` represents no
anchor text at all. They are bounded by the same outer byte cap (≤ 116 508 at the shortest usable
anchor).

**Verdict: NON_MATERIAL / DOCUMENTATION-SEMANTICS MISMATCH.** The declared bound is honoured
exactly as written, the persisted population is bounded, and the run completes inside its declared
deadline. **No code change was made.** No census threshold, sampling threshold, product budget,
persisted contract field or dependency was invented.

---

## 5. Files changed

`git diff --name-only aa75d6b… HEAD`:

| Path | Layer | Status | What changed |
| --- | --- | --- | --- |
| `src/pxapi/adapters/web/html_links.py` | adapter | modified | C-PXAPI-013: per-link and per-base `ValueError` isolation; module docstring gains the third rule |
| `src/pxapi/domain/site_identity.py` | domain | modified | C-PXAPI-014: the fragment is split off before rule 1; rule list gains rule 0; two docstrings corrected to say "addressing part" |
| `tests/adapters/test_html_links.py` | tests | modified | C-PXAPI-013 unit RED/GREEN + guard-narrowness lock |
| `tests/adapters/test_site_discovery_adapter.py` | tests | modified | C-PXAPI-013 end-to-end RED/GREEN against a real loopback server |
| `tests/domain/test_site_identity.py` | tests | modified | C-PXAPI-014 RED/GREEN + 21 negative controls + idempotence/contract-shape re-proof |
| `tests/application/test_discover_site.py` | tests | modified | C-PXAPI-015 contract-conflict locks |
| `tests/adapters/test_discovery_bounds.py` | tests | modified | C-PXAPI-016 A/B materiality locks |

`git diff --shortstat aa75d6b… HEAD` over `src/` and `tests/`: **7 files, +473 −16.**
`src/` alone is **+58 −16 across 2 files** (`html_links.py` +29 −5, `site_identity.py` +29 −11),
the larger part of it documentation.

---

## 6. Test evidence

### RED, against the base

Re-derived in a detached worktree at `aa75d6b…` carrying the candidate's `tests/`:

| File | Base result |
| --- | --- |
| `tests/adapters/test_html_links.py` | **14 failed**, 13 passed |
| `tests/adapters/test_site_discovery_adapter.py` | **3 failed**, 60 passed |
| `tests/domain/test_site_identity.py` | **21 failed**, 157 passed |
| `tests/application/test_discover_site.py` | 0 failed, 65 passed — C-PXAPI-015 locks |
| `tests/adapters/test_discovery_bounds.py` | 0 failed, 18 passed — C-PXAPI-016 locks |

**38 RED for the two reproduced findings; 0 RED for the two non-material ones.** That the last
two rows are green against the base *is* the evidence that neither finding is an implementation
defect.

### GREEN, on the candidate

| Gate | Command | Result | rc |
| --- | --- | --- | --- |
| lockfile | `uv lock --check` | `Resolved 29 packages` | 0 |
| lint | `uv run ruff check .` | `All checks passed!` | 0 |
| format | `uv run ruff format --check .` | `102 files already formatted` | 0 |
| full suite, Python 3.13.3 | `UV_PYTHON=3.13 uv run pytest -q` | **2867 passed, 1 skipped**, 2 warnings, 110.47 s | 0 |
| full suite, Python 3.14.6 | `UV_PYTHON=3.14 uv run pytest -q` | **2867 passed, 1 skipped**, 2 warnings, 110.58 s | 0 |

Both interpreters were pinned with `UV_PYTHON` and verified by `sys.version` inside the
environment, because `uv run` re-syncs the default interpreter otherwise. Baseline on `aa75d6b…`
collected **2788** tests; the candidate collects **2868** — **80 added**, of which 38 were RED
against the base and 42 were green there as locks and negative controls. No pre-existing
assertion was changed.

**The single skip is the opt-in real-boundary smoke**, unchanged and still opt-in:

```
SKIPPED [1] tests/smoke/test_real_boundary_smoke.py:34:
    opt-in: set PXAPI_REAL_BOUNDARY_SMOKE_URL to a public target
```

The two warnings are pre-existing `starlette`/`anyio` deprecations from the dependency set and are
present on the base.

### Countermutation proof

Every new guard was mutated — removed or inverted — and the tests that guard it required to go
red. Each mutation was verified **on disk** before its tests ran, each wrote to its own log, each
demanded an explicit non-zero `pytest` rc, and each restore was verified with `git diff --quiet`.

| Mutation | `pytest` rc | Verdict |
| --- | --- | --- |
| `013-base-guard-removed` | 1 | KILLED |
| `013-link-guard-removed` | 1 | KILLED |
| `013-link-guard-widened-to-Exception` | 1 | KILLED |
| `014-scan-the-whole-written-form-again` | 1 | KILLED |
| `014-forbidden-set-loses-the-backslash` | 1 | KILLED |
| `014-length-bound-moved-behind-the-split` | 1 | KILLED |
| `015-admitting-set-widened-to-ABSENT` | 1 | KILLED |
| `015-seed-candidate-rule-suspended` | 0 | survives alone — second authority holds |
| `015-seed-minItems-relaxed-in-the-schema` | 0 | survives alone — second authority holds |
| `016A-off-origin-declarations-enter-the-queue` | 1 | KILLED |
| `016B-distinct-target-bound-removed` | 1 | KILLED |
| `016B-observations-keyed-on-href-only` | 1 | KILLED |
| `NOOP-driver-canary` | 0 | green as required — the driver can tell the difference |

`mutations that did not behave as required: 0`, `final working tree clean: True`, driver rc 0.

The two single-authority survivors are the expected result, not a gap: the seedless-inventory
route is closed by `minItems: 1` **and** by `seed_candidate_present`, so removing either leaves the
other. A **combined** mutation suspending both was run separately and the lock went red
(`pytest rc 1`, both parametrisations failed, `site_inventory` present in the envelope), which is
what makes "two authorities" evidence rather than a claim.

The first pass killed only 9 of 11 and exposed three weak tests of ours — a guard-narrowness case
with no witness, a lock naming one of two authorities, and a multiplication lock that would have
passed on a run emitting a single observation. All three were strengthened in commit `179107b`
before the final pass. One mutation was also found to be malformed rather than the code correct:
an `if False:` edit left a dangling `elif _state_of(seed)` that dereferenced `None` and raised
`AttributeError`, which the use case caught as `SITE_INVENTORY_NOT_EMITTABLE` — the test passed for
a reason the mutation had created. It was rewritten to *suspend* the rule instead of breaking the
function.

### Real boundary

Not exercised. This repair is deterministic unit and integration correctness, and a live public
site is not a substitute for RED/GREEN proof. The opt-in smoke behaviour is preserved byte for
byte. **`AD-006` / `AC8` is not closed by this slice** and nothing here should be read as closing
it.

---

## 7. What deliberately did not change

| Area | State | Proof |
| --- | --- | --- |
| `contracts/` | untouched | base tree `9c450752b230e4474ff136327d066fd5838604aa` = head tree, byte-identical |
| `.github/` | untouched | base tree = head tree |
| `pyproject.toml` | untouched | base blob = head blob |
| `uv.lock` | untouched | base blob = head blob |
| `docs/evidence/PXAPI-19B-site-discovery-runtime.md` | untouched | base blob `68986e4b787ab57b7f36ce17d623d6636ee8dd5e` = head blob |
| `src/pxapi/adapters/web/site_discovery.py` | untouched | not in `git diff --name-only aa75d6b… HEAD` |
| `src/pxapi/config/discovery_limits.py` | untouched | not in the diff |
| `src/pxapi/domain/acquisition_semantics.py` | untouched | not in the diff |
| PXAPI-20 surface | absent | no `page-acquisition-record`, `RenderedPagePort`, Crawl4AI, browser runtime, scoring, projection, PDF, PostgreSQL, queue or worker touched |
| `CANONICALISATION_VERSION` | `1.0.0`, unchanged | see §9 |
| census / sampling thresholds | untouched | `C-PXAPI-005` / `AD-004` remain `MISSING`; no budget invented |

The `contracts/` and `acquisition_semantics.py` edits made during the countermutation pass were
temporary measurements, each restored and verified with `git diff --quiet` in the same run.

---

## 8. New findings

Recorded, **not fixed**, and left for Orchestrator triage. Listed in discovery order;
**NF-5 is the most severe and is the one to read first.** NF-5 and NF-6 were raised by the
read-only code review (§11) and re-derived here rather than accepted as reported.

### NF-1 — `CANONICAL_SEED` cannot express a non-2xx seed at all (severity: medium; needs a decision, not a patch)

This is C-PXAPI-015's residue. The seed source is structurally pinned to an admitting outcome
whenever an inventory is emitted, so no vocabulary exists for "the origin was established and the
seed document answered 404". Today the fact is visible only indirectly, through
`SAME_ORIGIN_PAGE_LINKS`. Closing it requires a contract decision — a new `SourceOutcome`, or a
relaxation of the `candidates`/`seed_candidate_present` pairing. **Not in current scope**, and
deliberately not silently resolved: inventing either would be a producer taking a contract
decision. Evidence in §2.

### NF-2 — an admissible page can still be lost when the fragment carries a raw space (severity: low; contract boundary, not a defect)

After the C-PXAPI-014 repair, `…/leistungen#unsere leistungen` canonicalises correctly, but the
*observation* is still inadmissible because `is_persistable_form` refuses the raw space anywhere
in the written form — that is `acquisition#/$defs/public_url`'s excluded set
(`\u0000-\u0020…`), and `observed_form` is recorded verbatim by design. So the repair recovers the
page for a fragment carrying a backslash or a Unicode space outside that set, and does not for one
carrying an ASCII space or tab. Recovering the latter would mean either persisting a
fragment-stripped `observed_form` — a form nobody served — or changing the contract. **Neither is
authorised here**, and both are arguably correct as they stand. Measured in the §2 table.

### NF-3 — `plan()` canonicalises each sitemap declaration twice (severity: informational; not a defect)

`plan(url)` computes `canonical_url_key(url)` and then calls `in_origin(key)`, which canonicalises
again; with `is_same_origin`'s internal re-canonicalisation the measured cost is ~5
`_canonicalise` calls per declaration. Purely redundant work, no behavioural effect, and bounded
as shown in §4. **Not changed**: touching `site_discovery.py` for a finding this document rules
NON_MATERIAL would blur the materiality verdict, and the brief asks for minimal change.

### NF-5 — the same malformed-value defect is live in `_robots` (severity: HIGH; out of this theme's scope)

`src/pxapi/adapters/web/site_discovery.py:502` resolves every `Sitemap:` declaration with an
unguarded `urljoin(response.final_url, value.strip())`. It is the *same* defect C-PXAPI-013
repairs in `html_links.py`, in a sibling reader of the same theme: one malformed value raises
`ValueError` out of `_robots`, is caught only by `_guarded`, and costs the whole source.

Re-derived on this branch with the repository's own test helpers — not taken from the review:

| `robots.txt` content | `ROBOTS_DECLARATION` | `SITEMAP` | sitemap forms |
| --- | --- | --- | --- |
| control: one good declaration | `USED` | `USED` | `['…/gefunden']` |
| malformed **before** a good declaration | `RUNTIME_ERROR` | `ABSENT` | `[]` |
| malformed **after** a good declaration | `RUNTIME_ERROR` | `ABSENT` | `[]` |
| malformed only | `RUNTIME_ERROR` | `ABSENT` | `[]` |

The declared sitemap and the page it lists are both lost, and the run claims *our* runtime failed
on a `robots.txt` it read perfectly — the same false `RUNTIME_ERROR` this branch closes for
document links.

**Why it was not fixed here.** It is a different source (`ROBOTS_DECLARATION`, not
`SAME_ORIGIN_PAGE_LINKS`) in a different file, and `site_discovery.py` is named in the brief under
C-PXAPI-015 and C-PXAPI-016, for both of which this slice deliberately changed nothing and
certified the file byte-identical to the base. The brief is explicit: "If you independently
reproduce a separate material defect: record it under NEW FINDING and leave it unchanged. Stop for
Product Owner review rather than silently expanding scope." Every C-PXAPI-013 required behaviour is
met without touching it.

**This is a genuine miss in how the repair was carried out**, not only in the finding's wording:
the defect class was fixed at the entry file without sweeping the sibling readers in the same
module for the same pattern. A one-line `grep -rn 'urljoin(' src/` would have surfaced it before
the first commit. The sweep has now been run — `page_fetcher.py:168` and
`analyze_homepage.py:478` are the two other unguarded call sites and are outside this theme
entirely; they are named here so the follow-up has its full list.

**Recommended follow-up:** one authorised change applying the same per-value `except ValueError`
to `_robots`, with the RED/GREEN pair the table above already defines.

### NF-6 — `EMPTY` for an all-unresolvable-links document is a claim about the website (severity: low)

`_links` returns `USED if links else EMPTY`, and `links` is now read *after* the per-href drop. A
document whose anchors are all unresolvable therefore reports `EMPTY`, which that function's own
comment defines as "the contract's word for a source that declared nothing at all" — and the
document did declare links. Before the repair the same case was `RUNTIME_ERROR`, a false claim
about *us*; the repair trades it for a false claim about the *site*, which is the direction this
codebase cares about most.

Both states are non-admitting and pinned to zero candidates, so no inventory differs. Making both
claims true means counting the dropped links and reporting `USED`-with-zero, which changes
`read_links`' return shape — beyond what C-PXAPI-013 names. Recorded in §3 and pinned by
`test_an_unresolvable_href_is_never_admitted_merely_to_preserve_its_siblings`. **Not changed.**

### NF-4 — `docs/context/project-state.md` still names `fe8d838…` as "current main" (severity: informational; already known)

Pre-existing wording drift, named as non-blocking in the task brief. `fe8d838…` remains the
correct integrated 19.B implementation baseline but is no longer current main, which is
`aa75d6b…`. **Not changed**: it is outside this repair's file scope.

---

## 9. Why `CANONICALISATION_VERSION` was not bumped

`DISCOVERY_METHOD_VERSION` is bound to `CANONICALISATION_VERSION`, and the C-PXAPI-014 repair does
change which written forms produce a key. The judgement recorded here — and offered explicitly for
Orchestrator review rather than asserted as settled — is that this is a **repair of a rule that was
already declared**, not a new rule: rule 6 said "dropped without being examined" before this
branch and says it after. No key that was produced before is produced differently now; forms that
had no key acquire the key the declared rules always said they had. A version bump would state
that two inventories of one site are no longer comparable, which would be a stronger claim than the
change supports.

**This is a judgement, not a measurement.** If the Orchestrator reads rule 6's correction as a
method change, the bump belongs in this PR and is a one-line edit.

The read-only review sharpened the argument against the position taken here, and it is
recorded rather than answered: the rule list still calls itself "the whole of version
`URL_CANONICAL_BASELINE 1.0.0`" while now containing a rule 0 and a narrowed rule 1, so one
version string names two behaviours. A consumer diffing two inventories of one site under the
documented "comparable only when the version agrees" guarantee would see candidates appear
(the `#a\b` forms) and could not tell a method change from a change in the site. That is a
real cost of not bumping, and it is the Orchestrator's call, not this slice's.

---

## 10. Code review

One read-only review of the exact diff `aa75d6b…..94939ad`, plus the repository's Sourcery app on
PR #18. Neither was permitted to merge or to widen scope.

| Source | Result |
| --- | --- |
| Sourcery (`gh pr checks 18`) | **pass**, zero inline comments; "Needs a human reviewer" on blast radius only, no action item |
| read-only review, effort `high` | 4 findings, all re-derived locally before being acted on |

| Review finding | Re-derived? | Disposition |
| --- | --- | --- |
| 1 — the same unguarded `urljoin` in `_robots` (HIGH) | **yes**, reproduced with the repo's own helpers | **NF-5**, out of scope, not fixed |
| 2 — the new comment's motivating example is not actually recovered (MEDIUM) | **yes**, `is_admissible` is still `False` for it | **fixed** — the comment now states precisely which fragment classes are recovered and which still need a contract decision |
| 3 — `EMPTY` is a claim about the website (LOW) | already measured in §3 | **NF-6**, not changed |
| 4 — `CANONICALISATION_VERSION` names two behaviours (LOW) | already open in §9 | recorded in §9, Orchestrator's call |

Only finding 2 produced a change, and it is confined to a comment inside a file this branch
already modifies. Findings 1 and 3 are behaviour changes outside what C-PXAPI-013…016 authorise and
were left unresolved on purpose.

## 11. Evidence ceiling

What this document does **not** establish:

1. **No gate decision.** `IC`, `R2G` and `R4M` for PXAPI-19 are Orchestrator authority. None is
   declared here, and the historical `R4M` for PR #16 stays `UNKNOWN` per Jira `16044`.
2. **No real-boundary evidence.** No public site was contacted. `AD-006` / `AC8` is not closed and
   the opt-in smoke was not run.
3. **C-PXAPI-015 is returned, not closed.** The evidence shows the requested repair is
   contract-impossible; it does **not** decide what the contract should say instead.
4. **C-PXAPI-016 is ruled non-material against the bounds as currently worded.** If an authority
   restates what `max_sitemap_documents` or `max_page_links` promises, that verdict must be
   re-measured — the measurements in §4 are the input to such a decision, not a substitute for it.
5. **Worst-case figures are from this machine** (Darwin 25.6.0, Apple Silicon, loopback server).
   2.108 s and 10.443 s are margin evidence against a 60 s deadline, not performance guarantees.
6. **The fuzz is evidence, not proof.** 2 705 652 calls produced only `ValueError` from `urljoin`
   and `urlsplit` on CPython 3.13.3 and the full suite agrees on 3.14.6. A future interpreter
   raising a different type from those functions would surface as an escaping exception, which
   `_guarded` records as `RUNTIME_ERROR` — the pre-repair behaviour, never something quieter.
7. **Mutation coverage is per-guard, not exhaustive.** Thirteen mutations were run; they cover
   every guard this branch adds and the two contract authorities behind the C-PXAPI-015 verdict.
   They are not a mutation score over the module.
8. **The malformed-value repair is not module-wide.** It closes the defect in `html_links.py`,
   which is what C-PXAPI-013 names. The identical pattern is still live in `_robots`
   (NF-5, re-derived and HIGH) and unguarded at `page_fetcher.py:168` and
   `analyze_homepage.py:478`. Reading this slice as "malformed URL values are now isolated"
   would be wrong; it isolates them in one reader.
9. **No Jira or Confluence write occurred.** No merge occurred. No deployment occurred.
