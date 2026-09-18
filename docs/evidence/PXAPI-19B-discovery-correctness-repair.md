# PXAPI-19.B — Discovery Correctness Repair (AD-007 / C-PXAPI-013…016)

**Jira:** `PXAPI-19` — Acquisition Method, Site Inventory & Sampling Manifest v1 (`In Arbeit`)
**Theme:** PXAPI-19 discovery correctness repair. One bounded bug-fix theme inside the already
authorised PXAPI-19.B discovery/canonicalisation boundary. **`PXAPI-20` is not authorised by this
slice and nothing here authorises it.**
**Decision authorities:** Jira `PXAPI-19` comment `16044` (historical `R4M` governance
exception), comment `16045` (implementation repair required); Confluence `55181314` (current DRS
semantics), `54362115` (current acquisition / site-intelligence architecture).
**Implementation base:** `aa75d6b52fe060b76a7cf900617ad5f990901183`, verified before any change.
**Candidate:** `fix/pxapi-19-discovery-correctness`, on top of the base:
`9f19db1b7a8263e355ee9913e4f85a53d10e66b3` (the repair and its tests),
`179107b2a9bdc68a0ec4d26175ae03acdec65082` (three guards the countermutation pass found
asleep), `94939ade509d5b104688d63ee005a153e73cb9b3` (this document),
`46669a9d32738e9d7876686b9c273264b4132a09` (the code-review answer of §10 — the head the
Orchestrator reviewed and returned as CHANGES REQUIRED) and the commit carrying the **NF-5
repair of §12**, which is the candidate head. A commit cannot record its own identity, so the
exact head SHA is stated on PR #18 and by `git rev-parse HEAD`.

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
| `src/pxapi/adapters/web/site_discovery.py` | adapter | modified | **NF-5 (§12):** per-declaration `ValueError` isolation in `_robots`; malformed-only → `MALFORMED`; docstring gains the tolerance rule |
| `src/pxapi/domain/site_identity.py` | domain | modified | C-PXAPI-014: the fragment is split off before rule 1; rule list gains rule 0; two docstrings corrected to say "addressing part" |
| `tests/adapters/test_html_links.py` | tests | modified | C-PXAPI-013 unit RED/GREEN + guard-narrowness lock |
| `tests/adapters/test_site_discovery_adapter.py` | tests | modified | C-PXAPI-013 end-to-end RED/GREEN against a real loopback server; **NF-5 scenarios A–G (§12.2)** |
| `tests/domain/test_site_identity.py` | tests | modified | C-PXAPI-014 RED/GREEN + 21 negative controls + idempotence/contract-shape re-proof |
| `tests/application/test_discover_site.py` | tests | modified | C-PXAPI-015 contract-conflict locks |
| `tests/adapters/test_discovery_bounds.py` | tests | modified | C-PXAPI-016 A/B materiality locks |

`git diff --shortstat aa75d6b… HEAD` over `src/` and `tests/`: **8 files, +660 −18.**
`src/` alone is **+93 −18 across 3 files** (`html_links.py` +29 −5, `site_discovery.py` +28 −2,
`site_identity.py` +36 −11), the larger part of it documentation.

**This table is cumulative over the whole branch.** `site_discovery.py` and the 152 added lines in
`test_site_discovery_adapter.py` marked NF-5 arrived *after* the review of head `46669a9…`; §12.7
isolates exactly that delta.

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

> **Scope of this subsection: head `46669a9…`, the head the Orchestrator reviewed.** The figures
> below are that measurement and are kept as recorded. The NF-5 repair of §12 added 8 tests after
> it, and §12.8 added a ninth, so the current head collects **2877** and runs **2876 passed,
> 1 skipped** on both interpreters — **§12.6 carries the gate results for the current head.** The
> lock, lint and format rows below are unchanged on it.

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
| `src/pxapi/adapters/web/site_discovery.py` | **no longer untouched — see §12** | `_robots()` alone changed, for NF-5, after the review of head `46669a9…`. Everything else in the file — `_links`, `_sitemaps`, `_read_sitemap`, `_guarded`, `_Budget`, the bootstrap and the `CANONICAL_SEED` path — is unchanged; `git diff 46669a9… -- src/` touches this one method |
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

### NF-5 — the same malformed-value defect is live in `_robots` (severity: HIGH) → **REPAIRED, see §12**

> **Status update.** This entry is the original finding record and is kept verbatim below. The
> Orchestrator ruled NF-5 a material defect inside the authorised PXAPI-19.B boundary and returned
> head `46669a9…` as CHANGES REQUIRED. **It is repaired; §12 carries the RED/GREEN, the exception
> surface and the countermutation.** The "Why it was not fixed here" paragraph below is therefore
> historical: it records the reasoning at the time, not the current state of the branch.

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
| 1 — the same unguarded `urljoin` in `_robots` (HIGH) | **yes**, reproduced with the repo's own helpers | **NF-5** — judged out of scope at the time; the Orchestrator overruled that and it is now **fixed, see §12** |
| 2 — the new comment's motivating example is not actually recovered (MEDIUM) | **yes**, `is_admissible` is still `False` for it | **fixed** — the comment now states precisely which fragment classes are recovered and which still need a contract decision |
| 3 — `EMPTY` is a claim about the website (LOW) | already measured in §3 | **NF-6**, not changed |
| 4 — `CANONICALISATION_VERSION` names two behaviours (LOW) | already open in §9 | recorded in §9, Orchestrator's call |

Only finding 2 produced a change, and it is confined to a comment inside a file this branch
already modifies. Findings 1 and 3 are behaviour changes outside what C-PXAPI-013…016 authorise and
were left unresolved on purpose.

**Superseded for finding 1.** The Orchestrator's independent review of head `46669a9…` ruled NF-5
material and inside the authorised PXAPI-19.B boundary. That ruling is the authority this branch
follows, and §12 closes it. Finding 3 (NF-6) and findings 2 and 4 are unaffected.

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
   and `urlsplit` on CPython 3.13.3 and the full suite agrees on 3.14.6; the NF-5 probe in §12.1
   adds 1 006 240 calls per interpreter against its own call shape, on both 3.13.3 and 3.14.6,
   with the same single type. A future interpreter raising a different type from those functions
   would surface as an escaping exception, which `_guarded` records as `RUNTIME_ERROR` — the
   pre-repair behaviour, never something quieter.
7. **Mutation coverage is per-guard, not exhaustive.** Nineteen mutations were run — thirteen for
   C-PXAPI-013/014/015/016, five for NF-5 in §12.5, and M6 for the truncation ordering in §12.8.
   They cover every guard this branch adds and the two contract authorities behind the
   C-PXAPI-015 verdict. They are not a mutation score over the module.
8. **The malformed-value repair is still not module-wide.** It closes the defect in
   `html_links.py` (C-PXAPI-013) and in `site_discovery._robots` (NF-5, §12). The same unguarded
   `urljoin` pattern remains at `page_fetcher.py:168` and `analyze_homepage.py:478`, which this
   slice deliberately did not touch: they are separate findings and are untriaged. Reading this
   branch as "malformed URL values are now isolated everywhere" would be wrong; it isolates them
   in the two readers named above.
9. **No Jira or Confluence write occurred.** No merge occurred. No deployment occurred.
10. **NF-5 is closed as a defect, not as a robots specification.** §12 makes one malformed
    declaration cost one declaration. It does not make this a conforming robots.txt parser: only
    the `Sitemap` field is still read, no directive is still applied, and the slice still claims
    no robots compliance of any kind.
11. **`MALFORMED` for a malformed-only robots file is a technical neutrality choice, not a
    contract ruling.** It reuses an existing `SourceOutcome` because inventing one is not
    authorised and `NO_SITEMAP_DECLARATION` would be false. If an authority decides that
    "declared but unresolvable" deserves its own state, that is a contract change and is not
    made here.
12. **The NF-5 tests are scenario coverage, not a fuzz of `_robots`.** Nine tests cover the
    orderings A to G, the never-fetched/never-persisted floor and the truncation ordering, and six
    mutations prove each can fail. No property-based test over arbitrary robots files was written.

---

## 12. NF-5 repair — malformed `Sitemap:` declaration isolation

Added after the code review of §10. The Orchestrator's independent verdict on head
`46669a9d32738e9d7876686b9c273264b4132a09` was **CHANGES REQUIRED** (`IC: NOT_GREEN`,
`R2G: NOT_GREEN`, `R4M: NOT EVALUATED`) because **NF-5 — recorded in §8 of this document as HIGH
and deliberately left unrepaired — is a material defect inside the same authorised PXAPI-19.B
discovery boundary.** It is now closed. **§8's NF-5 entry stands as the original finding record;
this section supersedes its "Why it was not fixed here" paragraph, which is now historical.**

Scope of this section: **NF-5 only.** `C-PXAPI-014` (fragment canonicalisation) is accepted as
implemented and is not extended here; `C-PXAPI-015` (`CANONICAL_SEED`) and `C-PXAPI-016`
(discovery limits) are untouched, as are `contracts/`, `DiscoveryLimits`, dependencies, workflows
and PXAPI-20. The remaining raw-ASCII-space observed-form issue (NF-2) stays a contract-boundary
question and is not addressed.

### Start state, measured before any change

| Fact | Value |
| --- | --- |
| `origin/main` | `aa75d6b52fe060b76a7cf900617ad5f990901183` |
| PR #18 head before mutation | `46669a9d32738e9d7876686b9c273264b4132a09` |
| local `HEAD` | `46669a9d32738e9d7876686b9c273264b4132a09` |
| `git status --porcelain` | empty |
| exact-head CI | push `35294573198` success; pull_request `35294576588` success; Python 3.13 and 3.14 success |
| open review threads | 0 |

### 12.1 Exception surface — re-derived, not inherited

The brief requires stopping rather than guessing if `ValueError` is not the complete exception
surface for the call this repair guards. It was re-derived here against the **exact call shape**
`urljoin(response.final_url, value.strip())` — an absolute http(s) base the fetcher already
retrieved, and an attacker-controlled value — over hand-picked hostile seeds, their pairwise
concatenations, and deterministic random strings over a hostile alphabet:

| Interpreter | calls | raises | exception types | non-`ValueError` types |
| --- | --- | --- | --- | --- |
| CPython 3.13.3 | 1 006 240 | 321 634 | `{'ValueError': 321634}` | `{}` |
| CPython 3.14.6 | 1 006 240 | 321 634 | `{'ValueError': 321634}` | `{}` |

`VERDICT=VALUEERROR_IS_COMPLETE` on both. The narrow guard is therefore the correct and complete
surface, and the same one the accepted `C-PXAPI-013` repair uses in `html_links.py`. This is
evidence, not proof — see the ceiling.

### 12.2 RED reproduction, against the unmodified source at `46669a9…`

`git diff --stat -- src/` was empty at the time of this run: the source was the reviewed head.
Measured with the repository's own loopback server and a recording fetcher.

| Scenario | `robots.txt` | `ROBOTS_DECLARATION` | `SITEMAP` | sitemap forms retained | URLs fetched |
| --- | --- | --- | --- | --- | --- |
| control | one valid declaration | `USED` | `USED` | `['/leistungen']` | `/`, `/robots.txt`, `/karte.xml` |
| **A** | malformed **before** valid | `RUNTIME_ERROR` | `ABSENT` | `[]` — **valid sibling lost** | `/`, `/robots.txt`, `/sitemap.xml` |
| **B** | valid, malformed, valid | `RUNTIME_ERROR` | `ABSENT` | `[]` — **both siblings lost** | `/`, `/robots.txt`, `/sitemap.xml` |
| **C** | malformed **after** valid | `RUNTIME_ERROR` | `ABSENT` | `[]` — **valid sibling lost** | `/`, `/robots.txt`, `/sitemap.xml` |
| **D** | malformed only | `RUNTIME_ERROR` | `ABSENT` | `[]` | `/`, `/robots.txt`, `/sitemap.xml` |
| **E** | no `Sitemap` field | `NO_SITEMAP_DECLARATION` | `ABSENT` | `[]` | `/`, `/robots.txt`, `/sitemap.xml` |
| **F** | valid off-origin + malformed | `RUNTIME_ERROR` | `REFUSED_SITEMAP` **absent from the report** | — | `evil.test` never resolved |

In A–D and F the run claims *our* runtime failed on a `robots.txt` it decoded and parsed
perfectly. In F the off-origin declaration's own source, `REFUSED_SITEMAP`, does not appear at
all — the whole robots source died before it could be reported.

RED test identifiers, all in `tests/adapters/test_site_discovery_adapter.py`:

| Scenario | Test | Pre-repair |
| --- | --- | --- |
| A | `test_a_malformed_sitemap_declaration_before_a_valid_one_does_not_discard_it` | FAILED |
| B | `test_a_malformed_sitemap_declaration_between_two_valid_ones_discards_neither` | FAILED |
| C | `test_a_malformed_sitemap_declaration_after_a_valid_one_does_not_discard_it` | FAILED |
| A–D | `test_a_malformed_declaration_is_never_fetched_and_never_persisted` | FAILED |
| D | `test_robots_declaring_only_malformed_sitemaps_is_malformed_not_a_missing_declaration` | FAILED |
| E | `test_a_robots_file_with_no_sitemap_field_is_still_a_missing_declaration` | PASSED (negative control) |
| F | `test_a_valid_off_origin_declaration_is_refused_not_called_malformed` | FAILED |
| G | `test_the_declaration_guard_does_not_turn_our_own_defect_into_malformed_input` | PASSED (narrowness lock) |

`6 failed, 3 passed, 62 deselected`. E and G are locks, not reproductions: they state what must
*not* change, and they were already green — which is exactly why the countermutation pass in
§12.5 is what proves they can fail at all.

### 12.3 Implementation — `src/pxapi/adapters/web/site_discovery.py`, `_robots()`

One behavioural change: **each declaration is resolved under its own `ValueError` guard, and a
file whose recognised declarations all fail to resolve is `MALFORMED` rather than
`NO_SITEMAP_DECLARATION`.**

```python
if separator and field_name.strip().lower() == "sitemap" and value.strip():
    try:
        declared.append(urljoin(response.final_url, value.strip()))
    except ValueError:
        unresolvable = True

if response.truncated:
    return SourceOutcome.BUDGET_EXHAUSTED, declared
if declared:
    return SourceOutcome.USED, declared
if unresolvable:
    return SourceOutcome.MALFORMED, declared
return SourceOutcome.NO_SITEMAP_DECLARATION, declared
```

**Exception boundary:** `except ValueError` around the individual `urljoin` call — the same narrow
boundary as the accepted `C-PXAPI-013` repair in `html_links.py`, and no broader. Not
`except Exception`.

**Why unrelated errors are not swallowed.** The guard wraps one expression whose only measured
failure mode is `ValueError` (§12.1), so a defect of ours that is not a URL cannot reach it.
Anything else raised anywhere in `_robots` — including from this call on some future interpreter —
still leaves the method, reaches the module-level `_guarded`, and is reported as
`RUNTIME_ERROR` with zero declarations, which is the pre-repair behaviour. The repair can only
make the failure surface *narrower*, never quieter. Test G pins this: `urljoin` is patched to
raise `RuntimeError` for one declaration value alone (so the robots fetch itself still resolves),
and `ROBOTS_DECLARATION` must still be `RUNTIME_ERROR`. Mutation **M2** proves G can fail.

**`MALFORMED` is an existing `SourceOutcome`, not a new one.** It already carries "this source was
served but could not be read", it already sits in `_NON_ADMITTING_PRECEDENCE`, and it is already
structurally pinned to zero admitted. No contract, vocabulary or `SourceOutcome` changed.

**Truncation precedence is unchanged, and the ordering is now load-bearing.** A read-only review
of head `b19539d…` found that this claim was **asserted but not tested**: the whole 2 875-test
suite stayed green when the `MALFORMED` branch was moved ahead of the truncation check, because
the pre-existing truncation test (`test_a_robots_file_cut_by_our_byte_bound_is_a_bounded_read`)
uses a declaration that *resolves*, so `unresolvable` is `False` in it and both orderings agree.
Re-derived and closed here — see §12.8. `response.truncated` is still tested first, so a cut
robots file is still `BUDGET_EXHAUSTED` with whatever declarations were recovered.

**Off-origin is unchanged**: a syntactically valid off-origin declaration resolves normally and is
handed to the existing same-origin/refused-sitemap logic, which still reports it as
`REFUSED_SITEMAP = TARGET_POLICY_REFUSED` without resolving its host.

### 12.4 GREEN evidence

Same harness, same scenarios, after the repair:

| Scenario | `ROBOTS_DECLARATION` | valid declarations retained | malformed omitted | malformed fetched? |
| --- | --- | --- | --- | --- |
| control | `USED` | `['/leistungen']` | n/a | n/a |
| **A** | `USED` | `['/leistungen']` | yes | no — `/`, `/robots.txt`, `/karte.xml` |
| **B** | `USED` | `['/eins', '/zwei']` | yes | no — `/`, `/robots.txt`, `/one.xml`, `/two.xml` |
| **C** | `USED` | `['/kontakt']` | yes | no — `/`, `/robots.txt`, `/karte.xml` |
| **D** | `MALFORMED` | none (none were valid) | yes | no — `/`, `/robots.txt`, `/sitemap.xml` |
| **E** | `NO_SITEMAP_DECLARATION` | n/a | n/a | unchanged |
| **F** | `USED` | off-origin resolved and refused downstream | yes | no — `evil.test` never resolved |

"Never fetched" is asserted directly, not inferred: a recording fetcher captures every URL the
discovery run requested, and the assertion is the **exact fetch list**, plus
`not any("[" in url for url in fetched)` and `not any("[" in o.observed_form for o in
report.observations)` — so the malformed value is proved absent from both the network and the
persisted inventory.

In D the conventional `/sitemap.xml` is still tried. That is the pre-existing fallback for any
robots file that hands the sitemap stage an empty list; it is not new behaviour and `SITEMAP`
reports its own state (`ABSENT` here).

`9 passed, 62 deselected` — the 6 RED tests now pass and the 2 locks stayed green.

### 12.5 Counter-mutation

Five mutations at the time of writing — a sixth, M6, was added in §12.8 after the read-only
review. Each is applied to a pristine copy, verified to have landed, and run into its
**own** output file, each followed by a restore verified byte-for-byte with `cmp` before the next.
A canary ran before the first mutation and after the last: both must be green.

| # | Mutation | Expected to be caught by | rc | Test that failed |
| --- | --- | --- | --- | --- |
| canary-pre | none | — | **0** | `8 passed` |
| M1 | remove the guard entirely (pre-repair resolution) | A, B, C, never-fetched, D, F | **1** | all 6 |
| M2 | widen `except ValueError` → `except Exception` | G | **1** | `…does_not_turn_our_own_defect_into_malformed_input` |
| M3 | guard, but never record it (`unresolvable = False`) | D | **1** | `…only_malformed_sitemaps_is_malformed…` |
| M4 | drop the `MALFORMED` branch | D | **1** | `…only_malformed_sitemaps_is_malformed…` |
| M5 | return `MALFORMED` unconditionally | E | **1** | `…no_sitemap_field_is_still_a_missing_declaration` |
| canary-post | none (restored) | — | **0** | `8 passed` |

`VERDICT=COUNTERMUTATION_PASSED`. Every mutation was detected by the *specific* test written to
catch it, not merely by "something went red": M1 hits isolation, M2 hits guard narrowness, M3 and
M4 hit the two independent authorities behind the malformed-only outcome, M5 hits the negative
control. M3 and M4 matter because the `MALFORMED` outcome is behind **two** conditions — recording
the fact and acting on it — and a single mutation of either must not survive.

### 12.6 Gate results on the NF-5 candidate

| Gate | Command | Result |
| --- | --- | --- |
| lock | `uv lock --check` | `Resolved 29 packages` — no relock |
| lint | `uv run ruff check .` | `All checks passed!` (rc 0, run unpiped) |
| format | `uv run ruff format --check .` | `102 files already formatted` (rc 0) |
| full suite 3.13 | `uv run --python 3.13 pytest -q` | **2876 passed, 1 skipped** (113.68 s) |
| full suite 3.14 | `uv run --python 3.14 pytest -q` | **2876 passed, 1 skipped** (114.88 s), exit 0 |
| C-PXAPI-013 unit | `pytest tests/adapters/test_html_links.py` | 27 passed |
| C-PXAPI-013 e2e | `pytest …test_site_discovery_adapter.py -k "unresolvable_href or unusable_base_href or decoder_cannot_read"` | 4 passed |
| C-PXAPI-014 | `pytest tests/domain/test_site_identity.py` | 178 passed |
| discovery surfaces | adapter + bounds + hostile-input + domain | 109 passed |

Interpreter identity was asserted inside each run (`assert sys.version_info[:2] == …`), not taken
from the flag, because `uv run` re-syncs the default environment. For the 3.14 figure above that
assertion runs **inside pytest itself**, as a `pytest_configure` plugin printing
`[canary] pytest running on 3.14.6`: an earlier 3.14 run was discarded because a concurrent
`uv run --python 3.13` in the same working directory swapped `.venv` underneath it mid-flight. It
reported the same pass count, and was thrown away rather than banked — a suite whose environment
changed under it proves nothing, whatever number it prints.

**The one skip is `tests/smoke/test_real_boundary_smoke.py` — opt-in, requires
`PXAPI_REAL_BOUNDARY_SMOKE_URL`.** It was deliberately not run: the brief forbids substituting a
public smoke for deterministic proof, and `AD-006` / `AC8` remains open.

### 12.7 Files changed by the NF-5 repair

`git diff --numstat 46669a9…` (the reviewed head):

| Path | Layer | Status | What changed |
| --- | --- | --- | --- |
| `src/pxapi/adapters/web/site_discovery.py` | adapter | modified | +28 −2: per-declaration `ValueError` isolation in `_robots`; malformed-only → `MALFORMED`; `_robots` docstring gains the tolerance rule |
| `tests/adapters/test_site_discovery_adapter.py` | tests | modified | +152 −0: scenarios A–G, the never-fetched/never-persisted floor, and the guard-narrowness lock |

Two files. No other behavioural file was touched.

### 12.8 Read-only review of head `b19539d…`, and the one gap it closed

Four independent lenses (correctness, guard-narrowness, safety/bounds, test-quality), each
adversarially verified from two angles by separate agents. 5 findings; 2 refuted by every
verifier, 2 are the same INFO-grade observation reported twice, **1 was material and is repaired
here.**

| # | Lens | Severity | Finding | Disposition |
| --- | --- | --- | --- | --- |
| 1 | guard-narrowness | MEDIUM | `PXAPI-19B-site-discovery-runtime.md:179` states the pre-repair `ROBOTS_DECLARATION` rule | **Refuted, both verifiers.** The row already mispredicted this exact input at `46669a9…`: `Sitemap: http://[` yielded `RUNTIME_ERROR` while the row says `USED (at least one Sitemap:)` for a body that decodes perfectly. The drift predates this diff; the repair only moved which non-`USED` state is reached, from one that blames our runtime to one that is neutral. That file is also **explicitly out of mutation scope** for this repair. Recorded, not changed. |
| 2 | correctness | INFO | `MALFORMED` is keyed on whether `urljoin` raises, not on whether the value names a readable target — `Sitemap: mailto:x@y.test` reports `USED` | **Refuted, both verifiers.** A verifier diffed the whole outcome matrix across both heads: they differ in **exactly one line**, `http://[::1` moving `RUNTIME_ERROR → MALFORMED`. `mailto:`, `javascript:`, `file:///` and a bad port report `USED` at *both* heads. That is what required semantics 3 and 6 ask for: 6 explicitly forbids collapsing a syntactically valid but unusable URL into `MALFORMED`. Boundary recorded, behaviour unchanged. |
| 3, 4 | safety/bounds, test-quality | INFO / LOW | `assert not any("[" in o.observed_form …)` cannot fail for any mutation of `_robots` | **Accurate but not a gap.** Verified independently: all four `DiscoveryObservation` sites are the seed origin (351), seed links (437, 452) and sitemap *entries* (605) — a declaration is never one. The proposed mutation (keep the raw value in `declared`) was simulated read-only: the fetch list and the observation set come back **byte-identical**, because `plan()` rejects the unresolvable value anyway, so semantic 7 is not violated by it; it only mislabels the outcome, which scenario D pins. Semantic 7's binding proof is the exact fetch list — under M1 the test dies at that assertion. The redundant line documents an architectural invariant and matches the idiom already at line 220. **Not changed.** |
| 5 | test-quality | MEDIUM | **Required semantic 5 was asserted, not tested** | **Material — repaired here.** |

**Finding 5, re-derived locally.** Moving `if unresolvable: return MALFORMED` ahead of
`if response.truncated: return BUDGET_EXHAUSTED` left the entire suite green. The pre-existing
truncation test cannot discriminate the two orderings: its declaration resolves, so `unresolvable`
is `False` and both orderings return `BUDGET_EXHAUSTED`. §12.3's "truncation precedence is
unchanged" and §11 item 7's "the mutations cover every guard this branch adds" were therefore
both **claims without a gate behind them** — a guard that has never failed is `not_run`, not
`passed`.

The wrong ordering is not cosmetic: a `robots.txt` that **our own byte bound** cut, whose readable
prefix happens to declare only unresolvable values, would report `MALFORMED` — blaming the site
for a prefix we chose to stop at. That is the neutrality inversion the source vocabulary exists to
prevent, and it is the same class of error NF-5 itself repaired.

**Repair:** one test, `test_a_truncated_robots_declaring_only_unresolvable_sitemaps_still_blames_our_bound`.
No production code changed — `git diff --stat -- src/` is empty for this round; the shipped
ordering was already correct. What was missing was the proof that it is.

**Counter-mutation, now six:**

| # | Mutation | rc | Caught by |
| --- | --- | --- | --- |
| canary-pre | none | **0** | `10 passed` |
| M1 | remove the guard entirely | **1** | 7 tests |
| M2 | widen to `except Exception` | **1** | the guard-narrowness lock |
| M3 | guard but never record it | **1** | the malformed-only test |
| M4 | drop the `MALFORMED` branch | **1** | the malformed-only test |
| M5 | return `MALFORMED` unconditionally | **1** | the no-`Sitemap`-field control |
| **M6** | **`MALFORMED` outranks truncation** (`if unresolvable and not declared:` inserted above the truncation check) | **1** | **the new truncation lock, and only it** |
| canary-post | none (restored) | **0** | `10 passed` |

M6 is deliberately narrow. A broader form — hoisting the branch above the `declared` check too —
also kills A, B, C and F, which would let the kill be credited to tests that were already green
before this round. Gated on `unresolvable and not declared`, it isolates the truncation ordering
alone and kills exactly one test. The pre-existing byte-bound test stays green under it, which is
the finding's own point, now measured.

**What the review confirmed rather than found.** Three lenses ran code against both heads rather
than reading the diff, and independently reproduced: the `ValueError`-only exception surface on a
separate corpus (1 000 076 inputs, both interpreters); that `UnicodeError` is unreachable (the one
`raise UnicodeError` in `urllib.parse` sits in the deprecated `_to_bytes()`, which `urljoin` and
`urlsplit` never call); that `decode_body` is outside the guard, so a decoding defect of ours
still reaches `RUNTIME_ERROR`; and every numeric claim in §5, §12.6 and §12.7. One lens also
measured the cost of the now non-short-circuiting loop at the 2 MiB response bound: **116 508
all-malformed declarations in 0.335 s**, so required semantic 8 holds under adversarial input and
not only in the happy path.

**Not independently verified:** the counter-mutation rows. A read-only review must not mutate the
working tree, so M1–M6 remain the author's measurement, backed by this driver's own canaries
(`canary-pre` and `canary-post` green, every restore `cmp`-verified byte-for-byte, and a
deliberately wrong anchor aborting the run).
