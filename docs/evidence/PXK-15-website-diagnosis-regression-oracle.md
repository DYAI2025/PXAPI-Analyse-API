# PXK-15 - Website Diagnosis Regression Oracle

## Purpose

PXK-15 freezes the current `pixelkiez-website-diagnosis` behavior as migration evidence before any PXAPI extraction. This is a reference Oracle, not vendored application code.

## Oracle identity

- Source artifact: `pixelkiez-website-diagnosis (4).zip`
- Source artifact authority: `USER_STATED_LATEST_ARTIFACT`
- Source ZIP SHA-256: `acb122fdfc1d999b8bc3525ffc7f0b7fba177e07d5ae014a738f6848793c067b`
- Declared release: `3.4.0-customer-presentation-quality-gate`
- FIND05 patch identity: `FIND-05-LIVE-GOOGLE-TRUTH-GATE-2026-09-01`
- FIND05 pipeline run: `pxk-find05-live-google-20260901-package`
- Frozen production-tree digest: `fc94cd78aba9db50da1437593bab5cda58dbecf4e2ef4f004cb5473b9f7e47c3`
- Frozen production-tree file count reported by the local verifier: 260

The tree digest follows the Skill's `pipeline_ledger.digest_tree` semantics: sorted relative path, NUL separator and SHA-256 of each file body; `reports`, `dist`, caches/Git and `.pyc/.pyo` are excluded. PXAPI reimplements this algorithm in `oracle_probe.py` rather than importing Skill code.

## Source conflicts preserved, not laundered

The current source contains a known release-metadata contradiction. The top-level release artifact digest and FIND05 build ledger bind to `fc94cd78...`, while historical `reliability_gate` fields still name `dbe282325a1ebd1acaaa0b02c822037a235e573e548e39b0a36ae96ad60569f2` and run `pxk-customer-quality-v340-20260831`.

`dbe282...` was independently resolved by the prior verifier as the previous `(3).zip` production tree. It is retained in the manifest only as historical conflict evidence and must never be accepted as the current PXAPI Oracle. Because `reports/` is excluded from the tree digest, this stale report field is outside the production-tree byte identity.

The ChatGPT-installed Skill surface/index has also shown inconsistent visibility of FIND05 files. For PXK-15, the concrete owner-approved ZIP plus its SHA-256 and the recomputed `fc94...` production-tree digest are the source-artifact identity. No reinstall or upstream repair is performed here.

## Protected behavior

`oracle-manifest.json` machine-addresses the protected domains, including:

- deterministic 48-metric scoring and FULL/PARTIAL/NO_SCORE semantics;
- non-penalizing missing/not_assessed behavior;
- evidence-authority and truth-discipline boundaries;
- non-scoring measurement enrichment/gateway behavior;
- Strategic Relevance and customer-output leakage guards;
- complete internal reporting and constrained customer projection;
- V01/V12 exclusions, ordinal V03, contextual V05 and renderer safety;
- non-compensatory customer-presentation quality, privacy scope, sentence integrity and four-lever business impact;
- FIND05 query-plan approval, authority modes, complete SERP snapshot contract, deterministic customer matcher, score/customer authority gate, not_assessed fallback and context-bound ranking projection.

One explicit capability gap is retained: the FIND05 competitor/customer classification boundary has no dedicated negative case in the current tree.

## Deterministic regression gate

The mandatory A2 gate is stdlib-only:

```bash
python oracle/website-diagnosis/oracle_probe.py verify /path/to/oracle-tree
python oracle/website-diagnosis/oracle_probe.py mutation-proof /path/to/oracle-tree
```

The prior read-only verifier reported the exact `fc94...` tree GREEN with `PASS 13/13 FIND-05 truth-gate evals`, then demonstrated RED under two disposable single-boundary mutations, including `FAIL F05-N02 expected=BLOCKED actual=PASS`. Those results are evidence candidates until rerun from the committed probe against the owner-approved tree before merge.

The Skill's existing `scripts/run_release_gate_mutation_evals.py` is explicitly rejected for A2: it imports `validate_reports` from `validate_release_gate.py`, but that function is absent in the current validator. The script also targets cross-skill/Voice release behavior outside PXK-15.

## Scope exclusions

Explicitly excluded from this Oracle:

- Voice-agent and ElevenLabs runtime behavior;
- generic Skill packaging and live-call authorization;
- A3 Python application scaffolding;
- FastAPI, PostgreSQL, S3, authentication, deployment and CI construction.

No Website Diagnosis production file is copied into PXAPI, and no source Skill behavior is modified by this change.

## PXK-15 acceptance mapping

1. **Oracle identity/digest committed** - this evidence file plus `oracle-manifest.json` bind the owner-approved artifact and `fc94...` tree.
2. **Protected invariants addressable** - stable IDs and source/validator mappings live in the manifest; mandatory FIND05 checks are executable with stdlib only.
3. **Regression can turn RED** - `oracle_probe.py mutation-proof` intentionally weakens the automated-direct-Google authority boundary on a temporary copy and requires the current FIND05 harness to fail.
4. **Voice/packaging excluded** - explicit in manifest, README and this document.
5. **Source Skill not modified** - reference-don't-vendor design; the probe mutates only a temporary copy and rechecks the source digest.

## Remaining closeout work

Before merge, rerun `verify` and `mutation-proof` against the owner-approved `(4).zip` extraction and inspect the exact PR head. After an accepted A2 merge, reconcile the stale Confluence Oracle identity in a separately authorized closeout write. Do not open A3 until A2 closeout is accepted.
