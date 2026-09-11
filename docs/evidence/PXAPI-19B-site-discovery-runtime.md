# PXAPI-19.B — Site Discovery, Inventory & Sampling Runtime

**Jira:** `PXAPI-19` — Acquisition Method, Site Inventory & Sampling Manifest v1 (`In Arbeit`)
**Increment:** `PXAPI-19.B` — Site Discovery / Inventory / Sampling Runtime. `PXAPI-20` is **not
authorized** by this slice and nothing here authorizes it.
**Authorities:** Confluence `55050241` v4 (19.A closeout / 19.B PRE_IMPLEMENTATION binding),
`54362115` (target architecture), `55181314` (DRS gate semantics); `docs/context/project-state.md`,
`decision-ledger.md`, `contradiction-ledger.md`; Jira `PXAPI-19`, all read live on 2026-09-11.
**Binding decisions applied:** `D-PXAPI19-PO-004` … `D-PXAPI19-PO-007`, `D-PXAPI-007`,
`D-PXAPI-008`, `D-PXAPI-010`; `C-PXAPI-005` / `AD-004` (census-to-sampling threshold `MISSING`).
**Implementation base:** `468ce6f187efcd108a930bf977858a3790e4bc52`, verified before any change.

This document records what was verified, by which command, with which result. It is not an
acceptance decision: `R2G` on the final candidate, an independent `R4M`, merge authorisation and
the Jira/Confluence closeout remain Orchestrator/Human authority, and `R4M` is not declared here.
A claim is **VERIFIED** when the author re-derived it with the command shown, in this repository,
on this branch, and **AGENT_REPORTED** when a subagent produced it and it was not re-derived.

## A. Start state

Measured before any file was changed.

| Check | Expected | Measured | Command |
| --- | --- | --- | --- |
| working directory | the PXAPI repository | `/Users/benjaminpoersch/pxk-api/PXAPI-Analyse-API` | `pwd` |
| remote | `DYAI2025/PXAPI-Analyse-API` | `https://github.com/DYAI2025/PXAPI-Analyse-API.git` (fetch and push) | `git remote -v` |
| fetched `origin/main` | `468ce6f187efcd108a930bf977858a3790e4bc52` | identical (`0d1c783..468ce6f main -> origin/main`) | `git fetch origin && git rev-parse origin/main` |
| starting `HEAD` | — | `1ec66b6bc38cc8a3c1959af211797b9220bbb8d1`, the merged 19.A branch | `git rev-parse HEAD` |
| worktree | clean | `git status --porcelain` printed nothing | `git status --porcelain` |
| existing 19.B PR | none | none; the only open PR is legacy `#5` (PXK-17), untouched | `gh pr list --state open` |
| 19.A contract baseline | `926c241…` is an ancestor of `origin/main` | yes (`Merge PR #14: PXAPI-19.A contract foundation`) | `git merge-base --is-ancestor 926c2415… origin/main` |
| baseline suite on `468ce6f` | green | `2228 passed, 2 warnings`, rc 0, identical to the 19.A receipt in `55050241` | `uv run pytest -q` |

The branch `feat/pxapi-19b-site-discovery-runtime` was created at exactly `468ce6f`.

## B. What this slice delivers

### The implementation in one paragraph

A provider-neutral `SiteDiscoveryPort` returns observations and neutral source outcomes and
nothing else. The static-HTTP provider establishes the canonical public origin through the
unchanged `PublicTargetPolicy`, then reads `/robots.txt` for `Sitemap:` lines, a bounded sitemap
tree and the seed document's same-origin links, with every fetch after the bootstrap scoped to that
origin and capped by the run's deadline. The Domain admits, canonicalises and aggregates the
observations, classifies each admissible page and plans a deterministic `CENSUS`. The use case
emits `site-inventory.v1` and `sampling-manifest.v1` only after both pass the six 19.A
contract-semantic rules and thirteen producer guarantees; a bootstrap that establishes no origin
emits neither.

### Files

The implementation is 32 files: 29 added, 3 modified, `+7033 −57`
(`git diff --shortstat 468ce6f 09b716a`). The evidence commit adds this document, 33 files in all.

| Path | Layer | Status | Responsibility |
| --- | --- | --- | --- |
| `src/pxapi/domain/site_identity.py` | domain | added | `URL_CANONICAL_BASELINE 1.0.0`: identity, origin, refusal reasons |
| `src/pxapi/domain/site_discovery.py` | domain | added | discovery vocabulary, admission, aggregation, admissibility, source counts |
| `src/pxapi/domain/page_classification.py` | domain | added | `PAGE_TYPE_BASELINE 1.0.0` |
| `src/pxapi/domain/sampling_policy.py` | domain | added | `CENSUS_FIRST_DETERMINISTIC 1.0.0` |
| `src/pxapi/domain/acquisition_semantics.py` | domain | added | the six 19.A rules and thirteen producer guarantees, fail-closed |
| `src/pxapi/domain/acquisition_digests.py` | domain | added | canonical JSON and the 19.A digest projections |
| `src/pxapi/ports/site_discovery.py` | ports | added | `SiteDiscoveryPort` |
| `src/pxapi/application/discover_site.py` | application | added | the `DiscoverSite` use case |
| `src/pxapi/adapters/web/site_discovery.py` | adapters | added | `HttpSiteDiscovery`: bootstrap, robots, sitemaps, seed links |
| `src/pxapi/adapters/web/html_links.py` | adapters | added | link and bounded-label reader |
| `src/pxapi/adapters/inbound/discover_cli.py` | adapters | added | `python -m pxapi.adapters.inbound.discover_cli <url>` |
| `src/pxapi/config/discovery_limits.py` | config | added | every discovery and selection bound |
| `src/pxapi/adapters/web/page_fetcher.py` | adapters | modified | optional origin scope; deadline cap; watchdog; three crash paths hardened |
| `src/pxapi/adapters/composition.py` | adapters | modified | `build_site_discovery` wiring |
| `tests/test_package_scaffold.py` | tests | modified | twelve `BEHAVIOR_ALLOWED` entries for the twelve new modules |
| 16 new test modules and `tests/smoke/__init__.py` | tests | added | 219 test functions (section C) |
| `docs/evidence/PXAPI-19B-site-discovery-runtime.md` | docs | added | this document |

### How the existing URL safety is reused, and why there is still one authority

`PublicTargetPolicy` (PXK-67) remains the **only** component that classifies a destination as
permitted, reused unchanged by composition: every fetcher discovery builds is a `SafePageFetcher`
over one shared policy instance, so the bootstrap and every discovery fetch get exactly the checks
the homepage analysis gets: http/https only, userinfo refused before any lookup, every address a
name resolves to classified with partial resolution fatal (private, loopback, link-local and cloud
metadata, unspecified, multicast, reserved, carrier-grade NAT, unique-local, IPv4-mapped IPv6), and
the connection pinned to the validated address. No address rule was added, copied or relaxed. An
architecture test names the crawler and browser providers tree-wide and proves none is imported.

What was added is a **scope**, deliberately not a second safety model: an optional predicate on
`SafePageFetcher` that can only refuse. Everything it admits is still classified by the policy,
a scope that admits everything cannot make the shipped policy accept loopback
(`test_a_scope_that_admits_everything_cannot_widen_the_shipped_policy`), and a name that resolves
publicly for the bootstrap and privately a moment later is refused on every later fetch
(`test_every_discovery_fetch_reruns_the_address_policy_so_a_rebound_name_is_refused`).

### Same-origin redirect handling

The bootstrap is the one unscoped fetch, because it is what *establishes* the origin: it reads the
canonical origin root of the submitted target, follows redirects with every hop re-validated and
re-resolved by the policy, and the origin of the response that finally arrives is `target_origin`.

Every later fetch goes through a fetcher scoped to exact origin equality (scheme, host and port).
The scope is consulted on **every hop, before the policy and before any socket**, so a `Location`
leaving the origin is refused without its host ever being resolved. That ordering is proved, not
asserted: a recording policy shows the off-origin URL never reaches `validate()` and a recording
resolver shows the foreign name is never looked up, for a foreign host, a scheme-relative `//host`,
a backslash-smuggled authority, the same host on another port and an `https` to `http` downgrade.
A sitemap refused on the way is reported as its own `REFUSED_SITEMAP` source, so the refusal stays
visible even when a sibling sitemap was read.

### Canonicalisation: `URL_CANONICAL_BASELINE 1.0.0`

`src/pxapi/domain/site_identity.py`, one decision `_canonicalise()` behind both `refuse()` and
`canonical_url_key()`, so the two cannot disagree:

1. a form carrying a control character, DEL, a C1 control, a Unicode separator or space, or a raw
   backslash (which RFC 3986 and WHATWG read differently) is refused;
2. the scheme is lower-cased and must be `http` or `https`;
3. a userinfo component is refused outright, never stripped;
4. the host is lower-cased; a percent sign, a second unbracketed colon or a bracketed value that
   is not one IPv6 literal is refused, and an IPv6 literal takes its compressed form;
5. the port must be ASCII digits in 1..65535, and the scheme's default port is dropped;
6. the fragment is dropped without being examined;
7. percent escapes are upper-cased and an escaped unreserved character is decoded;
8. dot segments are removed per RFC 3986, after rule 7, as section 6.2.2 requires;
9. an empty path becomes `/`; a trailing slash below the root is kept;
10. declared merges: the named tracking parameters (recognised after rule 7) are dropped unless the
    pair carries `;`, empty pairs are dropped and an emptied query disappears; every other
    parameter keeps its written order;
11. a character that may not appear raw is percent-encoded; an existing escape never is;
12. a key the contract's own `public_url` shape would refuse is refused, never truncated, and a
    written form already longer than that bound is refused before any other rule runs.

The contract's `public_url` / `public_origin` patterns and `maxLength` values are restated in the
Domain and pinned character for character against the schema; a fixed-seed property test over
3000 generated forms (1601 keyed, 1399 refused, every refusal reason represented) proves no raise,
every key idempotent, contract-valid and inside its own origin, and refusal exactly when there is
no key.

### Deduplication and provenance

An observation is **admitted** only when its verbatim form satisfies `public_url` and it has a
canonical key; a credential-bearing URL fails both and is dropped before persistence, never stored
as a rejected string. Admitted observations sharing a key become **one** candidate whose
`observed_forms` are every accepted form seen and whose `provenance` is every contributing source,
both sorted. Duplication is never an exclusion, a finding or a penalty: a repeated entry or link
costs nothing against any budget. A source's `candidate_count` is the number of candidates naming
it: what this inventory admitted, not what the source declared.

### Classifier: `PAGE_TYPE_BASELINE 1.0.0`

Seven classes: `HOMEPAGE` (the seed, by construction), `LEGAL`, `CONTACT`, `OFFER`, `PROOF`,
`ABOUT`, `KNOWLEDGE`, tested in that fixed order over whole hyphen-separated words, German and
English, never substrings, with a percent escape treated as a separator. The path is read first,
the query only when the path places nothing, and a bounded anchor label only when neither does.
A page this version cannot place gets no `page_type` in the inventory and the neutral
`UNCLASSIFIED` stratum in the manifest; an excluded candidate is not classified. Raw labels reach
no document.

### Planner: `CENSUS_FIRST_DETERMINISTIC 1.0.0`

Every eligible candidate is selected: the seed at rank 1 (`SEED`), then every other eligible
candidate in ascending `url_key` order (`CENSUS`), an order chosen because it means nothing.
**No selection budget is declared by default**, so the shipped policy is a census over every
eligible candidate of the bound inventory. A budget is a capability a caller may declare, not a
default: where one *is* declared, reaching it keeps `mode = CENSUS`, sets
`selection_complete = false` with `SELECTION_BUDGET_EXHAUSTED`, declares the budget and counts the
remainder under that exclusion reason. Until `fd3ad8a` the composition promoted
`max_selected_pages = 25` — the value of a registered 19.A *example* — into production policy;
that had no product or architecture authority and is recorded as finding `F-PXAPI19B-R4M-001`
below. `STRATIFIED_SAMPLE` cannot be
emitted: no production module holds a string constant naming it, the policy module holds no number
other than `0` and `1`, and the producer refuses any other mode; each is proved by a scan with its
own canary.

### Source outcomes

| Source | State and the condition that produces it |
| --- | --- |
| `CANONICAL_SEED` | `USED`, count 1, whenever an inventory exists |
| `SAME_ORIGIN_PAGE_LINKS` | `ABSENT` (404/410), `PROVIDER_FAILURE` (other non-2xx), `MALFORMED` (declared non-HTML type), `RUNTIME_ERROR` (undecodable, parser or runtime defect), `BUDGET_EXHAUSTED` (link budget, links-examined budget or byte bound), `USED` (links were enumerated; the count may be 0 when all left the origin), `EMPTY` (the document declared no link at all) |
| `ROBOTS_DECLARATION` | `BUDGET_EXHAUSTED` / `TIMEOUT` (our bounds), `TARGET_POLICY_REFUSED` (policy or scope), `PROVIDER_FAILURE` (fetch failure or non-2xx other than 404/410), `ABSENT` (404/410), `RUNTIME_ERROR` (undecodable), `MALFORMED` (HTML or NUL bytes), `USED` (at least one `Sitemap:`), `NO_SITEMAP_DECLARATION` (none); count always 0 |
| `SITEMAP` | one outcome for every sitemap document read: `BUDGET_EXHAUSTED` > `TIMEOUT` > `USED` > `TARGET_POLICY_REFUSED` > `PROVIDER_FAILURE` > `RUNTIME_ERROR` > `MALFORMED` > `EMPTY` > `ABSENT`; a document type or entity declaration, a tree deeper than 8, an unreadable encoding or a malformed body is `MALFORMED`, a body cut by our byte bound is `BUDGET_EXHAUSTED` with what was read |
| `REFUSED_SITEMAP` | `TARGET_POLICY_REFUSED`, count 0, whenever a sitemap reference was declared outside the origin, redirected outside it or refused by the policy; never read |
| bootstrap | no inventory: `TARGET_NOT_PERMITTED`, `SITE_DISCOVERY_TARGET_UNREACHABLE` (name or connection), `SITE_DISCOVERY_PROVIDER_FAILURE` (the target answered, but not followably), `SITE_DISCOVERY_TIMEOUT`, `SITE_DISCOVERY_RUNTIME_ERROR` |
| withheld document | `SITE_INVENTORY_NOT_EMITTABLE`, `SAMPLING_MANIFEST_NOT_EMITTABLE`: a defect of this service |

### Producer semantic validation

`src/pxapi/domain/acquisition_semantics.py`, called by the use case on every document before its
digests are computed and before it can leave the producer:

- **Contract-semantic:** exactly the six 19.A rules, proved to return the same verdict, rule for
  rule and pointer for pointer, as the unchanged 19.A reference in `tests/acquisition/semantics.py`
  on every registered example, every 19.A counterexample and a mutation corpus.
- **Producer guarantees:** thirteen rules that are ours and never applied to someone else's
  document: seed present with `CANONICAL_SEED` provenance and eligible; a contributing source
  reports an admitting outcome; every provenance resolves to a declared source; every source
  identity is a contract code; counts match provenance; every selection is an eligible candidate
  of the bound inventory with a stratum; selections and exclusions account for every candidate
  exactly once; completeness and incompleteness agree; a budget cause declares its budget; the mode
  is `CENSUS`. Every rule has a counterexample that fires exactly that rule.

Both layers fail closed: a violating document is withheld and the run fails with a code naming
our defect. An ambiguous manifest is refused by two layers, the producer gate and the digest
projection, so removing either alone changes nothing: that is defence in depth.

### Compatibility classification

| Surface | Change | Classification |
| --- | --- | --- |
| `contracts/v1/**` | none (`git diff 468ce6f..HEAD -- contracts/` empty) | no contract change |
| `tests/acquisition/**` (19.A reference) | none | unchanged |
| `pyproject.toml`, `uv.lock`, `.github/**` | none | no dependency, CI or infrastructure change |
| Python API | new modules; `SafePageFetcher(scope=None, deadline_cap=None)` keywords, old behaviour as default | additive, backward compatible |
| `SafePageFetcher` behaviour | unsplittable URLs and unencodable request lines return a failure kind instead of raising; a response still arriving at the deadline is `TIMEOUT` | hardening; the homepage analysis is now bounded against a trickling server too |
| CLI | new `discover_cli`; the existing CLI unchanged | additive |
| HTTP API | unchanged; no discovery endpoint | none |
| `analysis-run-state.failure.code` | new open tokens (`SITE_DISCOVERY_*`, `*_NOT_EMITTABLE`); `TARGET_NOT_PERMITTED` reused | additive within an open vocabulary |
| default selection policy (`fd3ad8a`) | the composition declares no `max_selected_pages`; the default census now covers the whole bound inventory instead of its first 25 candidates | **behavioural**: more pages are selected per run, and a default run no longer emits `budgets` or an incomplete selection |
| `DiscoveryLimits.max_selected_pages` (`fd3ad8a`) | removed; it was a selection bound living in discovery config | breaking for any caller reading that field — none exists outside this slice |
| credential-bearing `target_url` (`fd3ad8a`) | refused at the application boundary; the envelope omits `analysis_run_request` | **behavioural**: such a run emits no echo of the request it refused |

## C. Verification

### Gates on the candidate

Measured on `09b716a` with a clean tree (`git status --porcelain` empty). The evidence commit
adds only this document, so `git diff 09b716a..<evidence commit> -- src/ tests/` is empty and these
results carry over; the gates are re-run on the evidence commit itself and reported in the PR.

| Gate | Command | rc | Result |
| --- | --- | --- | --- |
| targeted | `uv run pytest -q` on the 16 new test modules plus `tests/test_package_scaffold.py` | 0 | `573 passed, 1 skipped` |
| acquisition (19.A reference) | `uv run pytest -q tests/acquisition` | 0 | `490 passed` |
| contracts | `uv run pytest -q tests/contracts` | 0 | `654 passed` |
| architecture | `uv run pytest -q tests/architecture` | 0 | `30 passed` |
| full suite, Python 3.13.3 | `uv run pytest -q` | 0 | `2768 passed, 1 skipped` |
| full suite, Python 3.14.6 | isolated worktree at `09b716a`, own venv, `UV_PYTHON=3.14` exported, interpreter printed before and after the run | 0 | `2768 passed, 1 skipped` in 103.94 s |
| lint | `uv run ruff check .` | 0 | `All checks passed!` |
| format | `uv run ruff format --check .` | 0 | `101 files already formatted` |
| lock | `uv lock --check` | 0 | lock file consistent; `pyproject.toml` and `uv.lock` untouched |
| CI | `python-compat` run `34645115573`, event `push`, head `09b716a680c536bf9cc8bf3e291650eb090b2865` | n/a | `py3.13` success, `py3.14` success |

The one skipped test is the opt-in Real-Boundary-Smoke, which runs only when
`PXAPI_REAL_BOUNDARY_SMOKE_URL` is set (section D). The 3.14 run imported `pxapi` from its own
worktree, and the interpreter was checked because a plain `uv run` re-syncs the environment to the
default interpreter: an earlier run labelled 3.14 was in fact 3.13.3 and was discarded.

### The two R4M repairs

Two findings were raised against `18a4aa3` by an independent review and repaired in `fd3ad8a`.
Both were re-derived here before anything was changed, by running the shipped code and reading
what it produced, rather than taken on the report's word.

**`F-PXAPI19B-R4M-001` — an unsupported number had become production policy.** The composition
root built `SelectionBudgets(max_selected_pages=DEFAULT_DISCOVERY_LIMITS.max_selected_pages)`,
and that limit was `25`. Measured on `18a4aa3`: `build_site_discovery().budgets` was
`SelectionBudgets(max_selected_pages=25)`. The value's only provenance is the registered 19.A
example `sampling-manifest.example.json`, which declares `budgets: {max_selected_pages: 25}` to
*illustrate* a declared bound; an example decides no policy, and no PXAPI product or architecture
authority ever set a page ceiling. The repair removes the field from `DiscoveryLimits` outright
rather than setting it to `None` — a bound that does not exist cannot be reached for again — and
the composition now declares no selection budget at all. The default is a true deterministic
census over every eligible candidate of the already bounded inventory.

No replacement number was invented, and that is measured rather than asserted: `grep -rn '\b25\b' src/`
returns nothing, no `DiscoveryLimits` field name contains `select`, and the composition root calls
`SelectionBudgets` with zero arguments, checked by an AST scan that has its own canary.

**`F-PXAPI19B-R4M-002` — a credential could become emitted output.** `analysis-run-request` types
`target_url` as `common#/$defs/url`, which is a structural shape that permits userinfo, so a
request carrying a credential is *schema-valid*. `PublicTargetPolicy` and the CLI both refuse such
a target, but neither stands between a schema-valid request and `DiscoverSite.run()`, which copied
the request verbatim into its failure envelope. Measured on `18a4aa3`, driving the use case with
`https://user:secret@example.com/`: the returned envelope contained `analysis_run_request` with
the credential URL intact, and `"secret" in json.dumps(envelope)` was `True`.

The repair refuses such a request at the application boundary, before it is copied into any
envelope and before the discovery port is asked for anything. The request is **withheld**, not
echoed and not redacted: a redacted target would be a value nobody submitted, and `run_id` already
makes the run traceable. The refusal reuses the Domain's own identity rule, `site_identity.refuse`,
so no second URL authority appears, and the failure code is the existing `TARGET_NOT_PERMITTED`,
so the refusal discloses nothing about *why* the target was refused. Responsibilities are
unchanged: the application boundary does data minimisation, `PublicTargetPolicy` remains the sole
authority on which addresses may be reached, and its source file is byte-identical to the base.

An architecture lock was added with the repair (`tests/architecture/test_safety_authority.py`):
the application layer may import no address primitive, and `is_public_address` may be declared in
exactly one module. It is deliberately *not* a ban on `ipaddress` in the inner layers, because
`domain.site_identity` imports it to compress an IPv6 literal — a question about identity, not
about reachability.

### Gates on the repaired candidate `fd3ad8a`

Measured after the two R4M repairs, on `fd3ad8a740d93d57c240b90dd266a77ea57166af`, working tree
clean before and after every run (`git status --porcelain` empty). **VERIFIED.**

| Gate | Command | rc | Result |
| --- | --- | --- | --- |
| full suite, Python 3.13.3 | `uv run pytest -q` | 0 | `2787 passed, 1 skipped` (baseline `2768 passed, 1 skipped`: +19 collected) |
| full suite, Python 3.14.6 | isolated worktree at `fd3ad8a` outside the repository, own venv, `UV_PYTHON=3.14` exported, worktree `HEAD` and `pxapi.__file__` printed, interpreter printed before *and* after | 0 | `2787 passed, 1 skipped, 2 warnings in 115.35s (0:01:55)` |
| acquisition (19.A reference) | `uv run pytest -q tests/acquisition` | 0 | `490 passed`, unchanged |
| contracts | `uv run pytest -q tests/contracts` | 0 | `654 passed`, unchanged |
| architecture | `uv run pytest -q tests/architecture` | 0 | `34 passed` (was `30`: the new single-authority lock) |
| focused repair modules | `uv run pytest -q` on the four modules the repair touches | 0 | `101 passed` |
| lint | `uv run ruff check .` | 0 | `All checks passed!` |
| format | `uv run ruff format --check .` | 0 | `102 files already formatted` |
| lock | `uv lock --check` | 0 | `Resolved 29 packages`; `pyproject.toml` and `uv.lock` untouched |

Surfaces proved untouched at `fd3ad8a` against the base `468ce6f`, each measured as a diff of
exactly **0 bytes**: `contracts/`, `src/pxapi/adapters/web/target_policy.py`, `pyproject.toml`,
`uv.lock`, `.github/` and `tests/acquisition/`. The target policy being byte-identical is the
evidence that the credential repair added no second egress authority.

### Every commit green

| Commit | Content | Verified | Result |
| --- | --- | --- | --- |
| `22f10cf` | domain | isolated worktree, own venv | `2551 passed`, ruff clean |
| `daf3d8d` | port, adapters, config | isolated worktree, own venv | `2641 passed`, ruff clean |
| `f06fc0d` | use case, wiring, CLI | main tree at identical content | `2689 passed, 1 skipped` |
| `8f61abd` | hostile input becomes a state | main tree before commit | `2698 passed, 1 skipped` |
| `73d22d5` | two survivors killed | CI `34639010861` (push, exact SHA) | `py3.13` success, `py3.14` success |
| `ff510a5` | post-budget fetch stop | main tree; CI `34639861518` (push, exact SHA) | `2702 passed`; `py3.13`, `py3.14` success |
| `f4d1451` | canonical identity fixes | isolated worktree, own venv | pytest rc 0, ruff clean |
| `c45e785` | classifier fixes | isolated worktree, own venv | `2725 passed, 1 skipped`, ruff clean |
| `d3ea846` | neutrality, contract, adapter fixes | main tree before commit | `2744 passed, 1 skipped` |
| `840b99f` | test-strength gaps | isolated worktree, own venv, Python 3.13.3 | `2754 passed, 1 skipped`, ruff check and format clean |
| `09b716a` | robustness bounds | main tree before commit | `2768 passed, 1 skipped`, ruff clean |
| `fd3ad8a` | the two R4M repairs | main tree before commit, Python 3.13.3; 3.14.6 in an isolated worktree | `2787 passed, 1 skipped` on both interpreters; ruff check, format and `uv lock --check` rc 0 |

### Defects the work found in itself, each observed RED before GREEN

- An unclosed, non-truncated sitemap was reported `EMPTY`: `XMLPullParser` raises a `close()`-time
  error without queuing it, and the parser swallowed it as though it were queued.
- Seven inputs raised instead of reporting: a redirect to a raw non-ASCII path, an unsplittable
  redirect or target, a robots file declaring an unknown charset, and a provider, a source read or
  a bootstrap fetch that raises. Three of those paths predate this slice and also affected the
  homepage analysis.
- The smoke's own request log showed a 495 KB sitemap fetched after the entry budget was spent.
- A patch of this slice's own reused a flag name that the budget check in the same loop then
  overwrote, hiding every sitemap refusal; the RED-first tests caught it before it was committed.

### The 30 required items

Every item names the tests that cover it and the counter-mutations that proved those tests fail
when the behaviour is broken (section "Counter-mutation"). File prefixes: `app` = application
use case, `adp` = discovery adapter, `bnd` = bounds, `scp` = fetcher scope, `hst` = hostile input,
`dom` = discovery domain, `idn` = canonical identity, `fuz` = identity fuzz, `pol` = sampling
policy, `sem` = semantics, `dig` = digests, `cls` = classifier, `cli` = CLI and wiring.

| # | Required item | Tests | Proved by |
| --- | --- | --- | --- |
| 1 | same frozen observations, any order: same inventory semantics and digest | `app::test_the_same_frozen_input_in_any_order_yields_the_same_documents`, `dig::test_no_enumeration_order_can_change_an_inventory_digest`, `dom::test_the_population_does_not_depend_on_the_order_observations_arrived_in` | M09, M10 |
| 2 | same inventory and policy: same manifest semantics and digest | `dig::test_the_producer_reproduces_every_registered_manifest_digest`, `dig::test_the_rank_and_not_the_array_position_orders_a_manifest_digest`, `app::test_the_producer_regenerates_the_registered_bounded_census`, `pol::test_the_plan_does_not_depend_on_the_order_the_population_arrived_in` | M11 |
| 3 | canonical target seed exists | `app::test_the_canonical_target_seed_exists_and_is_the_origin`, `app::test_a_report_without_the_seed_is_withheld_rather_than_given_an_invented_one` | M29 |
| 4 | bootstrap failure: no fake inventory or manifest | `app::test_a_failed_bootstrap_produces_no_inventory_and_no_manifest` (6 cases), `app::test_a_report_naming_a_bootstrap_failure_is_a_failure_even_when_it_names_an_origin`, `app::test_a_provider_that_raises_ends_the_run_as_our_runtime_error` | M16, M58 |
| 5 | private target refusal | `adp::test_the_shipped_policy_refuses_every_non_public_bootstrap_target` (`10.0.0.8`; names resolving to `10.0.0.5` and to public plus `192.168.1.1`), `adp::test_every_discovery_fetch_reruns_the_address_policy_so_a_rebound_name_is_refused` | M08 |
| 6 | loopback, link-local and metadata refusal | the same test: `127.0.0.1`, `[::1]`, `[::ffff:127.0.0.1]`, `169.254.169.254`, a name resolving to `169.254.169.254`; `cli::test_the_production_wiring_is_strict_and_refuses_loopback_before_any_connection` | M08 |
| 7 | credential/userinfo rejection | `idn::test_a_form_without_an_identity_is_refused_with_its_reason`, `idn::test_a_credential_bearing_form_is_never_persistable`, `adp::test_a_credential_bearing_target_is_refused_before_any_lookup`, `adp::test_a_backslash_href_a_browser_reads_as_another_host_is_never_admitted`, `app::test_a_credential_bearing_observation_is_never_persisted_or_digested`, `cli::test_a_credential_bearing_target_is_refused_without_being_echoed`; and from `fd3ad8a` the application boundary itself: `app::test_a_credential_bearing_target_never_reaches_an_envelope_or_the_port`, `app::test_no_written_form_of_userinfo_survives_into_anything_this_run_emits` (5 forms), `app::test_the_production_composition_refuses_a_credential_without_resolving_anything` and its non-vacuity canary, `app::test_the_boundary_predicate_answers_only_about_credentials` | M03, M04, M17, M59, MR03, MR04, MR05 |
| 8 | redirect attempting to leave the allowed origin | all of `scp`, `adp::test_a_robots_redirect_leaving_the_origin_is_refused_before_any_lookup`, `adp::test_once_established_the_origin_is_never_left_even_for_the_original_host`, `adp::test_a_sitemap_redirected_out_of_the_origin_stays_visible_beside_one_that_was_read` | M01, M02, M05, M07, M55 |
| 9 | duplicate observations aggregate provenance | `dom::test_two_forms_of_one_page_become_one_candidate_with_aggregated_provenance`, `dom::test_duplication_is_neither_an_exclusion_nor_a_second_candidate`, `adp::test_a_repeated_sitemap_entry_costs_nothing_against_the_entry_budget` | M34, M36, M54 |
| 10 | duplicate semantic identities fail closed at producer validation | `sem::test_the_semantic_gate_alone_refuses_a_document_every_producer_rule_accepts`, `sem::test_the_producer_refuses_every_19a_counterexample_with_its_recorded_violations`, `app::test_a_duplicated_source_identity_fails_closed_before_any_document_is_emitted`, `app::test_an_ambiguous_manifest_is_withheld_through_the_production_path`, `dig::test_an_ambiguous_document_receives_no_digest` | M12, M15 |
| 11 | missing sitemap | `adp::test_a_missing_sitemap_is_absent` | M39 |
| 12 | malformed sitemap | `adp::test_a_malformed_sitemap_admits_nothing`, `adp::test_a_document_that_is_not_a_sitemap_is_malformed`, `adp::test_a_sitemap_declaring_entities_is_not_parsed_at_all`, `bnd::test_a_utf16_sitemap_declaring_entities_is_refused_like_any_other`, `bnd::test_a_deeply_nested_sitemap_is_refused_without_building_a_tree` | M23, M25, M71 |
| 13 | empty valid sitemap | `adp::test_an_empty_valid_sitemap_is_empty`, `adp::test_a_failed_sitemap_is_not_hidden_behind_an_empty_sibling` | M41, M52 |
| 14 | robots missing | `adp::test_a_missing_robots_file_is_absent_and_the_conventional_sitemap_is_tried` | M39 |
| 15 | robots without `Sitemap:` | `adp::test_a_robots_file_without_a_sitemap_declaration_says_exactly_that` | M40 |
| 16 | robots with a valid same-origin sitemap declaration | `adp::test_a_same_origin_sitemap_declaration_is_followed`, `adp::test_robots_directives_other_than_sitemap_are_never_applied`, `bnd::test_a_robots_file_that_begins_with_a_byte_order_mark_is_read_from_its_first_line` | M38, M73 |
| 17 | hostile/off-origin sitemap declaration | `adp::test_an_off_origin_sitemap_declaration_is_refused_without_ever_being_resolved`, `adp::test_a_sitemap_index_is_followed_and_its_off_origin_children_refused`, `adp::test_a_page_listed_inside_a_sitemap_index_is_not_fetched_as_a_sitemap` | M06, M53, M55 |
| 18 | discovery budget exhaustion | `adp::test_the_link_budget_stops_the_read_and_says_so`, the byte-bound, entry, document and request budget tests in `adp`, `adp::test_once_the_entry_budget_is_spent_no_further_sitemap_is_fetched`, `adp::test_a_gzip_sitemap_is_inflated_only_up_to_our_byte_bound`, `bnd::test_the_links_examined_are_bounded_as_well_as_the_links_admitted`, `bnd::test_a_robots_file_of_many_declarations_is_planned_only_up_to_the_queue` | M20, M24, M42, M74, M75, M76 |
| 19 | runtime timeout or failure stays neutral | `adp::test_the_discovery_deadline_turns_every_remaining_source_into_a_timeout`, `adp::test_a_source_the_server_answers_too_slowly_is_a_timeout`, `adp::test_a_bootstrap_the_server_answers_too_slowly_is_a_timeout_not_unreachable`, `bnd::test_a_trickling_body_cannot_outlive_the_fetch_deadline`, `bnd::test_one_slow_source_cannot_hold_a_discovery_past_its_own_deadline`, all of `hst`, `bnd::test_one_sitemap_whose_read_raises_does_not_discard_its_siblings` | M26, M27, M49, M66, M67, M68, M72 |
| 20 | unknown page type: neutral `UNCLASSIFIED` | `app::test_a_page_the_classifier_cannot_place_is_counted_under_the_neutral_stratum`, `pol::test_every_selection_carries_a_stratum_and_an_unplaced_page_the_neutral_one`, `cls::test_a_page_this_version_cannot_place_is_left_unplaced` | M22 |
| 21 | every selection carries stratum, reason and stable identity | `app::test_every_selection_has_a_stratum_a_reason_and_a_stable_identity` (pins `SEED` at rank 1), the `selection_is_*` and `every_selection_carries_a_stratum` counterexamples in `sem` | M28 |
| 22 | ranks dense and unique | `pol::test_ranks_are_dense_and_unique_and_identities_are_selected_once`, the rank rows of the `sem` equivalence corpus | M18 |
| 23 | selection identities unique | the same test, and `unique_selected_url_key` in the `sem` equivalence corpus | equivalence with the 19.A reference |
| 24 | exclusion reasons unique | `pol::test_exclusion_reasons_are_unique_and_sorted`, `pol::test_selections_and_exclusions_account_for_every_candidate_exactly_once` | M19 |
| 25 | `selection_complete=false` requires a technical cause | `sem::test_a_manifest_counterexample_fires_exactly_its_rule[incompleteness_matches_completeness]`, `sem::test_a_complete_selection_that_also_names_a_cause_is_refused`, `app::test_a_budget_bounded_census_names_its_cause_and_its_budget` | M30 |
| 26 | budget-exhausted cause requires a declared budget | `sem::test_a_manifest_counterexample_fires_exactly_its_rule[budget_cause_declares_its_budget]`, `app::test_a_budget_bounded_census_names_its_cause_and_its_budget` | M31 |
| 27 | no technical failure creates score, polarity, severity or site-quality output | `app::test_no_technical_source_state_produces_a_verdict_of_any_kind` (9 outcomes), `app::test_no_failed_run_produces_a_verdict_of_any_kind`, its canary `app::test_the_verdict_scan_finds_a_planted_verdict` | structural: both contracts are closed objects with no such member |
| 28 | producer never emits `STRATIFIED_SAMPLE` | `pol::test_no_population_size_switches_the_method` (12 cases), `pol::test_no_production_module_can_name_a_sampling_mode_but_census`, `app::test_a_plan_the_producer_may_not_emit_is_withheld_and_the_inventory_kept` | M13, M14 |
| 29 | no invented numeric sampling threshold | `pol::test_the_policy_module_carries_no_number_that_could_be_a_threshold` and its canary; 19.A `test_no_sampling_vocabulary_encodes_a_census_threshold` still passes; and from `fd3ad8a`, no invented *selection* ceiling either: `cli::test_the_production_default_selects_a_full_census_and_declares_no_page_ceiling` asserts the composition builds `SelectionBudgets` with zero arguments and that no `DiscoveryLimits` field names a selection bound, with `cli::test_the_selection_budget_scan_sees_a_planted_ceiling` as its canary | the canary plants `500` and is caught; the ceiling canary plants `SelectionBudgets(25)`; MR01, MR02 |
| 30 | controlled Real-Boundary-Smoke | `tests/smoke/test_real_boundary_smoke.py` (opt-in) and the recorded runs in section D | — |

### Counter-mutation

A driver script (scratchpad tooling, not part of the repository; every mutation it applies is
named by ID below and in the 30-item table) takes each mutation in turn. It asserts the targeted
snippet occurs exactly once, writes the mutation and verifies it on disk, runs only the named test
modules in a fresh subprocess, restores the file from the pinned commit and verifies the restore
byte for byte. A mutation counts as **killed only when pytest exits with rc 1**; any other rc is an
error and never a kill. A null mutation (a comment added to the policy module) must survive, which
proves the driver does not report every run as a kill.

| Run | Candidate | Where | Result |
| --- | --- | --- | --- |
| first pass | `8f61abd` | main tree | 36 killed, **2 survived** (M06, M11), canary survived; every restore verified and the tree equal to the candidate, but the clean-tree check failed on the review workflow's untracked worktrees under `.claude/`, which are now excluded locally |
| survivors | `73d22d5` | main tree | M06 and M11 killed after the two tests were strengthened; canary survived |
| robots and sitemap states | `73d22d5` | main tree | M39, M40, M41 killed; canary survived |
| post-budget stop | `ff510a5` | main tree | M24, M42 killed; canary survived |
| after the review fixes | `d3ea846` | isolated worktree, own venv | 62 killed, canary survived: 63 of 63 as expected |
| **final** | `09b716a` | isolated worktree, own venv, `20:36:23Z` to `20:43:02Z`, Python 3.13.3 | **73 killed, canary survived: 74 of 74 as expected**; every mutation applied and restored; tree clean and equal to the candidate afterwards |

| **R4M repairs** | `fd3ad8a` | main tree, clean before and after | **5 killed of 5, null canary survived**; every mutation verified on disk before the run and every restore verified byte for byte |

The five mutations of the repair run, each breaking one repaired guard:

- `MR01` puts `SelectionBudgets(max_selected_pages=25)` back into the composition root — 2 failed;
- `MR02` gives `DiscoveryLimits` a `max_selected_pages` field again — 1 failed;
- `MR03` deletes the credential guard from `DiscoverSite.run()` — 7 failed;
- `MR04` blinds the boundary predicate so it never sees a credential — 8 failed;
- `MR05` emits the withheld `analysis_run_request` anyway — 7 failed;
- `MR06` is the null canary, a comment only, and **survived** at `101 passed`, which is what
  proves the driver is not reporting every run as a kill.

The 73 mutations of the final run, by the guard they break:

- origin boundary and the single safety authority: M01, M02, M05, M06, M07, M08;
- canonical identity: M03, M04, M34, M35, M44, M45, M46, M47, M48, M62;
- admission, aggregation and digests: M09, M10, M11, M12, M17, M36, M56;
- planner and producer guarantees: M13, M14, M18, M19, M22, M28, M29, M30, M31, M57;
- use case and CLI: M15, M16, M58, M59, M65;
- adapter sources: M20, M21, M23, M24, M25, M26, M27, M37, M38, M39, M40, M41, M42, M49, M50,
  M51, M52, M53, M54, M55;
- classifier: M32, M33, M60, M61;
- time, parsing and work bounds: M66 to M76.

M69 is interpreter-dependent: it puts `HTMLParser.close()` back, which is quadratic on the 3.13.3
the driver ran on and measured linear on 3.14.6, so the mutation is expected to survive there (not
run). The guard it proves is the wall-clock test, which passes on both interpreters.

### The registered 19.A examples, regenerated by the producer

Driven through the real use case from their own illustrative discovery input, the producer
regenerates `site-inventory.example.json` (equal as a set, digests identical),
`sampling-manifest.example.json` and `sampling-manifest.bounded-selection.example.json` (equal as
documents, byte for byte after JSON parsing), and reproduces all twelve digests of all six
registered acquisition examples (`test_the_producer_reproduces_every_registered_*_digest`).
Those examples were written by hand before any producer existed, so agreement is evidence the
producer implements what the contracts meant.

### Adversarial review

Workflow `wf_7cf59d0c-e95`: twelve agents, six reviewers and six independent skeptics, each in its
own git worktree detached at the reviewed candidate `8f61abd`, each printing that SHA and its own
`pxapi` import path before any work. The preamble required the import path not to start with the
repository path; the harness places worktrees under `<repo>/.claude/worktrees/`, so that rule was
mis-specified, and each path was checked instead to lie inside the agent's own worktree
(`wf_7cf59d0c-e95-1` to `-12`). **All findings and verdicts are AGENT_REPORTED.**

**49 findings** (1 critical, 16 high, 22 medium, 10 low); skeptic verdicts **49 CONFIRMED, 0
REFUTED, 0 PLAUSIBLE**. Every finding that led to a change was re-derived by the author as a
RED-first test before the fix; the review itself was run against `8f61abd` and did not re-review
the fixes, which are proved by those tests and by the counter-mutation runs.

| Dimension | Findings | Confirmed | Disposition |
| --- | --- | --- | --- |
| SSRF and origin boundary | 4 (1 critical, 1 high, 2 medium) | 4 | fixed: backslash, ASCII ports and Unicode spaces in `f4d1451`; a refusal on the way stays visible (`REFUSED_SITEMAP`) in `d3ea846` |
| 19.A contract conformance | 7 (1 high, 3 medium, 3 low) | 7 | all fixed in `d3ea846` |
| determinism and canonicalisation | 11 (4 high, 4 medium, 3 low) | 11 | fixed in `f4d1451` and `c45e785`; the empty-pair and bare-`?` merges are kept and now declared rules |
| neutrality and scope | 6 (1 high, 4 medium, 1 low) | 6 | fixed in `d3ea846`; the overclaiming docstring rewritten in `f4d1451` |
| robustness under hostile input | 9 (6 high, 2 medium, 1 low) | 9 | F1-F8 fixed in `09b716a`; F9 (`103 Early Hints` treated as final) deferred |
| test strength | 12 (3 high, 7 medium, 2 low) | 12 | two already closed by `73d22d5`; the rest closed in `840b99f`; the smoke stays opt-in by design, and the production wiring now has a default test |

The critical finding (SSRF-1): an href such as `/\\user:pw@evil.test/` resolved on-origin under
`urljoin` and was keyed on-origin, while every browser reads it as a credentialed URL on another
host; it was persisted and selected. The reviewer proposed resolving backslashes the WHATWG way
before `urljoin`; the fix chosen is stricter, refusing any form with a raw backslash, so such an
href is never admitted at all (`adp::test_a_backslash_href_a_browser_reads_as_another_host_is_never_admitted`).

### Reviewability

`git diff --no-ext-diff --unified=0 468ce6f 09b716a | wc -c` = **317200** bytes, the implementation
without this document (src `170297`, tests
`146903`), 2.27 times the `< 140000` convention (Confluence `45907970`). The history splits at
commit `22f10cf` (the Domain and its tests), which alone measures **137026**, under the
convention. The brief allows exactly one 19.B PR, so the slice was not split: whether to review it
as one PR or along that split point is a Product Owner decision.

At the repaired candidate `fd3ad8a` the same measurement is **340448** bytes
(`git diff --no-ext-diff --unified=0 468ce6f fd3ad8a -- src/ tests/ | wc -c`), **2.43** times the
convention. The Product Owner decision for this repair was explicitly *not to split PR #16*, so
the figure is reported rather than acted on.

## D. Real-Boundary-Smoke

**Candidate:** `09b716a680c536bf9cc8bf3e291650eb090b2865`, working tree clean before and after,
Python 3.13.3, run on 2026-09-11 from the operator's machine. **VERIFIED.**

> This is the **pre-repair** run. It records what that candidate really did, including the
> 25-page default this slice has since removed, and it is kept for that reason. Its *manifest*
> figures are superseded by the rerun on `fd3ad8a` at the end of this section; its inventory
> figures are not, and the two runs agreeing on every inventory digest is itself evidence that
> the repair changed selection and nothing upstream of it.

**Commands:** `uv run python -m pxapi.adapters.inbound.discover_cli <target>` for each target, the
opt-in test `PXAPI_REAL_BOUNDARY_SMOKE_URL=<target> uv run pytest tests/smoke/test_real_boundary_smoke.py`,
and an instrumented run that wraps only the fetchers of the real composition to log every request.

**Ceiling:** `DiscoveryLimits(max_requests=8, max_sitemap_documents=5, max_sitemap_entries=500,
max_page_links=200, max_links_examined=2000, max_label_length=120, total_deadline_seconds=60.0,
max_selected_pages=25)`; every fetch `FetchLimits(max_redirects=3, connect_timeout_seconds=5.0,
read_timeout_seconds=10.0, total_deadline_seconds=20.0, max_response_bytes=2097152)`, capped by
what remains of the run's deadline and enforced by the watchdog. Shipped `PublicTargetPolicy`,
real DNS, real sockets.

| | `https://www.rfc-editor.org/` | `https://example.com/` |
| --- | --- | --- |
| started / finished (UTC) | `20:36:39Z` / `20:36:42Z`, CLI rc 0 | `20:36:42Z` / `20:36:43Z`, CLI rc 0 |
| run state | `SUCCEEDED`, both stages `SUCCEEDED` | `SUCCEEDED`, both stages `SUCCEEDED` |
| `target_origin` | `https://www.rfc-editor.org/` | `https://example.com/` |
| sources | `CANONICAL_SEED USED 1`, `ROBOTS_DECLARATION USED 0`, `SAME_ORIGIN_PAGE_LINKS USED 19`, `SITEMAP BUDGET_EXHAUSTED 500` | `CANONICAL_SEED USED 1`, `ROBOTS_DECLARATION ABSENT 0`, `SAME_ORIGIN_PAGE_LINKS USED 0`, `SITEMAP ABSENT 0` |
| candidates | 506, all eligible; `HOMEPAGE 1`, `CONTACT 1`, `ABOUT 2`, `KNOWLEDGE 2`, unclassified 500 | 1: `HOMEPAGE`, eligible |
| manifest | `CENSUS`, `selection_complete: false`, cause `SELECTION_BUDGET_EXHAUSTED`, budget 25; 25 selected (`HOMEPAGE 1`, `CONTACT 1`, `ABOUT 2`, `KNOWLEDGE 1`, `UNCLASSIFIED 20`); `SELECTION_BUDGET_EXHAUSTED 481` | `CENSUS`, `selection_complete: true`; 1 selected; no exclusion |
| inventory `input_digest` | `sha256:b7c56b38069a4d98296baca64d94d7cc32784651df8b08aa6c11b3cef75ff98a` | `sha256:a0863851775c24d26a254897d11b41c42aba36096edb9bc7804015ee0d037b8d` |
| inventory `output_digest` | `sha256:d3b74162e4d60ab0982981c854ae7f2c335096ddbd99ce021f27f864850d25ff` | `sha256:9e916d8a7d658cea6f783067ecd3729e41b4bee7838b4bca929092be252dbdb8` |
| manifest `input_digest` | `sha256:1785628c835052360660f89839c2c9284fd7c3605763ceb8fa72cda9c8c85581` | `sha256:f788f023ddc0c956820deb5fd3bf0bd5be797fa810759f1463ccc47b6d2b363d` |
| manifest `output_digest` | `sha256:34b83d9897da01885988eb05efa518cc6e07b68b5e2bc56f38647d9514c974f2` | `sha256:1d1e126cd160b5ef1386b21ee60f824fe1f382703c59de934142a65f2fdaf480` |
| identities | run `px-ffe5a42c2e4d41c1a97ac3e82b83ef2d`, inventory `px-743f2a8debea42099eab0fbe698a9f34`, manifest `px-ba5372ef0a3344c3866737ad4faf67b2` | run `px-8ad44b69531f44fea0943a93fb588803`, inventory `px-e0699677a2fe4de1b4ef1b3c514695c7`, manifest `px-c9517309668546f093faa60785a1d01d` |
| opt-in pytest smoke | `1 passed` | `1 passed` |

**Request log** (instrumented run on rfc-editor.org, `20:36:43Z`): 4 requests in 1.75 s against a
ceiling of 8: the bootstrap `GET /` (unscoped, 200, 182305 bytes), then, all scoped to the origin,
`/robots.txt` (200, 135 bytes), `/sitemap.xml` (200, 259 bytes, a sitemap index) and
`/sitemap-1.xml` (200, 701403 bytes). No redirect and no truncation. The same run on the earlier
candidate `73d22d5` made 5 requests, the fifth a 495 KB `/sitemap-2.xml` fetched after the entry
budget was spent; commit `ff510a5` removed it.

**Determinism across the real boundary:** the rfc-editor.org inventory `output_digest` and
manifest `output_digest` above are identical to those of the run on `73d22d5` at `19:34:26Z`,
across six commits that changed canonicalisation, the sitemap parser and the adapter. The
inventory `input_digest` differs by design: `d3ea846` made it bind the transient labels. The
manifest `input_digest` differs because it binds the inventory's identity, which is new on every run. The
example.com links outcome moved from `EMPTY` to `USED` with 0 admitted, the confirmed neutrality
fix for a page whose only link leaves the origin, and its `output_digest` moved with it.

**Neutral limitations observed:** the sitemap source stopped at our 500-entry bound; the census
stopped at our 25-page budget and names that cause; 500 of 506 candidates are RFC documents outside
the classifier's SME vocabulary and are `UNCLASSIFIED`; and a budgeted census selects the seed plus
a lexicographic prefix, which is neutral and not representative.

**A third target was excluded.** `https://www.gnu.org/` declares an `http://` sitemap on an
`https` site, a live off-origin declaration. During a preview run the host stopped answering this
client altogether (`curl` status 000 with and without a User-Agent), and the pipeline reported
that as neutral `TIMEOUT` and `PROVIDER_FAILURE`. It is not reproducible, so it is not part of the
recorded evidence; the off-origin paths are covered by loopback tests.

**Evidence ceiling.** This smoke proves the tested boundary only: that two public origins were
established safely through the shipped policy, discovered within declared bounds, reduced to valid
inventories and planned as valid census manifests by the committed code. It does not prove
arbitrary internet crawling, production scale, complete site coverage, browser rendering, PXAPI-20
multi-page acquisition, scoring quality or customer uplift, and a public site can change between
two runs.

### Rerun on the repaired candidate `fd3ad8a`

**Candidate:** `fd3ad8a740d93d57c240b90dd266a77ea57166af`, working tree clean before and after
(`git status --porcelain` empty, printed by the driver), Python 3.13.3, run on 2026-09-11 from
the operator's machine, shipped `PublicTargetPolicy`, real DNS, real sockets. **VERIFIED.**

**Commands:** `uv run python -m pxapi.adapters.inbound.discover_cli <target>` for each target, the
opt-in test `PXAPI_REAL_BOUNDARY_SMOKE_URL=<target> uv run pytest -q tests/smoke/test_real_boundary_smoke.py`,
and a second, instrumented run in which only `SafePageFetcher.fetch` is wrapped — the policy, the
scope and the deadline cap stay exactly as shipped, so the log adds nothing but a request record.

**Ceiling:** `DiscoveryLimits(max_requests=8, max_sitemap_documents=5, max_sitemap_entries=500,
max_page_links=200, max_links_examined=2000, max_label_length=120, total_deadline_seconds=60.0)` —
there is no longer a `max_selected_pages` member — with every fetch under
`FetchLimits(max_redirects=3, connect_timeout_seconds=5.0, read_timeout_seconds=10.0,
total_deadline_seconds=20.0, max_response_bytes=2097152)`, capped by what remains of the run's
deadline and enforced by the watchdog. **No selection budget was declared.**

| | `https://www.rfc-editor.org/` | `https://example.com/` |
| --- | --- | --- |
| started / finished (UTC) | `22:15:58Z` / `22:16:01Z`, CLI rc 0, wall `3.36 s` | `22:16:03Z` / `22:16:04Z`, CLI rc 0, wall `1.12 s` |
| run state | `SUCCEEDED`, both stages `SUCCEEDED` | `SUCCEEDED`, both stages `SUCCEEDED` |
| `target_origin` | `https://www.rfc-editor.org/` | `https://example.com/` |
| sources | `CANONICAL_SEED USED 1`, `ROBOTS_DECLARATION USED 0`, `SAME_ORIGIN_PAGE_LINKS USED 19`, `SITEMAP BUDGET_EXHAUSTED 500` | `CANONICAL_SEED USED 1`, `ROBOTS_DECLARATION ABSENT 0`, `SAME_ORIGIN_PAGE_LINKS USED 0`, `SITEMAP ABSENT 0` |
| candidates discovered / eligible | 506 / 506 | 1 / 1 |
| **selected** | **506** (was 25 on `09b716a`) | 1 |
| `mode` | `CENSUS` | `CENSUS` |
| `selection_complete` | **`true`** (was `false`) | `true` |
| `budgets` member | **absent** (was `{max_selected_pages: 25}`) | **absent** (was `{max_selected_pages: 25}`) |
| `incompleteness` | absent (was `SELECTION_BUDGET_EXHAUSTED`) | absent |
| `exclusions` | `[]` (was `SELECTION_BUDGET_EXHAUSTED 481`) | `[]` |
| strata of the selection | `HOMEPAGE 1`, `CONTACT 1`, `ABOUT 2`, `KNOWLEDGE 2`, `UNCLASSIFIED 500` | `HOMEPAGE 1` |
| inventory `input_digest` | `sha256:b7c56b38069a4d98296baca64d94d7cc32784651df8b08aa6c11b3cef75ff98a` — **unchanged** | `sha256:a0863851775c24d26a254897d11b41c42aba36096edb9bc7804015ee0d037b8d` — **unchanged** |
| inventory `output_digest` | `sha256:d3b74162e4d60ab0982981c854ae7f2c335096ddbd99ce021f27f864850d25ff` — **unchanged** | `sha256:9e916d8a7d658cea6f783067ecd3729e41b4bee7838b4bca929092be252dbdb8` — **unchanged** |
| manifest `input_digest` | `sha256:c5b5e6866db4ef05f8faa17d011985afd2c505de268abc15949ef7bd5db250d3` (was `1785628c…`) | `sha256:325630281ce2cab89877ded1e99d811ac161b2bd7ba60e5572ff91f6685dc281` (was `f788f023…`) |
| manifest `output_digest` | `sha256:44cba5cc4f0b05169ce6e5920a329e07713a10851525fe197b165c182cd89cfb` (was `34b83d98…`) | `sha256:1d1e126cd160b5ef1386b21ee60f824fe1f382703c59de934142a65f2fdaf480` — **unchanged** |
| identities | run `px-e476a9c30ae540689998cfece0bf5bba`, inventory `px-74e1ca319add4985829b131054bba7f7`, manifest `px-d51f7c6c85eb4c11917d10b915ecf09b` | run `px-6f6aa954378c4b488f101625bac73872`, inventory `px-7b080269f0854040b60b291310de8a3f`, manifest `px-27d6d5c3538d4b5fad92cbfc08380848` |
| requests / runtime (instrumented) | 4 requests in `1.71 s` against a ceiling of 8 | 3 requests in `0.76 s` against a ceiling of 8 |
| opt-in pytest smoke | `1 passed` | `1 passed` |

**Request log** (rfc-editor.org): the bootstrap `GET /` (unscoped, 182314 bytes, 0.30 s), then,
all scoped to the origin, `/robots.txt` (135 bytes), `/sitemap.xml` (259 bytes, a sitemap index)
and `/sitemap-1.xml` (701403 bytes). No redirect and no truncation. The digests of the plain CLI
run and of the instrumented run are identical, for both targets.

**What the digests prove.** Every **inventory** digest is byte-identical to the pre-repair run on
`09b716a`, so the repair changed selection and nothing upstream of it. The rfc-editor.org manifest
digests both moved, which is correct: `input_digest` binds the declared budgets, and there are now
none; `output_digest` binds the selection, and it grew from 25 to 506. The example.com manifest
`output_digest` is **unchanged** while its `input_digest` moved — the sharpest available check
that the two digests mean what the contract says they mean, since a complete census of one page
has identical selection semantics under either budget, and only the declared inputs differ.

**The semantic consequence.** On an inventory of materially the same shape as before, the default
planner no longer stops at 25. It stopped at 25 only because 25 was the old default; it now covers
the population discovery was allowed to find.

**Two truths kept separate.** The same rfc-editor.org run reports `SITEMAP BUDGET_EXHAUSTED` with
500 admitted — discovery reached one of *its* bounds — while the selection over the resulting
inventory is complete with no budget declared. Discovery incompleteness lives in the inventory's
source outcomes; selection completeness lives in the manifest. The smoke test asserts both on
every run.

**Evidence ceiling.** This proves the tested boundary only: two public origins were established
safely, discovered within their bounds, reduced to valid inventories and planned as valid complete
censuses by the committed code. It does not prove arbitrary internet crawling, production scale,
complete site coverage, browser rendering, PXAPI-20 acquisition, scoring quality or customer
uplift. 500 of the 506 rfc-editor.org candidates are RFC documents outside the classifier's SME
vocabulary and are counted `UNCLASSIFIED`, which is a neutral statement about this classifier.
A public website can change between two runs, so the candidate count is recorded and deliberately
not asserted by any test.

## E. Scope: explicitly not built

Crawl4AI, Playwright or any browser, Selenium, `RenderedPagePort`, JavaScript execution, PXAPI-20
multi-page acquisition or evidence population (links are read only from the seed document the
bootstrap already retrieved), scoring or weights, customer projection, PDF, PostgreSQL, queues,
workers, leasing, CRM, buyer-intent inference, deployment or infrastructure changes, a
census-to-sampling threshold, production `STRATIFIED_SAMPLE`, an HTTP endpoint for discovery, any
Jira or Confluence edit, and any change to legacy PR `#5`. robots.txt is read for `Sitemap:` lines
only; no `User-agent`, `Allow`, `Disallow` or `Crawl-delay` directive is read, applied or claimed
(`test_robots_directives_other_than_sitemap_are_never_applied`).

## F. Decisions taken inside the authorised scope

Each is a choice the brief left open, recorded so that a reviewer can see it and reverse it.

1. **The bootstrap reads the origin root** of the submitted target; the origin of the response
   that finally arrives, after policy-validated redirects, is `target_origin`.
2. **Any response establishes the origin.** A `404` or `500` homepage answers the bootstrap
   question; what the page is becomes a neutral link-source state, never a missing inventory.
3. **Links come from the seed document only.** Reading more pages would be PXAPI-20 acquisition.
4. **`SAME_ORIGIN_PAGE_LINKS` yields same-origin links; sitemap entries outside the origin are
   recorded** and excluded `OFF_ORIGIN`, because a sitemap is the site's own declaration.
5. **`REFUSED_SITEMAP` is a source of its own** in the open source vocabulary, so a refusal stays
   visible beside a sitemap that was read.
6. **The inventory `input_digest` binds the transient label** where an observation carried one.
   The label never reaches the document but can change a classification, and a label-free record
   keeps the 19.A shape, so every registered digest still reproduces.
7. **The provider reports the seed**; the Domain never synthesises one.
8. **No selection budget is declared by default** (`fd3ad8a`). A caller may declare
   `max_selected_pages`, and a declared budget travels in the manifest planned under it;
   `max_candidates_considered` stays unused vocabulary. Until `fd3ad8a` the composition declared
   `max_selected_pages = 25` by default, which is finding `F-PXAPI19B-R4M-001`.
9. **`selection_complete` is about the selection only**, as its schema text says; discovery that
   hit a bound is recorded in the inventory's source outcomes, so `SAFETY_LIMIT_REACHED` and
   `RUNTIME_LIMIT_REACHED` have no trigger in 19.B.
10. **A raw backslash has no identity.** RFC 3986 and WHATWG read it differently and a browser is
    the second reader, so a form carrying one is refused rather than keyed under one reading.
11. **Budgets count distinct written forms**, so repetition never costs a page; the distinct link
    targets examined are bounded separately by `max_links_examined`.
12. **Canonicalisation declines every merge it cannot justify**: parameters keep their order, a
    trailing slash below the root is kept, IDN hosts are not converted to A-labels.
13. **Sitemaps are streamed through expat** with document types and entities refused by the parser
    and a depth cap of 8, instead of a byte-level guard.
14. **The link reader never calls `HTMLParser.close()`**, which is quadratic on unterminated markup
    on some CPython releases (measured on 3.13.3: 128 KB of `<a` in 20.8 s through `close()`,
    0.009 s without it; 3.14.6: 0.001 s either way).
15. **A watchdog enforces every fetch deadline** and every discovery fetch is capped by what
    remains of the run, because a per-receive timeout resets on every byte.
16. **Run failure codes are open tokens**; no `problem` code was registered and `manifest.json` is
    unchanged. **No HTTP endpoint** for discovery; the CLI is the smoke's entry point.

## G. Remaining truth

**VERIFIED by the author:** everything in sections A, B, C (except where marked) and D, each with
the command shown. That includes both R4M repairs: each finding was re-derived by running the
shipped code on `18a4aa3` and reading what it actually produced, each repair is proved by tests
that were observed to go red under counter-mutation, and each was re-measured across the real
boundary on `fd3ad8a`.

**AGENT_REPORTED:** the adversarial reviewers' and skeptics' findings and verdicts from the
`8f61abd` review round. Every finding that led to a change was re-derived by a RED-first test
written and run by the author; the dispositions are in section C. The two R4M findings repaired
in `fd3ad8a` are deliberately **not** carried as AGENT_REPORTED: both were re-measured here, on
this tree, before anything was changed, and those measurements are quoted in section C.

**MISSING:** an independent `R4M`, which this document does not declare and which remains
Orchestrator/Human authority; the Jira and Confluence closeout (read-only in this slice); the
census-to-sampling threshold (`C-PXAPI-005`), which keeps `STRATIFIED_SAMPLE` a vocabulary rather
than a capability — and which is precisely why no page ceiling was invented to replace the one
that was removed.

**Unresolved and carried:**
- The reviewability figure is 2.27 times the convention at `09b716a` and **2.43** at the repaired
  candidate `fd3ad8a` (section C). The Product Owner decision for this repair was not to split
  PR #16, so the figure is reported and not acted on.
- **The default census now scales with the site.** Removing the ceiling is what the finding
  required, and the consequence is that a run selects every eligible candidate discovery found —
  506 on rfc-editor.org where the old default took 25. Nothing in this slice fetches a selected
  page, so the cost today is bounded by discovery, not by selection; the figure is the one to
  watch when PXAPI-20 acquisition is authorised and each selection becomes work.
- A census bounded by an **explicitly declared** budget selects a lexicographic prefix, which is
  neutral but not representative; representative selection needs the missing threshold decision.
- An `HTTP/1.1 103 Early Hints` interim response is treated as final by the pre-existing fetcher;
  the resulting state is a neutral `PROVIDER_FAILURE`. Deferred.
- The pre-existing homepage parser (`html_observations.read_html`, PXK-67) still calls
  `HTMLParser.close()` and is therefore quadratic on unterminated markup on unpatched CPython
  releases. Out of this slice's scope; the discovery reader is not affected.
- The fetcher sends no `User-Agent` (pre-existing PXK-67 behaviour).
- `docs/context/*` was not updated: governance closeout is its own step, as it was for 19.A.

**Deferred:** a discovery HTTP endpoint; link discovery beyond the seed document (PXAPI-20); IDN
A-label normalisation.

**What this slice does not prove:** arbitrary internet crawling, production scale, complete site
coverage, browser rendering, PXAPI-20 multi-page acquisition or evidence population, scoring
quality, customer uplift, or a representative sample.
