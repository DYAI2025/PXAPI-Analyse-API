# Website Diagnosis Regression Oracle

This directory is PXK-15 evidence, not PXAPI application code.

The current Oracle is the owner-approved `pixelkiez-website-diagnosis (4).zip` production tree with digest `fc94cd78aba9db50da1437593bab5cda58dbecf4e2ef4f004cb5473b9f7e47c3`.

## Boundary

- Do not vendor the Website Diagnosis source tree into PXAPI.
- Do not import anything under `oracle/` from future `src/pxapi` application code.
- Do not modify the source Skill while testing this Oracle.
- Voice/ElevenLabs runtime behavior, live calls, generic Skill packaging and A3 scaffolding are excluded from PXK-15.
- The historical `dbe282...` digest is conflict evidence only and is explicitly rejected as a live Oracle.

## Mandatory stdlib-only gate

Extract the owner-approved ZIP outside this repository and point the probe to its root:

```bash
python oracle/website-diagnosis/oracle_probe.py digest /path/to/pixelkiez-website-diagnosis
python oracle/website-diagnosis/oracle_probe.py verify /path/to/pixelkiez-website-diagnosis
python oracle/website-diagnosis/oracle_probe.py mutation-proof /path/to/pixelkiez-website-diagnosis
```

`verify` checks the exact production-tree digest, required FIND05 files/tokens and the hermetic FIND05 truth-gate regression suite. `mutation-proof` copies the Oracle to a temporary directory, intentionally weakens the direct-Google authority boundary, and requires the FIND05 suite to turn RED. The original tree is re-digested afterwards.

Extended score/truth/PDF suites are optional evidence only when their existing third-party/runtime dependencies are already available. PXK-15 does not install them and must report unavailable suites as `CAPABILITY_MISSING` or `NOT_RUN_DEPENDENCY_UNAVAILABLE`, never PASS.

Known upstream defect: `scripts/run_release_gate_mutation_evals.py` is not used by A2 because it imports `validate_reports`, which is absent from the current `validate_release_gate.py`, and its cross-skill/Voice focus is outside this Oracle.
