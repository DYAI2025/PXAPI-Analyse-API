#!/usr/bin/env python3
"""PXK-15 stdlib-only probe for the frozen Website Diagnosis regression oracle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "oracle-manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def digest_tree(root: Path, manifest: dict) -> str:
    spec = manifest["digest_algorithm"]
    excluded_dirs = set(spec["exclude_dirs"])
    excluded_suffixes = set(spec["exclude_suffixes"])
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if set(rel.parts) & excluded_dirs or path.suffix in excluded_suffixes:
            continue
        h.update(str(rel).replace(os.sep, "/").encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def require_current_files(root: Path, manifest: dict) -> list[str]:
    return [p for p in manifest["required_current_files"] if not (root / p).is_file()]


def token_checks(root: Path) -> list[str]:
    checks = {
        "references/live-google-serp-truth-gate.md": [
            "provider_api", "human_verified_direct_google", "automated_direct_google", "not_assessed"
        ],
        "assets/capability-registry.json": [
            "requires_FIND-05-LIVE-SERP-TRUTH_PASS"
        ],
        "scripts/serp_truth.py": [
            "provider_api", "human_verified_direct_google", "search_sample", "automated_direct_google",
            "FIND-05-LIVE-SERP-TRUTH", "not_assessed"
        ],
    }
    errors = []
    for rel, tokens in checks.items():
        text = (root / rel).read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                errors.append(f"missing token {token!r} in {rel}")
    return errors


def run_find05(root: Path, manifest: dict) -> subprocess.CompletedProcess[str]:
    script = root / "scripts" / "run_serp_truth_gate_evals.py"
    return subprocess.run(
        [sys.executable, str(script), str(root)],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )


def verify(root: Path, manifest: dict, run_eval: bool = True) -> int:
    identity = manifest["oracle_identity"]
    expected = identity["oracle_artifact_digest"]
    stale = identity["historical_conflicting_digest"]
    before = digest_tree(root, manifest)
    if before == stale:
        return fail(f"stale historical oracle supplied: {stale}")
    if before != expected:
        return fail(f"oracle digest mismatch: expected {expected}, got {before}")
    missing = require_current_files(root, manifest)
    if missing:
        return fail("required current files missing: " + ", ".join(missing))
    token_errors = token_checks(root)
    if token_errors:
        return fail("; ".join(token_errors))
    if run_eval:
        result = run_find05(root, manifest)
        combined = result.stdout + result.stderr
        expected_summary = manifest["mandatory_probe"]["find05_expected_summary"]
        if result.returncode != 0 or expected_summary not in combined:
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            return fail(f"FIND05 mandatory regression did not match expected summary {expected_summary!r}")
    after = digest_tree(root, manifest)
    if after != before:
        return fail(f"source oracle changed during verification: {before} -> {after}")
    print(f"PASS: PXK-15 oracle verified {after}")
    return 0


def mutation_proof(root: Path, manifest: dict) -> int:
    if verify(root, manifest, run_eval=True) != 0:
        return 1
    source_digest = digest_tree(root, manifest)
    with tempfile.TemporaryDirectory(prefix="pxk15-oracle-") as td:
        copy_root = Path(td) / "skill"
        shutil.copytree(root, copy_root)
        target = copy_root / "scripts" / "serp_truth.py"
        text = target.read_text(encoding="utf-8")
        mutations = [
            (
                'ALLOWED_COLLECTION_MODES = {"provider_api", "human_verified_direct_google"}',
                'ALLOWED_COLLECTION_MODES = {"provider_api", "human_verified_direct_google", "automated_direct_google"}',
            ),
            (
                'BLOCKED_COLLECTION_MODES = {"search_sample", "automated_direct_google"}',
                'BLOCKED_COLLECTION_MODES = {"search_sample"}',
            ),
            (
                'if collection.get("automated_direct_google") is not False:',
                'if False:',
            ),
        ]
        for old, new in mutations:
            if old not in text:
                return fail(f"mutation anchor not found: {old}")
            text = text.replace(old, new, 1)
        target.write_text(text, encoding="utf-8")
        result = run_find05(copy_root, manifest)
        combined = result.stdout + result.stderr
        expected_failure = manifest["mandatory_probe"]["mutation_expected_failure"]
        if result.returncode == 0:
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            return fail("mutation proof stayed green")
        if expected_failure not in combined:
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            return fail(f"mutation failed for an unexpected reason; missing {expected_failure!r}")
    final_digest = digest_tree(root, manifest)
    if final_digest != source_digest:
        return fail(f"source oracle changed during mutation proof: {source_digest} -> {final_digest}")
    print(f"PASS: mutation proof turned RED as expected: {expected_failure}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("digest", "verify", "mutation-proof"):
        p = sub.add_parser(name)
        p.add_argument("skill_dir")
    args = parser.parse_args()
    root = Path(args.skill_dir).resolve()
    manifest = load_manifest()
    if not root.is_dir():
        return fail(f"oracle skill dir not found: {root}")
    if args.cmd == "digest":
        print(digest_tree(root, manifest))
        return 0
    if args.cmd == "verify":
        return verify(root, manifest, run_eval=True)
    return mutation_proof(root, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
