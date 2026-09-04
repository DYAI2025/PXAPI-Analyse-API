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

## Determinism

Contract validation is offline and deterministic. The harness builds one `referencing`
registry from the schemas' own `$id`s, so no reference resolves over the network, and it runs
without a format checker: every constraint the contracts rely on is an assertion keyword
(`pattern`, `const`, `enum`, `required`, `if`/`then`), never a `format` annotation, which
validates nothing unless a checker is explicitly wired in.
