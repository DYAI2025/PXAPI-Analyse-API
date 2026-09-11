# PXAPI contracts

JSON Schema is the canonical authority for every PXAPI contract. A contract is data: a schema
file, at least one valid example, and a registry entry that names it. There is no second,
hand-written definition of the same shape in Python.

## Layout

```text
contracts/v1/
├── manifest.json          the registry: the single inventory of v1 contracts
├── schemas/               one file per contract, plus shared definitions
└── examples/              at least one valid example per contract
```

Targeted invalid documents live with the tests, under
`tests/contracts/fixtures/invalid/<contract>/`, because they are proofs about the schema
rather than part of the published contract surface.

## The registry

`manifest.json` is the only place the contract inventory exists. The validation harness reads
it and derives everything else — which contracts exist, what each is called, which version it
is at, where its schema and examples live. The harness holds no list of contract names and no
contract count, so **registering a contract requires no change to any test.**

Each entry carries:

| Member | Meaning |
| --- | --- |
| `name` | the contract's stable name, lower kebab case |
| `id` | its schema `$id`, always `<id_namespace><name>:<version>` |
| `version` | the contract's own version — see below |
| `role` | `core` or `support`, from the registry's declared role vocabulary |
| `status` | `active` or `deprecated`, from the declared status vocabulary |
| `owner_slice` | the delivery slice that owns this contract's meaning |
| `schema` | path to the schema file, relative to the contract root |
| `examples` | one or more valid example documents |

`registry.version` describes the shape of `manifest.json` itself. It is **not** a version of
the contracts listed in it.

## Versioning

**Every contract is versioned in its own right.** The registry entry's `version`, the schema's
`$id`, and the `const` on the document's `schema_version` are three statements of one fact and
must agree; a test proves they do. There is deliberately no global contracts version acting as
the semantic authority for all contracts: `foo` may sit at `1.0.0` next to `bar` at `2.1.0`.

A new version of a contract is a new schema artifact with a new `$id`, never a widened
`const` on the existing one.

Registering a contract is **additive**: it never alters the meaning of a contract already
registered, and it never requires an existing consumer to change.

## Compatibility rules for consumers

* Treat a problem `code` you do not know as a generic problem of the given `title` and
  `detail`. Never reject a document because its code is unfamiliar.
* Do not depend on the order of `errors`; depend on `(pointer, keyword)`.
* Do not parse `detail`. It is human-readable text rendered from a fixed template, and the
  template may be reworded. Everything machine-readable is in `code` and `errors`.
* Every contract root object is closed. Sending an unrecognised property is an error, not a
  forward-compatible extension.

## The Analysis Run lifecycle and scan mode

**Global execution state is deliberately coarse.** `analysis-run-state` carries exactly six
states:

```text
CREATED -> QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED
```

Those five arrows are the whole approved edge set: 5 of the 36 ordered pairs are legal, 31 are
not, and every self-transition is among the 31. Terminal states — `SUCCEEDED`, `FAILED`,
`CANCELLED` — are the states with no outgoing edge, derived rather than declared. The schema
fixes the vocabulary; `pxapi.domain.run_state` is the authority on which transitions are legal,
and an unapproved one raises `ILLEGAL_RUN_TRANSITION`, registered in the manifest under the
existing open problem-code policy.

`entered_at` is always present. `finished_at` is present **iff** the state is terminal.
`failure` is present **iff** the state is `FAILED`, and it carries a `code` and nothing else —
no detail, no stage attribution. `CANCELLED` is the state plus the terminal timestamp: this
slice defines no cancellation reason, requester or retry metadata, and the closed root refuses
one.

**`SUCCEEDED` is an execution fact, not a release decision.** It does not mean customer
release, delivery, report readiness, completed scoring, or legal or security approval, and it
does not mean every stage succeeded. The contract carries no member that could say otherwise.

**Stage execution is a separate record.** `stage-execution-record` describes one stage's own
execution and is linked to the run by `run_id` alone — it is not embedded in the run state, and
neither document is derived from the other. Its `status` is a closed four-value vocabulary,
`RUNNING | SUCCEEDED | FAILED | CANCELLED`: there is no `PENDING` and no `QUEUED`, because a
record exists only once the stage has begun. The absence of a record means no record is
present, and carries no further meaning.

`stage_id` is an **open** stable token, not an enum: this slice fixes the token's lexical shape
and deliberately not the set of stages, so a stage a later slice introduces validates without a
schema change. Treat a `stage_id` you do not know as an unknown stage, never as an error.

A `FAILED` stage record and a `SUCCEEDED` run state for the same run are both valid at the same
time. That is a statement about the contracts, not a claim that a stage failure is harmless:
**whether a given stage or provider failure is fatal to a run is orchestration policy, which no
contract here decides.** A later slice must decide it explicitly rather than inherit it from a
schema, which is why neither document carries an `optional`, `fatal` or `severity` member.

**`scan_mode` records an authorised operating mode and nothing more.** `analysis-run-request`
requires exactly one of `PUBLIC_NON_INVASIVE` or `OWNER_VERIFIED_CONTROLLED`; the vocabulary is
closed and case-sensitive and there is no default, so a run whose mode was never stated is not
a valid request. Recording the mode is **not** performing owner verification, access control,
URL safety, SSRF or egress enforcement, robots handling or any scanner execution policy — those
belong to the slices that own them, and a valid request document proves none of them.

**A closed vocabulary is pinned as a whole set, not one token at a time.** An invalid fixture
proves that a particular token is rejected; it says nothing about the set, so a value silently
added to a closed `enum` would leave every fixture green. `tests/test_closed_vocabularies.py`
states each closed vocabulary in the registry once and in full — deriving it from the Domain
where the Domain owns the fact — and fails when a closed vocabulary appears anywhere in the
registry that nobody has pinned. Widening or narrowing `scan_mode`, the run state, the stage
status or either terminal condition is therefore a reviewed change, never an accident.

## Assessment, measurement and website evidence

**A technical failure is never a finding about the website.** That is the rule the assessment
vocabulary exists to make structural rather than merely intended.

`assessment.v1.json` is a **shared definition, not a registered contract**. Every registered
contract pins its own `schema_version` at its root, so a block embedded in more than one carrier
would drag a nested version into every document that carries it. The block is still validatable
on its own through the harness, and its members reference this file's own `$defs` by absolute
URI: a local `#/$defs/...` would be resolved against whichever schema embeds the block, and
resolve nowhere.

An assessment says exactly one of two things, and carrying both is refused:

```text
performed      collection_mode  MEASURED | OBSERVED
               result_state     KNOWN | UNKNOWN | CONFLICT | NOT_APPLICABLE

never happened not_assessed_reason  PROVIDER_FAILURE | RUNTIME_ERROR | PERMISSION_DENIED
                                    | TIMEOUT | UNSUPPORTED | NOT_REQUESTED
```

`KNOWN` is the only result state that carries a value about the subject. `UNKNOWN` means the
assessment ran and established nothing; `CONFLICT` means observations disagree and the
disagreement is unresolved; `NOT_APPLICABLE` means the measurement does not apply to this
subject. Those three are outcomes **about the assessment**, never findings about the site.

Every `not_assessed_reason` names the analysis process — a provider, our own runtime, a
permission, a time budget, an unsupported subject, or nobody having asked. That is why this
vocabulary is closed while an identifier such as `metric_id`, `collector` or `scenario` stays
open: an open reason token could carry one that describes the website instead. A reason is not a
severity and not a retry policy; whether a reason is worth retrying is orchestration, which no
contract here decides.

### What each carrier may then state

| assessment | measurement `result` | evidence `polarity` |
| --- | --- | --- |
| performed, `KNOWN` | required | permitted, `POSITIVE` or `NEGATIVE` |
| performed, `UNKNOWN` / `CONFLICT` / `NOT_APPLICABLE` | refused | refused |
| never happened, any reason | refused | refused |

**Polarity is permitted, not required.** Evidence that is `KNOWN` and carries no judgement omits
the member. There is deliberately **no `NEUTRAL` token**: a vocabulary entry for "known and
neither good nor bad" invites a reader to treat it as a verdict, and nobody has defined what
that verdict would mean. Outside `KNOWN` the member is refused outright rather than given a
neutral value to hold, which is what makes a provider failure structurally incapable of
appearing as a negative statement about a customer's site.

`KNOWN` website evidence must name **at least one** `measurement_refs` entry, because derived
evidence with nothing measured behind it is an assertion rather than evidence. An empty list
elsewhere means nothing was derived — never that the website lacks something.

### The measured value is closed, not open

`measurement-record.result` is a discriminated shape: `value_type` names one of `BOOLEAN`,
`INTEGER`, `TEXT` or `URL`, and exactly the matching typed member is carried. There is no
`value: any`. A value shape a later slice needs is a **new version of the contract**, chosen
deliberately, rather than a widening that changes what every existing consumer must read.

`text_value` inherits the shared single-line bound. A longer observed text is not representable
in `1.0.0`; widening it is a new version, never a widened bound on the existing one.

### The raw-data boundary

Raw bodies, HTML captures and provider payloads **never live inline** in a normalised record.
The closed roots refuse the member, and `raw_artifact_ref` is an **opaque token and nothing
more** — no digest, no location, no media type, no size, no retention rule, no redaction
metadata. Those belong to the artifact contract a later slice owns and are deliberately not
anticipated here. `tests/evidence/test_assessment_semantics.py` enforces the inline ban on the
two contracts this slice owns, and not registry-wide: what a later, separately authorised
contract may hold is not this slice's decision.

## Producing documents from a real observation

PXK-67 is the first slice that writes these contracts from live input, and two of its decisions
are worth stating here because they are contract decisions rather than collector conveniences.

**An open vocabulary meant no contract had to change.** `metric_id`, `collector`, `scenario`
and `stage_id` all reference `common#/$defs/code`, which fixes a token's lexical shape and
never the set. Every metric the walking skeleton introduces — `HTTP_STATUS`, `FINAL_URL`,
`CONTENT_TYPE`, `TRANSPORT_IS_HTTPS`, `REDIRECT_COUNT`, and the presence/value pairs for the
page title, the meta description and the canonical link — validates against the contracts
exactly as they were merged. Registering three further `problem_codes` was likewise additive.

**A bound is read from the contract, never copied into a collector.** `text_value` inherits the
shared single-line bound, and a producer needs that number to decide whether an observed text
is representable at all. It reads it out of the schema at runtime — the same technique the
`problem` producer already uses for `errors.maxItems` — so widening the bound in a later
contract version cannot leave a stale constant behind that silently keeps discarding values the
contract would now accept.

The rule that follows is the one the vocabulary was built for. An observed text that will not
fit is **not** shortened and presented as the original: the element's *presence* is still a
`KNOWN` boolean, and the *value* becomes a performed assessment with `result_state` `UNKNOWN`
and no `result` at all. The same holds when a response body reached the reader's byte bound —
an element that was not seen in a truncated document is `UNKNOWN`, never `false`, because
otherwise a producer's own limit would appear as a defect on the analysed site.

Three outcomes stay carefully distinct, and each has a different token:

```text
absent          the site declares no title            KNOWN, boolean false
not applicable  there is no value to read             NOT_APPLICABLE, no result
unknown         the assessment established nothing    UNKNOWN, no result
```

None of them is a `not_assessed_reason`, and no `not_assessed_reason` is any of them: a
provider failure, a timeout, a refused permission and a runtime error say nothing about the
subject, and a document carrying one is refused a value and a polarity outright.

## Site inventory and sampling manifest

PXAPI-19.A adds the two contracts that make the analysed page population itself reproducible,
and registers **no producer for either**. `site-inventory.v1` is the provider-neutral population
of publicly discovered targets for one site; `sampling-manifest.v1` records which of that
population an Analysis Run set out to analyse, and why. Both are technical artifacts: neither
carries a score, a severity, a polarity or a finding, and the closed roots refuse an added one.

`acquisition.v1.json` is a **third shared-definitions file**, not an extension of
`common.v1.json`. `common`'s `$id` pins it at `1.0.0` and every registered contract references
that exact URI, so adding a definition there would either leave the version lying about the
file's content or break every existing reference. It holds the lexical URL and digest shapes of
the acquisition slice: `public_url`, `public_origin`, `url_key` and `digest`.

`public_url` differs from `common#/$defs/url` in exactly one respect. Its authority segment
excludes `@`, so a credential-bearing URL such as `https://user:secret@example.com/` **cannot
become persisted canonical contract data**. Every URL-valued member of both contracts resolves
to this shape, to `public_origin` or to `url_key`, both of which are built on it; a test asserts
that neither contract references the userinfo-permitting shape at all, so a member somebody
forgets cannot become the way userinfo is persisted. `digest` carries its algorithm in the value
— `sha256:` plus 64 lower-case hex characters — so a document is never read against an assumption
about how its digest was produced, and a later algorithm is a new contract version rather than a
longer string.

`public_origin` is `public_url` **narrowed to an origin**: scheme, authority (legal port form
included) and at most the normalised root slash. A path beyond the root, a query and a fragment
are each refused. `site-inventory.target_origin` uses it, because that member is the canonical
site authority and the seed identity — a member every consumer reads as "the site" must not be
able to hold one page of the site. It is referenced by the inventory alone today and still lives
in the shared file, because it narrows the very authority segment `public_url` declares beside
it, and one authority shape stated twice is how the two drift apart. It stays **lexical**: DNS
resolution, reachability, redirect policy, egress rules, loopback and private ranges and robots
handling remain PXAPI-19.B and runtime concerns, and a valid value proves none of them.

### The digest topology

Each contract carries **exactly two** digests. There is deliberately no third `content_digest`:
a third member would create a second, unowned notion of a document's identity.

| Digest | Computed over | Never participates |
| --- | --- | --- |
| `site-inventory.input_digest` | the admitted discovery observations, which this document does not carry | envelope ids, `generated_at`, both digest members |
| `site-inventory.output_digest` | target origin, discovery method and version, classifier and version, source outcomes, normalised candidates | the same |
| `sampling-manifest.input_digest` | `inventory_ref`, `inventory_output_digest`, `policy_id`, `policy_version`, declared `budgets` | the same |
| `sampling-manifest.output_digest` | `mode`, `selection_complete`, `incompleteness` when present, the selections in rank order, the exclusion summary | the same |

The canonical form is deterministic UTF-8 JSON with sorted keys, no insignificant whitespace and
**no floating-point member anywhere** — a digest over a float is not portable between producers,
so no member of either contract admits one. Re-emitting the same semantics under a new id at a
new instant leaves both digests unchanged, which is what makes them comparable across runs.

**Semantic ordering must not make an order-independent input order-dependent.** The two contracts
therefore differ deliberately: the inventory's candidates, their `observed_forms` and their
`provenance`, and the `sources` list are **sets** the contract renders as arrays, so the
projection sorts them and the digest cannot depend on the sequence a producer happened to visit
sources in. A manifest's selection order **is** semantic, and it is carried by an explicit
`selection_rank` rather than by the array position — so re-serialising a manifest in another
array order cannot change what it means, while permuting the ranks does.

`tests/acquisition/digests.py` is the reference implementation of these rules. It is test code
because PXAPI-19.A ships no producer, and its member classification is derived against the
schemas: a member added later without a decision about whether it participates in a digest turns
the suite red rather than silently digesting or silently escaping.

### Semantic keys, and why the digest fails closed

The canonical ordering sorts each order-independent collection by a **semantic key** — a source's
`source_id`, a candidate's `url_key`, a selection's `selection_rank`, an exclusion's `reason`.
Five relationships follow from that, and **JSON Schema states none of them**:

| Rule | What it keeps unambiguous |
| --- | --- |
| `source_id` unique per inventory | a candidate's `provenance` resolves to one outcome |
| candidate `url_key` unique | observations that share an identity aggregate onto one candidate |
| selected `url_key` unique per manifest | the selection set is a set; the accounting does not double-count |
| `selection_rank` unique **and dense** (`1..n`) | the order authority names one real position per selection |
| exclusion `reason` unique per manifest | a reader never adds two partial counts of one reason |

`uniqueItems` does not cover these: it compares **whole items**, so two sources with one
`source_id` and different outcomes, or two selections at one rank with different identities, pass
it. This is stated rather than glossed over — **no claim is made anywhere that JSON Schema
enforces these relationships.**

Ambiguity is not cosmetic. `sorted` is stable, so two equal keys keep whatever order the producer
emitted, and the "canonical" digest of an ambiguous document silently depends on serialisation
order. `tests/acquisition/semantics.py` is the contract-semantic layer that refuses such a
document, and the digest projections call it **before** ordering anything, so no digest is ever
produced for a document that has no canonical order. Every counterexample under
`tests/acquisition/fixtures/semantic-invalid/` is asserted **schema-valid first** and semantically
invalid second — that pairing is the evidence — and the unguarded ordering is reconstructed in the
tests and shown producing two different digests for two serialisations of one document.

PXAPI-19.A authorises no production validator, so this layer is test code and no `src/pxapi`
module is added for it. **Equivalent producer-side enforcement is mandatory in PXAPI-19.B:**
nothing in this slice prevents a producer from emitting a document no consumer can order.

### One authority for discovery source state

`sources[]` is the **single** authority on what became of each attempted discovery source. There
is deliberately no root-level `sitemap_state` or `robots_state` beside it, because two accounts
of one fact can disagree and a reader would then have to choose. Each entry names the source as
an **open** token — a source a later slice introduces validates without a schema change, and the
same token is what a candidate's `provenance` names — plus a **closed** outcome:

```text
USED                    read, and its entries enumerated
EMPTY                   read, well formed, and declared nothing
ABSENT                  not served where it would be declared
MALFORMED               served, but not parseable as the source kind it claims
NO_SITEMAP_DECLARATION  an applicable source was present and declared no sitemap
BUDGET_EXHAUSTED        one of our own declared bounds stopped the read
TARGET_POLICY_REFUSED   our own target policy refused the fetch
PROVIDER_FAILURE        a component outside our runtime failed
RUNTIME_ERROR           our own runtime failed
TIMEOUT                 a time budget elapsed
```

Every one of the ten names the **analysis process**, and none is a website-quality polarity. The
vocabulary is closed for two reasons: an open token could arrive carrying a reason that describes
the site, and each token carries its own rule about the admitted count. `candidate_count` is how
many candidates *this inventory admitted from that source* — never a count of what the source or
the website contains — and only `USED`, `BUDGET_EXHAUSTED` and `TIMEOUT` may report a non-zero
one. Every other outcome is pinned to zero, so **an absent, malformed, undeclared, refused or
failed source is structurally incapable of reporting that it contributed pages.**

`PROVIDER_FAILURE` and `RUNTIME_ERROR` are kept apart exactly as
`assessment#/$defs/not_assessed_reason` keeps them apart, and `PROVIDER_FAILURE` deliberately
stays a *source outcome*: attributing a failure to a component is the opposite of handing that
component a decision.

### Bootstrap truth

An inventory exists **only after** a canonical public target origin has been established, so it
always contains at least the canonical target seed, whose `url_key` is `target_origin`. There is
deliberately no representable successful zero-candidate inventory: such a document would read as
"this site has no pages" when what actually happened is that discovery never started. A bootstrap
that cannot establish the origin produces **no inventory and no manifest** — a neutral technical
run failure whose wiring belongs to PXAPI-19.B.

A discovery that found nothing beyond the homepage is therefore a **one-candidate** inventory
with neutral source outcomes, which is what `site-inventory.homepage-only.example.json` is; there
is no `empty-discovery` example, and a test asserts there never is. JSON Schema cannot compare two
members of one document, so the seed-identity rule is enforced over every registered example
rather than by the schema; the schema enforces the part it can, that the list is never empty.
`sampling-manifest.v1` applies the same rule to its own selections for the same reason.

### Duplicate, rejected and transient URL truth

Accepted observations that canonicalise to the same identity are **one candidate with aggregated
provenance**, never several. `observed_forms` holds the distinct accepted forms that were seen and
`provenance` the `source_id` values that contributed them, both as unordered sets. Duplication is
**not** a website defect, not a score signal and not automatically an exclusion, and there is no
`DUPLICATE_URL_KEY` token anywhere in either contract — a test asserts that too, so introducing
one is a reviewed change rather than an accident.

An arbitrary rejected URL string is deliberately **not persisted** merely so that a digest can be
recomputed: the manifest's `exclusions` is a bounded per-reason count summary and the closed roots
refuse a URL list. Raw anchor labels remain transient PXAPI-19.B input and are not part of the
19.A canonical contract; the closed candidate object refuses one.

A candidate's `page_type` is **optional**, and its absence means the classifier assigned no type.
It never means the page is irrelevant, wrong or excluded — and the absence of a member is
structurally incapable of carrying a judgement. The taxonomy itself stays an open token: fixing a
stratum or page-type set is versioned classification work, not a set invented by this slice.

A manifest's `stratum` is deliberately the **opposite**: required on every selection. The
asymmetry is not an oversight. A candidate is a page discovery merely found, and whether the
classifier reached it is a fact about the classifier; a **selected** page is one this analysis
committed to, and PXAPI-19 AC4 requires every one of them to carry Page-Type/Stratum, a selection
reason and a stable reference. An absent stratum on a selection would also be read two ways —
"counted under no stratum" by one consumer, "nothing worth counting" by the next — so a selection
the classification could not place is recorded under the neutral token **`UNCLASSIFIED`** instead.
The taxonomy stays open around it: the member still resolves to `common#/$defs/code`, declares no
`enum`, and no member of the contract keys on the token, so nothing in the schema can treat an
unclassified page differently from any other. It is not a quality, not an exclusion, not a lower
rank and not a weight, and a test asserts the token appears exactly once in the schema file — in
the description that names it, and never in an `enum`, a `const` or a conditional.

### Sampling semantics

`mode` is closed at `CENSUS | STRATIFIED_SAMPLE`, and each token names an **intent, not an
achievement**. `CENSUS` means the policy set out to select every eligible candidate exhaustively;
whether it got there is `selection_complete`'s statement and never the mode's:

```text
CENSUS + selection_complete: true    the census completed — the only combination that says so
CENSUS + selection_complete: false   valid and authorised: the census was bounded or interrupted,
                                     and it carries the technical limitation that stopped it
```

Reading `CENSUS` alone as "every eligible page was selected" is wrong in exactly the case the
pair exists to record, and a test refuses the absolute phrasing returning to the description.
**The census-to-sampling threshold is `MISSING`** (contradiction ledger `C-PXAPI-005`) and is not
invented here: the only numeric constant either contract declares is the zero that pins a
non-admitting source's count, and a test asserts it. `STRATIFIED_SAMPLE` existing in the
vocabulary lets a manifest say which method was used; it is **not** a claim that a
benchmark-authorised sample can currently be produced.

Selection is Pixelkiez methodology. `policy_id` and `policy_version` are both required, so a
selection is always attributable to a versioned method, and no member name or selection token
names a crawl provider — a test scans for that. `selection_complete` is **mandatory and neutral
in both values**: `false` means the selection was bounded or stopped early and is a statement
about this analysis; it never means the site is small, thin or incompletely built, and nothing
downstream may treat it as a penalty.

That neutrality is **structural rather than promised**. `false` is admissible only alongside
`incompleteness`, the smallest root object that can carry a technical cause — one closed member,
and nothing that could describe, measure or rank the site:

```text
SELECTION_BUDGET_EXHAUSTED  one of our own declared selection budgets was reached
SAFETY_LIMIT_REACHED        one of our own safety bounds stopped the selection
RUNTIME_LIMIT_REACHED       our own runtime stopped it — a time budget, or a failure
```

Two root conditionals bind it: `false` **requires** the member, `true` **refuses** it — a
completed selection that also claimed a cause for not completing would be two contradictory
statements in one document — and `SELECTION_BUDGET_EXHAUSTED` additionally requires `budgets`, so
a bound named as the cause can be read rather than merely asserted. `budgets` is therefore
`Conditional`, not `Optional`. Coupling `selection_complete` to the existing `exclusions` summary
instead would have been the smaller change, and it is not available: the repository's schema
meta-rule (`SchemaWalk` in `tests/contracts/support.py`) forbids a conditional that reaches into
array items, so a root member cannot be coupled to an item. That constraint, not a preference,
is why a root-level object exists.

A manifest binds `inventory_output_digest` to the exact inventory output it selected against, so
it can never be read as a selection over a population it did not see.

### What these two contracts do not prove

A valid inventory or manifest proves a document shape and nothing else — **including that it does
not prove the semantic-key rules above.** Those are checked by a separate layer, and a producer
that never runs it can emit a schema-valid document no consumer can order. It does not prove that
site discovery runs, that same-origin traversal, sitemap or robots handling is implemented, that
a producer canonicalises or deduplicates, that a sampling planner exists, that the sampling
threshold is known, that any page was fetched, or that any URL was reachable, safe or permitted.
A valid `target_origin` proves a lexical shape and no DNS, SSRF, egress or reachability decision.
Acquiring a selected page is PXAPI-20's decision and `page-acquisition-record.v1` is not part of
this slice.

## The Problem contract and its producer rule

`problem` is transport-neutral: no HTTP status, no type URI, no other transport binding. The
adapter that owns a transport maps the document onto it.

A producer of `problem` documents must follow these rules, which the tests enforce against the
reference producer in `tests/contracts/support.py`:

1. **Fixed templates only.** `title` is a fixed string per code. `detail` is rendered from a
   template plus values the producer resolved from its own registry. A validator's message,
   an exception's text, a traceback, a filesystem path, a token or a secret is never copied
   into any member.
2. **Structure, not prose, for violations.** Each entry of `errors` is a JSON pointer and the
   violated schema keyword. There is no free-text member, because a free-text member is the
   channel through which validator output — and anything it quotes — reaches a client.
3. **Resolve names before echoing them.** A contract name may appear in `detail` only after
   the registry resolved it, and the string echoed is the registry's own value. An
   unregistered name is reported as `CONTRACT_NOT_FOUND` and never appears in the document.
4. **Bounded output.** `errors` carries at most `maxItems` entries. A producer that finds more
   truncates to the bound and states the untruncated count in `detail`.
5. **Single-line text.** `title` and `detail` reject every C0 and C1 control character, DEL,
   and the Unicode LINE SEPARATOR and PARAGRAPH SEPARATOR — not merely CR and LF.
6. **An unsupported version and an absent one are different problems.** A `schema_version`
   that is present but not the one the contract pins fails `const` and is reported as
   `SCHEMA_VERSION_UNSUPPORTED`; an omitted one fails `required` and is reported as
   `CONTRACT_VALIDATION_FAILED`. The two never collapse into one code.

## Determinism

Contract validation is offline and deterministic. The harness builds one `referencing`
registry from the schemas' own `$id`s, so no reference resolves over the network, and it runs
without a format checker: every constraint the contracts rely on is an assertion keyword
(`pattern`, `const`, `enum`, `required`, `if`/`then`), never a `format` annotation, which
validates nothing unless a checker is explicitly wired in.
