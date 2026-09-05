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
