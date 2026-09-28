"""Offline checks of the PXAPI-20.B real-boundary proof harness.

The harness is a standard-library script run by the control interpreter, not part of the
product package, so it is imported here by file path. Nothing in this module touches the
network or ``uv``. The only interpreter other than the one running the tests is the same
executable started again in isolated mode, to run the harness's contract verifier for real.

Every positive fixture is what the shipped runtime emits over the frozen discovery report and a
fake fetch port, published exactly as the command line publishes it — so a green case is
contract-valid by construction and is asserted to be. Every negative case tampers with that
bundle and passes only when the proof rejects it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from pxapi.adapters.inbound import acquire_cli
from pxapi.domain import acquisition_digests
from pxapi.domain.page_acquisition import acquisition_violations
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure
from tests.application.test_acquire_selected_pages import (
    ORIGIN,
    PAGE_A,
    PAGE_B,
    REQUEST,
    SELECTED,
    FakeFetcher,
    build,
    response,
)
from tests.contracts.support import CONTRACTS, CONTRACTS_DIR

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tools" / "pxapi20b_real_boundary_proof.py"

#: The accepted Agent-team control interpreter and the uv its readiness evidence located.
CONTROL = "/Users/benjaminpoersch/.agt-runner/venv/bin/python"
LIVE_UV = Path("/Users/benjaminpoersch/.local/bin/uv")
SCRATCH_HOME = "/private/tmp/agent-proof-sandbox/home"

SHA = "0123456789abcdef0123456789abcdef01234567"
RUN = REQUEST["run_id"]
#: The three pages a budget of 3 selects from the frozen report, in rank order.
PAGES = tuple(SELECTED[:3])
TRACKED_ORIGIN = "tracked src/pxapi of the checkout"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pxapi20b_real_boundary_proof", HARNESS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


proof = _load()


def _forbidden(*_args: object) -> str:
    pytest.fail("uv discovery must not consult the (possibly scratch) home directory")


# --- fixtures: real runtime output, published as the command line publishes it -----------------


def _envelope(budget: int = 3, fetcher: FakeFetcher | None = None) -> dict[str, Any]:
    """One real multi-page envelope: the shipped runtime over the frozen report and a fake port."""
    return build(fetcher or FakeFetcher(), budget).run(dict(REQUEST))


def _mixed() -> dict[str, Any]:
    """A neutral mixed run: 200, 404 and a timeout, contained per page."""
    fetcher = FakeFetcher(
        {
            PAGE_A: response(PAGE_A, status=404),
            PAGE_B: PageFetchFailure(FetchFailureKind.TIMEOUT),
        }
    )
    return _envelope(fetcher=fetcher)


def _bundle(envelope: dict[str, Any]) -> dict[str, Any]:
    """``file name -> document`` exactly as the command line publishes it, receipt included."""
    return acquire_cli.expected_bundle(envelope)


def _rendered(
    envelope: dict[str, Any], bundle: dict[str, Any] | None = None
) -> tuple[dict[str, bytes], str]:
    bundle = _bundle(envelope) if bundle is None else bundle
    files = {
        name: (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        for name, value in bundle.items()
    }
    return files, json.dumps(envelope, indent=2)


def _check(
    envelope: dict[str, Any], bundle: dict[str, Any] | None = None, budget: int = 3
) -> tuple[list[str], dict[str, Any]]:
    files, stdout = _rendered(envelope, bundle)
    return proof.check_bundle(files, stdout, budget)


# --- uv discovery -------------------------------------------------------------------------------


def test_uv_on_path_is_taken_first() -> None:
    asked: list[str] = []

    def which(name: str) -> str | None:
        asked.append(name)
        return "/opt/tools/uv"

    assert proof.find_uv(which, CONTROL, lambda _path: True) == Path("/opt/tools/uv")
    assert asked == ["uv"]


def test_live_uv_is_derived_from_the_control_interpreter_not_from_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", SCRATCH_HOME)
    monkeypatch.setattr(Path, "home", _forbidden)
    monkeypatch.setattr(os.path, "expanduser", _forbidden)

    assert proof.runner_home(Path(CONTROL)) == Path("/Users/benjaminpoersch")
    candidates = proof.uv_candidates(CONTROL, resolve=lambda path: path)
    assert candidates == [Path("/Users/benjaminpoersch/.agt-runner/venv/bin/uv"), LIVE_UV]
    assert not any(str(candidate).startswith(SCRATCH_HOME) for candidate in candidates)

    found = proof.find_uv(lambda _name: None, CONTROL, lambda path: path == LIVE_UV)
    assert found == LIVE_UV


def test_live_uv_is_derived_from_the_resolved_interpreter_too() -> None:
    linked = "/usr/local/bin/python3"
    candidates = proof.uv_candidates(linked, resolve=lambda _path: CONTROL)
    assert candidates == [
        Path("/usr/local/bin/uv"),
        Path("/Users/benjaminpoersch/.agt-runner/venv/bin/uv"),
        LIVE_UV,
    ]


@pytest.mark.parametrize(
    "interpreter",
    [
        "/usr/bin/python3",
        "/opt/homebrew/bin/python3.11",
        "venv/.agt-runner/bin/python",
        "/Users/someone/agt-runner/venv/bin/python",
    ],
)
def test_no_home_is_derived_outside_a_runner_directory(interpreter: str) -> None:
    assert proof.runner_home(Path(interpreter)) is None
    candidates = proof.uv_candidates(interpreter, resolve=lambda path: path)
    assert candidates == [Path(interpreter).parent / "uv"]


def test_uv_on_path_that_is_not_an_executable_file_is_not_accepted() -> None:
    found = proof.find_uv(lambda _name: "/opt/tools/uv", CONTROL, lambda path: path == LIVE_UV)
    assert found == LIVE_UV


def test_uv_is_absent_when_no_candidate_is_an_executable_file() -> None:
    assert proof.find_uv(lambda _name: None, CONTROL, lambda _path: False) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_only_an_existing_executable_regular_file_is_accepted(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "uv"
    directory = tmp_path / "directory" / "uv"
    directory.mkdir(parents=True)
    plain = tmp_path / "plain" / "uv"
    plain.parent.mkdir()
    plain.write_text("#!/bin/sh\n")
    plain.chmod(0o644)
    runnable = tmp_path / "runnable" / "uv"
    runnable.parent.mkdir()
    runnable.write_text("#!/bin/sh\n")
    runnable.chmod(0o755)

    assert not proof.is_executable_file(missing)
    assert not proof.is_executable_file(directory)
    assert not proof.is_executable_file(plain)
    assert proof.is_executable_file(runnable)


def test_a_missing_uv_fails_the_bootstrap_stage(tmp_path: Path) -> None:
    def runner(
        argv: Sequence[str], _cwd: Path, _env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        stdout = SHA + "\n" if list(argv[:2]) == ["git", "rev-parse"] else ""
        return subprocess.CompletedProcess(list(argv), 0, stdout=stdout, stderr="")

    facts: dict[str, Any] = {}
    with pytest.raises(proof.ProofFailure) as failure:
        proof.run_proof(
            tmp_path,
            tmp_path / "proof",
            facts,
            runner=runner,
            environ={},
            which=lambda _name: None,
            executable="/nonexistent-control/bin/python",
        )
    assert failure.value.stage == "bootstrap"
    assert facts["exact_sha"] == SHA
    assert "uv" not in facts


# --- runtime selection and command line ---------------------------------------------------------


def test_the_project_requires_python_admits_both_preferred_pythons() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requires = pyproject["project"]["requires-python"]
    assert proof.PREFERRED_PYTHONS == ((3, 14), (3, 13))
    assert proof.satisfies((3, 14, 0), requires)
    assert proof.satisfies((3, 13, 13), requires)
    assert not proof.satisfies((3, 12, 9), requires)
    assert not proof.satisfies((3, 15, 0), requires)


@pytest.mark.parametrize(
    ("version", "spec", "expected"),
    [
        ((3, 14, 0), ">=3.14", True),
        ((3, 14, 2), ">=3.13,<3.15", True),
        ((3, 13, 7), ">=3.14", False),
        ((3, 15, 0), ">=3.13,<3.15", False),
        ((3, 14), "==3.14.0", True),
        ((3, 14, 1), "!=3.14.1", False),
    ],
)
def test_requires_python_predicate(version: tuple[int, ...], spec: str, expected: bool) -> None:
    assert proof.satisfies(version, spec) is expected


def test_an_unsupported_requires_python_clause_is_refused() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        proof.satisfies((3, 14, 0), "~=3.14")


def test_the_cli_argv_is_exact_and_isolated() -> None:
    argv = proof.cli_argv(Path("/scratch/venv/bin/python"), Path("/checkout/out/canonical"))
    assert argv == [
        "/scratch/venv/bin/python",
        "-I",
        "-m",
        "pxapi.adapters.inbound.acquire_cli",
        "https://www.rfc-editor.org/",
        "--max-selected-pages",
        "3",
        "--output-dir",
        "/checkout/out/canonical",
    ]
    assert proof.ISOLATED_FLAGS == ("-I",)
    assert proof.python_argv(Path("/p"), "-c", "pass") == ["/p", "-I", "-c", "pass"]


def test_the_canonical_files_and_contracts_mirror_the_command_line() -> None:
    produced = acquire_cli.PRODUCED_DOCUMENTS
    assert {member: name for member, (_c, name) in produced.items()} == proof.CANONICAL_FILES
    assert {member: c for member, (c, _n) in produced.items()} == proof.CANONICAL_CONTRACTS
    assert acquire_cli.RECEIPT_FILE == proof.CLI_RECEIPT
    plural = {member for member, shape in acquire_cli.CONTAINER_SHAPES.items() if shape is list}
    assert plural == proof.LIST_MEMBERS
    for contract in proof.CANONICAL_CONTRACTS.values():
        assert CONTRACTS.has_contract(contract), contract
    assert set(proof.PAGE_MEMBERS) == {"page_acquisitions", "measurements", "website_evidence"}


def test_the_verifier_is_told_every_file_its_contract_and_its_container() -> None:
    spec = proof.verifier_spec(Path("/out/canonical"), Path("/checkout/contracts/v1"))
    assert spec["canonical"] == "/out/canonical"
    assert spec["contract_root"] == "/checkout/contracts/v1"
    expected_documents = {
        name: {
            "contract": proof.CANONICAL_CONTRACTS[member],
            "plural": member in proof.LIST_MEMBERS,
        }
        for member, name in proof.CANONICAL_FILES.items()
    }
    assert spec["documents"] == expected_documents
    assert spec["page_documents"] == {
        "manifest": "sampling-manifest.json",
        "records": "page-acquisition-records.json",
        "measurements": "measurement-records.json",
        "evidence": "website-evidence.json",
    }
    argv = proof.verifier_argv(Path("/scratch/venv/bin/python"), spec)
    assert argv[:3] == ["/scratch/venv/bin/python", "-I", "-c"]
    assert argv[3] == proof.CONTRACT_VERIFIER
    assert json.loads(argv[4]) == spec
    assert Path("contracts/v1") == proof.CONTRACT_ROOT
    contract_root = ROOT / proof.CONTRACT_ROOT
    assert contract_root == CONTRACTS_DIR


def test_the_command_environment_cannot_redirect_imports_or_the_registry() -> None:
    environ = {
        "PATH": "/sandbox/bin",
        "PYTHONPATH": "/elsewhere",
        "PYTHONHOME": "/elsewhere",
        "VIRTUAL_ENV": "/elsewhere",
        "SSL_CERT_DIR": "/elsewhere",
        "PXAPI_CONTRACTS_DIR": "/elsewhere/contracts",
        "UV_CACHE_DIR": "/kept",
    }
    env = proof.cli_environment(environ, "/scratch/venv/cacert.pem")
    assert env == {
        "PATH": "/sandbox/bin",
        "UV_CACHE_DIR": "/kept",
        "SSL_CERT_FILE": "/scratch/venv/cacert.pem",
    }


# --- digests and the receipt, recomputed --------------------------------------------------------


def test_the_digest_rules_mirror_the_shipped_producer() -> None:
    assert proof.CANONICAL_JSON == acquisition_digests.CANONICAL_JSON_OPTIONS
    assert proof.INVENTORY_OUTPUT == acquisition_digests.INVENTORY_OUTPUT
    assert proof.MANIFEST_INPUT == acquisition_digests.MANIFEST_INPUT
    assert proof.MANIFEST_OUTPUT == acquisition_digests.MANIFEST_OUTPUT
    assert acquisition_digests.INVENTORY_INPUT == ()
    envelope = _envelope()
    inventory = envelope["site_inventory"]
    manifest = envelope["sampling_manifest"]
    assert proof.inventory_output_projection(
        inventory
    ) == acquisition_digests.inventory_output_projection(inventory)
    assert proof.manifest_input_projection(
        manifest
    ) == acquisition_digests.manifest_input_projection(manifest)
    assert proof.manifest_output_projection(
        manifest
    ) == acquisition_digests.manifest_output_projection(manifest)
    for member in proof.PAGE_MEMBERS:
        assert proof.digest_of(envelope[member]) == acquisition_digests.digest_of(envelope[member])
    assert proof.digest_of({"b": 1, "a": [True, None]}) == acquisition_digests.digest_of(
        {"a": [True, None], "b": 1}
    )


def test_the_recomputed_digests_reproduce_a_real_bundle_s_own_values() -> None:
    envelope = _envelope()
    inventory = envelope["site_inventory"]
    manifest = envelope["sampling_manifest"]
    recomputed = proof.recompute_digests(inventory, manifest)
    assert recomputed == {
        "site_inventory": {"output_digest": inventory["output_digest"]},
        "sampling_manifest": {
            "input_digest": manifest["input_digest"],
            "output_digest": manifest["output_digest"],
        },
    }
    assert all(proof.is_digest(value) for block in recomputed.values() for value in block.values())
    digests = {inventory["output_digest"], manifest["input_digest"], manifest["output_digest"]}
    assert len(digests) == 3
    # The inventory's input digest is over observations the bundle does not carry: shape only.
    assert "input_digest" not in recomputed["site_inventory"]
    assert proof.is_digest(inventory["input_digest"])
    assert not proof.is_digest("sha256:" + "g" * 64)
    assert not proof.is_digest("sha256:" + "0" * 63)
    assert not proof.is_digest(None)


def test_an_ambiguous_document_has_no_recomputable_digest() -> None:
    envelope = _envelope()
    inventory = envelope["site_inventory"]
    manifest = envelope["sampling_manifest"]
    inventory["candidates"].append(dict(inventory["candidates"][0]))
    manifest["selections"][2]["selection_rank"] = 1
    recomputed = proof.recompute_digests(inventory, manifest)
    assert recomputed["site_inventory"]["output_digest"] is None
    assert recomputed["sampling_manifest"]["output_digest"] is None
    assert recomputed["sampling_manifest"]["input_digest"] == manifest["input_digest"]


@pytest.mark.parametrize("envelope", [_envelope(), _mixed(), _envelope(budget=10)])
def test_the_expected_receipt_is_the_command_line_s_receipt_re_derived(
    envelope: dict[str, Any],
) -> None:
    assert proof.expected_receipt(envelope) == acquire_cli.page_receipt(envelope)
    assert proof.expected_receipt(envelope) == _bundle(envelope)[proof.CLI_RECEIPT]


# --- the canonical bundle: the positive cases are real and contract-valid -------------------------


def test_the_positive_fixture_is_itself_contract_valid() -> None:
    envelope = _envelope()
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED"
    assert [s["url_key"] for s in envelope["sampling_manifest"]["selections"]] == list(PAGES)
    assert acquire_cli.container_problems(envelope) == []
    assert acquire_cli.invalid_documents(CONTRACTS, envelope) == []
    violations = acquisition_violations(
        envelope["page_acquisitions"],
        envelope["sampling_manifest"],
        envelope["measurements"],
        envelope["website_evidence"],
    )
    assert violations == ()
    mixed = _mixed()
    assert acquire_cli.invalid_documents(CONTRACTS, mixed) == []


def test_a_coherent_multi_page_bundle_is_accepted() -> None:
    envelope = _envelope()
    receipt = _bundle(envelope)[proof.CLI_RECEIPT]
    problems, summary = _check(envelope)
    assert problems == []
    assert summary["linked_page_refs"] == list(PAGES)
    assert summary["pages"] == receipt["pages"]
    assert summary["document_digests"] == receipt["document_digests"]
    assert summary["recomputed_digests"] == {
        "site_inventory": {"output_digest": envelope["site_inventory"]["output_digest"]},
        "sampling_manifest": {
            "input_digest": envelope["sampling_manifest"]["input_digest"],
            "output_digest": envelope["sampling_manifest"]["output_digest"],
        },
    }
    assert summary["run"]["run_id"] == RUN
    assert summary["run"]["state"] == "SUCCEEDED"
    assert summary["run"]["selection_complete"] is False
    assert summary["document_digests"]["measurements"]["count"] == 39


def test_a_bundle_with_neutral_mixed_page_outcomes_is_accepted() -> None:
    problems, summary = _check(_mixed())
    assert problems == []
    rows = summary["pages"]
    outcomes = [row["acquisition_outcome"] for row in rows]
    assert outcomes == ["RESPONSE_RECEIVED", "RESPONSE_RECEIVED", "TIMEOUT"]
    assert rows[1]["http_status"] == 404
    assert rows[2]["http_status"] is None
    assert rows[2]["not_assessed_reasons"] == ["TIMEOUT"]
    assert summary["linked_page_refs"] == list(PAGES)


def test_a_complete_selection_is_accepted_under_its_budget() -> None:
    problems, summary = _check(_envelope(budget=10), budget=10)
    assert problems == []
    assert summary["run"]["selection_complete"] is True
    assert summary["run"]["incompleteness"] is None


def test_a_one_page_bundle_is_rejected() -> None:
    problems, _summary = _check(_envelope(budget=1), budget=1)
    assert "only 1 page(s) selected; at least 2 needed" in problems
    assert any("resolves for 1 page(s)" in problem for problem in problems)


def test_a_missing_file_is_rejected() -> None:
    files, stdout = _rendered(_envelope())
    del files["website-evidence.json"]
    problems, summary = proof.check_bundle(files, stdout, proof.MAX_SELECTED_PAGES)
    assert problems == ["website-evidence.json: missing"]
    assert summary == {}


def test_an_extra_file_is_rejected() -> None:
    files, stdout = _rendered(_envelope())
    files["stray.json"] = b"{}"
    problems, summary = proof.check_bundle(files, stdout, proof.MAX_SELECTED_PAGES)
    assert problems == ["stray.json: not part of the bundle"]
    assert summary == {}


def test_a_printed_envelope_that_differs_from_the_files_is_rejected() -> None:
    files, _stdout = _rendered(_envelope())
    problems, _summary = proof.check_bundle(files, json.dumps(_envelope(budget=1)), 3)
    assert "stdout: the printed envelope differs from the files written" in problems


def test_a_wrong_budget_is_rejected() -> None:
    problems, _summary = _check(_envelope(), budget=2)
    assert "sampling manifest budget is not max_selected_pages=2" in problems


# --- the canonical bundle: every forgery of a document is rejected ------------------------------

Tamper = Callable[[dict[str, Any]], str]


def _no_schema_version(envelope: dict[str, Any]) -> str:
    del envelope["site_inventory"]["schema_version"]
    return "site-inventory.json/0: declares no schema_version"


def _no_schema_version_in_a_plural(envelope: dict[str, Any]) -> str:
    del envelope["measurements"][2]["schema_version"]
    return "measurement-records.json/2: declares no schema_version"


def _malformed_inventory_digest(envelope: dict[str, Any]) -> str:
    envelope["site_inventory"]["output_digest"] = "sha256:not-a-digest"
    return "site-inventory.json: output_digest is not a sha256 digest"


def _wrong_inventory_digest(envelope: dict[str, Any]) -> str:
    forged = "sha256:" + "0" * 64
    envelope["site_inventory"]["output_digest"] = forged
    envelope["sampling_manifest"]["inventory_output_digest"] = forged
    return "site-inventory.json: output_digest does not reproduce from the document"


def _malformed_inventory_input_digest(envelope: dict[str, Any]) -> str:
    envelope["site_inventory"]["input_digest"] = "sha256:" + "g" * 64
    return "site-inventory.json: input_digest is not a sha256 digest"


def _wrong_manifest_input_digest(envelope: dict[str, Any]) -> str:
    envelope["sampling_manifest"]["input_digest"] = "sha256:" + "1" * 64
    return "sampling-manifest.json: input_digest does not reproduce from the document"


def _wrong_manifest_output_digest(envelope: dict[str, Any]) -> str:
    forged = "sha256:" + "2" * 64
    envelope["sampling_manifest"]["output_digest"] = forged
    for record in envelope["page_acquisitions"]:
        record["sampling_manifest_output_digest"] = forged
    return "sampling-manifest.json: output_digest does not reproduce from the document"


def _duplicate_selection(envelope: dict[str, Any]) -> str:
    selections = envelope["sampling_manifest"]["selections"]
    selections[2]["url_key"] = selections[1]["url_key"]
    return "sampling manifest selects a Page Ref twice"


def _gapped_ranks(envelope: dict[str, Any]) -> str:
    envelope["sampling_manifest"]["selections"][2]["selection_rank"] = 5
    return "sampling manifest ranks are not exactly 1..n"


def _unknown_selection(envelope: dict[str, Any]) -> str:
    envelope["sampling_manifest"]["selections"][1]["url_key"] = "https://example.com/unknown"
    return "page https://example.com/unknown: not a candidate of the bound inventory"


def _missing_acquisition(envelope: dict[str, Any]) -> str:
    del envelope["page_acquisitions"][1]
    return f"page {PAGE_A}: no acquisition record"


def _duplicate_acquisition(envelope: dict[str, Any]) -> str:
    envelope["page_acquisitions"].append(dict(envelope["page_acquisitions"][0]))
    return f"page {ORIGIN}: acquired 2 times"


def _extra_acquisition(envelope: dict[str, Any]) -> str:
    stray = {
        **envelope["page_acquisitions"][0],
        "acquisition_id": "acq-stray",
        "url_key": "https://example.com/stray",
        "measurement_refs": [],
        "measurements_withheld_reason": "SOURCE_URL_NOT_REPRESENTABLE",
    }
    envelope["page_acquisitions"].append(stray)
    return "record acq-stray: not a selected page"


def _record_unbound(envelope: dict[str, Any]) -> str:
    record = envelope["page_acquisitions"][1]
    record["sampling_manifest_ref"] = "man-other"
    return f"record {record['acquisition_id']}: not bound to the manifest"


def _raw_artifact(envelope: dict[str, Any]) -> str:
    record = envelope["page_acquisitions"][0]
    record["raw_artifact_ref"] = "art-1"
    return f"record {record['acquisition_id']}: points at a raw artifact"


def _unexplained_gap(envelope: dict[str, Any]) -> str:
    record = envelope["page_acquisitions"][2]
    record["measurement_refs"] = []
    return (
        f"record {record['acquisition_id']}: measurements neither carried nor withheld "
        "with a reason"
    )


def _missing_measurement(envelope: dict[str, Any]) -> str:
    gone = envelope["measurements"].pop(0)
    owner = envelope["page_acquisitions"][0]["acquisition_id"]
    return f"record {owner}: unknown measurement {gone['measurement_id']}"


def _duplicated_measurement(envelope: dict[str, Any]) -> str:
    first = envelope["measurements"][0]
    envelope["measurements"].append(dict(first))
    return f"measurement {first['measurement_id']}: identity occurs twice"


def _orphan_measurement(envelope: dict[str, Any]) -> str:
    envelope["measurements"].append({**envelope["measurements"][0], "measurement_id": "m-orphan"})
    return "measurement m-orphan: owned by no record"


def _measurement_owned_twice(envelope: dict[str, Any]) -> str:
    shared = envelope["page_acquisitions"][0]["measurement_refs"][0]
    envelope["page_acquisitions"][1]["measurement_refs"].append(shared)
    return f"measurement {shared}: owned by two records"


def _measurement_named_twice(envelope: dict[str, Any]) -> str:
    record = envelope["page_acquisitions"][0]
    record["measurement_refs"].append(record["measurement_refs"][0])
    return f"record {record['acquisition_id']}: names a measurement twice"


def _metric_measured_twice(envelope: dict[str, Any]) -> str:
    record = envelope["page_acquisitions"][0]
    twin = {**envelope["measurements"][0], "measurement_id": "m-twin"}
    envelope["measurements"].append(twin)
    record["measurement_refs"].append("m-twin")
    return f"record {record['acquisition_id']}: measures {twin['metric_id']} twice"


def _measurement_out_of_context(envelope: dict[str, Any]) -> str:
    item = envelope["measurements"][0]
    item["observed_at"] = "2020-01-01T00:00:00Z"
    return f"measurement {item['measurement_id']}: not observed at its page's acquisition instant"


def _measurements_from_two_response_urls(envelope: dict[str, Any]) -> str:
    record = envelope["page_acquisitions"][0]
    refs = record["measurement_refs"]
    by_id = {item["measurement_id"]: item for item in envelope["measurements"]}
    by_id[refs[0]]["source_url"] = "https://example.com/x"
    by_id[refs[2]]["source_url"] = "https://example.com/y"
    return (
        f"record {record['acquisition_id']}: measurements are sourced at more than one response URL"
    )


def _unlinked_evidence(envelope: dict[str, Any]) -> str:
    item = envelope["website_evidence"][1]
    item["measurement_refs"] = ["m-unknown"]
    return f"evidence {item['evidence_id']}: not linked to exactly one page"


def _empty_evidence(envelope: dict[str, Any]) -> str:
    item = envelope["website_evidence"][0]
    item["measurement_refs"] = []
    return f"evidence {item['evidence_id']}: references no measurement"


def _duplicated_evidence(envelope: dict[str, Any]) -> str:
    first = envelope["website_evidence"][0]
    envelope["website_evidence"].append(dict(first))
    return f"evidence {first['evidence_id']}: identity occurs twice"


def _cross_page_evidence(envelope: dict[str, Any]) -> str:
    records = envelope["page_acquisitions"]
    item = envelope["website_evidence"][0]
    item["measurement_refs"] = [
        records[0]["measurement_refs"][0],
        records[1]["measurement_refs"][0],
    ]
    return f"evidence {item['evidence_id']}: not linked to exactly one page"


def _evidence_out_of_context(envelope: dict[str, Any]) -> str:
    item = envelope["website_evidence"][0]
    item["source_url"] = "https://example.com/elsewhere"
    (ref,) = item["measurement_refs"]
    return f"evidence {item['evidence_id']}: context differs from measurement {ref}"


def _polarised_evidence(envelope: dict[str, Any]) -> str:
    item = envelope["website_evidence"][0]
    item["polarity"] = "NEGATIVE"
    return f"evidence {item['evidence_id']}: carries a polarity"


def _another_run(envelope: dict[str, Any]) -> str:
    envelope["measurements"][1]["run_id"] = "run-0002"
    return "measurement-records.json/1: belongs to another run"


def _failed_state(envelope: dict[str, Any]) -> str:
    envelope["analysis_run_state"]["state"] = "FAILED"
    return "run state is 'FAILED', not 'SUCCEEDED'"


DOCUMENT_TAMPERS: dict[str, Tamper] = {
    "no-schema-version": _no_schema_version,
    "no-schema-version-in-a-plural": _no_schema_version_in_a_plural,
    "malformed-inventory-output-digest": _malformed_inventory_digest,
    "wrong-inventory-output-digest": _wrong_inventory_digest,
    "malformed-inventory-input-digest": _malformed_inventory_input_digest,
    "wrong-manifest-input-digest": _wrong_manifest_input_digest,
    "wrong-manifest-output-digest": _wrong_manifest_output_digest,
    "duplicate-selection": _duplicate_selection,
    "gapped-ranks": _gapped_ranks,
    "unknown-selection": _unknown_selection,
    "missing-acquisition": _missing_acquisition,
    "duplicate-acquisition": _duplicate_acquisition,
    "extra-acquisition": _extra_acquisition,
    "record-unbound": _record_unbound,
    "raw-artifact": _raw_artifact,
    "unexplained-gap": _unexplained_gap,
    "missing-measurement": _missing_measurement,
    "duplicated-measurement": _duplicated_measurement,
    "orphan-measurement": _orphan_measurement,
    "measurement-owned-twice": _measurement_owned_twice,
    "measurement-named-twice": _measurement_named_twice,
    "metric-measured-twice": _metric_measured_twice,
    "measurement-out-of-context": _measurement_out_of_context,
    "two-response-urls": _measurements_from_two_response_urls,
    "unlinked-evidence": _unlinked_evidence,
    "empty-evidence": _empty_evidence,
    "duplicated-evidence": _duplicated_evidence,
    "cross-page-evidence": _cross_page_evidence,
    "evidence-out-of-context": _evidence_out_of_context,
    "polarised-evidence": _polarised_evidence,
    "another-run": _another_run,
    "failed-state": _failed_state,
}


@pytest.mark.parametrize("case", sorted(DOCUMENT_TAMPERS))
def test_a_forged_canonical_document_is_rejected_even_with_a_matching_receipt(case: str) -> None:
    """The receipt is regenerated from the forged documents, so only the document checks bite."""
    envelope = _envelope()
    expected = DOCUMENT_TAMPERS[case](envelope)
    problems, _summary = _check(envelope)
    assert expected in problems, problems


def test_a_forged_digest_copied_into_the_receipt_is_caught_on_both_sides() -> None:
    envelope = _envelope()
    _wrong_inventory_digest(envelope)
    problems, _summary = _check(envelope)
    assert "site-inventory.json: output_digest does not reproduce from the document" in problems
    assert "sampling-manifest.json: input_digest does not reproduce from the document" in problems
    assert "receipt.json: site_inventory does not describe the canonical documents" in problems
    assert "receipt.json: sampling_manifest does not describe the canonical documents" in problems


def test_a_measurement_of_a_page_without_a_response_is_sourced_at_its_page_ref() -> None:
    envelope = _mixed()
    record = envelope["page_acquisitions"][2]
    assert record["acquisition_outcome"] == "TIMEOUT"
    ref = record["measurement_refs"][0]
    item = next(m for m in envelope["measurements"] if m["measurement_id"] == ref)
    item["source_url"] = PAGE_A
    problems, _summary = _check(envelope)
    expected = (
        f"record {record['acquisition_id']}: measurements of a page without a response are not "
        "sourced at its Page Ref"
    )
    assert expected in problems
    evidence_problems = [problem for problem in problems if problem.startswith("evidence ")]
    assert any("context differs" in problem for problem in evidence_problems)


def test_the_missing_and_duplicate_acquisition_cases_report_the_whole_chain() -> None:
    envelope = _envelope()
    _missing_acquisition(envelope)
    problems, _summary = _check(envelope)
    assert "acquisition records are not exactly the selection in rank order" in problems
    assert sum(problem.endswith(": owned by no record") for problem in problems) == 13
    assert sum("not linked to exactly one page" in problem for problem in problems) == 13

    envelope = _envelope()
    _duplicate_acquisition(envelope)
    problems, _summary = _check(envelope)
    first = envelope["page_acquisitions"][0]["acquisition_id"]
    assert f"record {first}: acquisition identity occurs twice" in problems
    assert sum(problem.endswith(": owned by two records") for problem in problems) == 13


# --- the canonical bundle: every forgery of the receipt is rejected -----------------------------


def _forged_count(receipt: dict[str, Any]) -> str:
    receipt["document_digests"]["page_acquisitions"]["count"] = 4
    return "document_digests"


def _forged_digest(receipt: dict[str, Any]) -> str:
    receipt["document_digests"]["measurements"]["digest"] = "sha256:" + "a" * 64
    return "document_digests"


def _forged_selected_count(receipt: dict[str, Any]) -> str:
    receipt["sampling_manifest"]["selected_count"] = 2
    return "sampling_manifest"


def _forged_manifest_digest(receipt: dict[str, Any]) -> str:
    receipt["sampling_manifest"]["output_digest"] = "sha256:" + "b" * 64
    return "sampling_manifest"


def _forged_inventory_digest(receipt: dict[str, Any]) -> str:
    receipt["site_inventory"]["output_digest"] = "sha256:" + "c" * 64
    return "site_inventory"


def _forged_candidate_count(receipt: dict[str, Any]) -> str:
    receipt["site_inventory"]["candidate_count"] = 506
    return "site_inventory"


def _forged_run_state(receipt: dict[str, Any]) -> str:
    receipt["run_state"] = "FAILED"
    return "run_state"


RECEIPT_FORGERIES: dict[str, Callable[[dict[str, Any]], str]] = {
    "document-count": _forged_count,
    "semantic-digest": _forged_digest,
    "selected-count": _forged_selected_count,
    "manifest-digest": _forged_manifest_digest,
    "inventory-digest": _forged_inventory_digest,
    "candidate-count": _forged_candidate_count,
    "run-state": _forged_run_state,
}


@pytest.mark.parametrize("case", sorted(RECEIPT_FORGERIES))
def test_a_forged_receipt_member_is_rejected(case: str) -> None:
    envelope = _envelope()
    bundle = _bundle(envelope)
    member = RECEIPT_FORGERIES[case](bundle[proof.CLI_RECEIPT])
    problems, _summary = _check(envelope, bundle)
    assert problems == [f"receipt.json: {member} does not describe the canonical documents"]


def _row_outcome(rows: list[dict[str, Any]]) -> tuple[int, str]:
    rows[0]["acquisition_outcome"] = "TIMEOUT"
    return 0, "acquisition_outcome"


def _row_status(rows: list[dict[str, Any]]) -> tuple[int, str]:
    rows[0]["http_status"] = 500
    return 0, "http_status"


def _row_refs(rows: list[dict[str, Any]]) -> tuple[int, str]:
    rows[1]["measurement_refs"].pop()
    return 1, "measurement_refs"


def _row_evidence(rows: list[dict[str, Any]]) -> tuple[int, str]:
    rows[1]["evidence_refs"] = list(rows[0]["evidence_refs"])
    return 1, "evidence_refs"


def _row_reasons(rows: list[dict[str, Any]]) -> tuple[int, str]:
    rows[2]["not_assessed_reasons"] = ["TIMEOUT"]
    return 2, "not_assessed_reasons"


def _row_withheld(rows: list[dict[str, Any]]) -> tuple[int, str]:
    rows[2]["measurements_withheld_reason"] = "SOURCE_URL_NOT_REPRESENTABLE"
    return 2, "measurements_withheld_reason"


def _row_rank(rows: list[dict[str, Any]]) -> tuple[int, str]:
    rows[0]["selection_rank"] = 3
    return 0, "selection_rank"


def _row_body_digest(rows: list[dict[str, Any]]) -> tuple[int, str]:
    rows[2]["body_digest"] = "sha256:" + "d" * 64
    return 2, "body_digest"


ROW_FORGERIES: dict[str, Callable[[list[dict[str, Any]]], tuple[int, str]]] = {
    "outcome": _row_outcome,
    "status": _row_status,
    "measurement-refs": _row_refs,
    "evidence-refs": _row_evidence,
    "reasons": _row_reasons,
    "withheld-reason": _row_withheld,
    "rank": _row_rank,
    "body-digest": _row_body_digest,
}


@pytest.mark.parametrize("case", sorted(ROW_FORGERIES))
def test_a_forged_receipt_page_row_is_rejected(case: str) -> None:
    envelope = _envelope()
    bundle = _bundle(envelope)
    index, member = ROW_FORGERIES[case](bundle[proof.CLI_RECEIPT]["pages"])
    problems, _summary = _check(envelope, bundle)
    assert problems == [f"receipt.json: page row {index} differs in {member}"]


def test_a_receipt_with_the_wrong_rows_or_members_is_rejected() -> None:
    envelope = _envelope()
    bundle = _bundle(envelope)
    receipt = bundle[proof.CLI_RECEIPT]
    receipt["pages"].append(dict(receipt["pages"][0]))
    receipt["verdict"] = "GREEN"
    del receipt["document_digests"]
    problems, _summary = _check(envelope, bundle)
    assert problems == [
        "receipt.json: document_digests is missing",
        "receipt.json: verdict is not derivable from the canonical documents",
        "receipt.json: 4 page row(s) for 3 acquisition record(s)",
    ]

    bundle = _bundle(envelope)
    bundle[proof.CLI_RECEIPT]["pages"] = None
    problems, _summary = _check(envelope, bundle)
    assert problems == ["receipt.json: pages is not a list"]


# --- the canonical bundle: malformed input is reported, never raised ----------------------------


def _scalar_selections(envelope: dict[str, Any]) -> None:
    envelope["sampling_manifest"]["selections"] = "x"


def _boolean_rank(envelope: dict[str, Any]) -> None:
    envelope["sampling_manifest"]["selections"][0]["selection_rank"] = True


def _scalar_refs(envelope: dict[str, Any]) -> None:
    envelope["page_acquisitions"][0]["measurement_refs"] = "nope"


def _scalar_candidates(envelope: dict[str, Any]) -> None:
    envelope["site_inventory"]["candidates"] = 7


def _null_failure(envelope: dict[str, Any]) -> None:
    envelope["analysis_run_state"]["failure"] = None


def _list_source(envelope: dict[str, Any]) -> None:
    envelope["site_inventory"]["sources"][0] = ["not", "an", "object"]


MALFORMED: dict[str, Callable[[dict[str, Any]], None]] = {
    "scalar-selections": _scalar_selections,
    "boolean-rank": _boolean_rank,
    "scalar-refs": _scalar_refs,
    "scalar-candidates": _scalar_candidates,
    "null-failure": _null_failure,
    "list-source": _list_source,
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_a_malformed_bundle_is_reported_deterministically_not_raised(case: str) -> None:
    envelope = _envelope()
    MALFORMED[case](envelope)
    # The receipt of the untampered run stays beside the malformed documents: the command
    # line's own receipt derivation is not asked to survive input it never produced.
    untampered = _bundle(_envelope())
    files = {name: json.dumps(value).encode("utf-8") for name, value in untampered.items()}
    for member, name in proof.CANONICAL_FILES.items():
        files[name] = json.dumps(envelope[member]).encode("utf-8")
    stdout = json.dumps(envelope)
    problems, _summary = proof.check_bundle(files, stdout, 3)
    assert problems
    assert problems == proof.check_bundle(files, stdout, 3)[0]


def test_non_json_constants_and_wrong_containers_are_rejected_before_any_linkage() -> None:
    files, stdout = _rendered(_envelope())
    files["site-inventory.json"] = b'{"schema_version": "1.0.0", "x": NaN}'
    files["sampling-manifest.json"] = b"[]"
    problems, summary = proof.check_bundle(files, stdout, 3)
    assert problems == [
        "site-inventory.json: not valid JSON",
        "sampling-manifest.json: unexpected document shape",
    ]
    assert summary == {}


# --- the verifier, run for real in this interpreter under -I ------------------------------------


def _verify(files: Mapping[str, bytes], directory: Path) -> dict[str, Any]:
    """Run :data:`CONTRACT_VERIFIER` as the harness runs it, against the real registry."""
    canonical = directory / "canonical"
    canonical.mkdir()
    for name, data in files.items():
        (canonical / name).write_bytes(data)
    workdir = directory / "cwd"
    workdir.mkdir()
    spec = proof.verifier_spec(canonical, CONTRACTS_DIR)
    completed = subprocess.run(
        proof.verifier_argv(Path(sys.executable), spec),
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_the_verifier_accepts_the_positive_fixture_and_binds_its_origin(tmp_path: Path) -> None:
    files, _stdout = _rendered(_envelope())
    report = _verify(files, tmp_path)
    assert proof.verification_problems(report) == []
    assert report["isolated"] is True
    assert report["safe_path"] is True
    assert report["contract_root"] == os.path.realpath(CONTRACTS_DIR)
    assert report["producer_violations"] == []
    assert report["problems"] == []
    assert {name: entry["count"] for name, entry in report["documents"].items()} == {
        "analysis-run-request.json": 1,
        "analysis-run-state.json": 1,
        "stage-execution-records.json": 3,
        "site-inventory.json": 1,
        "sampling-manifest.json": 1,
        "page-acquisition-records.json": 3,
        "measurement-records.json": 39,
        "website-evidence.json": 39,
    }
    assert proof.origin_binding(report["pxapi_origin"], ROOT, tmp_path / "venv") == TRACKED_ORIGIN
    assert proof.isolation_problem(report, ROOT, tmp_path / "venv") is None


def test_the_verifier_rejects_a_document_without_schema_version(tmp_path: Path) -> None:
    envelope = _envelope()
    del envelope["site_inventory"]["schema_version"]
    files, _stdout = _rendered(envelope)
    problems = proof.verification_problems(_verify(files, tmp_path))
    # The reference validator reports a missing required member at the containing object,
    # which for a root member is the empty pointer; the keyword is what names the defect.
    prefix = "site-inventory.json/0: violates site-inventory at "
    required = [p for p in problems if p.startswith(prefix) and p.endswith("[required]")]
    assert required, problems


def test_the_verifier_rejects_an_invalid_digest_string(tmp_path: Path) -> None:
    envelope = _envelope()
    envelope["site_inventory"]["output_digest"] = "sha256:not-a-digest"
    envelope["measurements"][4]["schema_version"] = "9.9.9"
    files, _stdout = _rendered(envelope)
    problems = proof.verification_problems(_verify(files, tmp_path))
    prefix = "site-inventory.json/0: violates site-inventory at /output_digest ["
    assert any(problem.startswith(prefix) for problem in problems), problems
    assert (
        "measurement-records.json/4: violates measurement-record at /schema_version [const]"
        in problems
    )


def test_the_verifier_applies_the_acquisition_producer_invariants(tmp_path: Path) -> None:
    envelope = _envelope()
    envelope["page_acquisitions"].append(dict(envelope["page_acquisitions"][0]))
    files, _stdout = _rendered(envelope)
    problems = proof.verification_problems(_verify(files, tmp_path))
    assert "page documents: /page_acquisitions [one_record_per_selection]" in problems
    assert "page documents: /page_acquisitions/3 [unique_acquisition_id]" in problems
    assert "page documents: /page_acquisitions/3 [measurement_owned_once]" in problems


def test_the_verifier_reports_a_misshapen_or_unreadable_file_instead_of_raising(
    tmp_path: Path,
) -> None:
    files, _stdout = _rendered(_envelope())
    files["sampling-manifest.json"] = b"[]"
    files["measurement-records.json"] = b"\xff\xfe"
    problems = proof.verification_problems(_verify(files, tmp_path))
    assert "sampling-manifest.json: container is not one JSON object" in problems
    assert "measurement-records.json: unreadable (UnicodeDecodeError)" in problems
    assert "page documents: the producer invariants cannot be applied" in problems
    assert not any(problem.endswith("not validated") for problem in problems)


# --- the verifier's report, interpreted ---------------------------------------------------------


def _healthy_report(origin: str) -> dict[str, Any]:
    return {
        "pxapi_origin": origin,
        "executable": "/scratch/venv/bin/python",
        "isolated": True,
        "safe_path": True,
        "contract_root": str(ROOT / "contracts" / "v1"),
        "documents": {
            name: {"contract": proof.CANONICAL_CONTRACTS[member], "count": 1, "violations": []}
            for member, name in proof.CANONICAL_FILES.items()
        },
        "producer_violations": [],
        "problems": [],
    }


def test_the_origin_is_bound_to_the_tracked_source_or_the_locked_environment(
    tmp_path: Path,
) -> None:
    root = tmp_path / "checkout"
    venv = tmp_path / "scratch" / "venv"
    tracked = root / "src" / "pxapi" / "__init__.py"
    installed = venv / "lib" / "python3.14" / "site-packages" / "pxapi" / "__init__.py"
    installed_origin = "locked disposable project environment"
    assert proof.origin_binding(str(tracked), root, venv) == TRACKED_ORIGIN
    assert proof.origin_binding(str(installed), root, venv) == installed_origin
    for elsewhere in (
        root / "pxapi" / "__init__.py",
        root / "src" / "pxapi" / "adapters" / "__init__.py",
        tmp_path / "other-checkout" / "src" / "pxapi" / "__init__.py",
        root / "src" / "pxapi" / "__main__.py",
        tmp_path / ".local" / "lib" / "python3.14" / "site-packages" / "pxapi" / "__init__.py",
    ):
        assert proof.origin_binding(str(elsewhere), root, venv) is None, elsewhere
    assert proof.origin_binding(None, root, venv) is None
    assert proof.origin_binding("", root, venv) is None


def test_an_unisolated_runtime_or_a_foreign_registry_is_an_isolation_problem(
    tmp_path: Path,
) -> None:
    root = ROOT
    venv = tmp_path / "venv"
    origin = str(ROOT / "src" / "pxapi" / "__init__.py")
    assert proof.isolation_problem(_healthy_report(origin), root, venv) is None
    for field in ("isolated", "safe_path"):
        report = {**_healthy_report(origin), field: False}
        assert "isolated mode" in str(proof.isolation_problem(report, root, venv))
    report = _healthy_report(str(ROOT / "pxapi" / "__init__.py"))
    assert "not the locked project" in str(proof.isolation_problem(report, root, venv))
    report = {**_healthy_report(origin), "contract_root": str(tmp_path / "contracts" / "v1")}
    assert "contract root" in str(proof.isolation_problem(report, root, venv))


def test_a_report_that_is_not_the_verifier_s_is_itself_a_problem() -> None:
    assert proof.verification_problems(None) == [
        "verification: the verifier printed no JSON object"
    ]
    assert proof.verification_problems({}) == [
        "verification: the verifier validated no document",
        "page documents: the producer invariants were not applied",
    ]
    report = _healthy_report("/x")
    del report["documents"]["website-evidence.json"]
    report["producer_violations"] = None
    assert proof.verification_problems(report) == [
        "website-evidence.json: not validated",
        "page documents: the producer invariants were not applied",
    ]
    report = _healthy_report("/x")
    report["documents"]["site-inventory.json"]["violations"] = "broken"
    assert proof.verification_problems(report) == [
        "verification: malformed verifier report (TypeError)"
    ]


def test_shadowing_entries_name_exactly_the_importable_shapes(tmp_path: Path) -> None:
    for name in ("pxapi.py", "pxapi.pyc", "pxapi.cpython-314-darwin.so", "pxapi_tools", "tools"):
        (tmp_path / name).write_text("")
    (tmp_path / "pxapi").mkdir()
    (tmp_path / "src").mkdir()
    assert proof.shadowing_entries(tmp_path) == [
        "pxapi",
        "pxapi.cpython-314-darwin.so",
        "pxapi.py",
        "pxapi.pyc",
    ]
    assert proof.shadowing_entries(tmp_path / "src") == []


# --- the proof receipt --------------------------------------------------------------------------


def _minor(request: str) -> str:
    """The preferred minor a ``uv python find`` request pins (``...,==3.14.*`` -> ``"3.14"``)."""
    match = re.search(r"==(\d+\.\d+)\.\*$", request)
    assert match is not None, f"request pins no minor: {request!r}"
    return match.group(1)


Verifier = Callable[[Sequence[str], Path, Mapping[str, str]], str]


def _real_verifier(argv: Sequence[str], cwd: Path, env: Mapping[str, str]) -> str:
    """The harness's verifier command, run for real by this test interpreter."""
    completed = subprocess.run(
        [sys.executable, *argv[1:]],
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


class ScriptedHost:
    """Answers every command the proof issues as a healthy host would, and records them.

    ``installed`` maps the minor a ``uv python find`` request pins (``"3.14"``) to the release
    the interpreter it names reports; the interpreter lives in ``<tmp>/python<minor>/bin``. Like
    real ``uv python find --system``, a request is answered as uv does when nothing is installed
    unless that directory is on the ``PATH`` the lookup was given. The project venv reports the
    synced interpreter's release unless ``project_version`` says otherwise. The command line
    publishes ``envelope`` (a real one by default) exactly as the shipped command line would,
    after ``bundle_tamper``; the verifier answers with a healthy report naming ``origin`` after
    ``report_tamper``, unless a real ``verifier`` is given.
    """

    def __init__(
        self,
        tmp_path: Path,
        installed: Mapping[str, Sequence[int]] | None = None,
        *,
        project_version: Sequence[int] | None = None,
        managed_dir: Path | None = None,
        lock_rewrite: tuple[Path, bytes] | None = None,
        untracked: str = "",
        origin: Path | None = None,
        envelope: dict[str, Any] | None = None,
        bundle_tamper: Callable[[dict[str, Any]], None] | None = None,
        report_tamper: Callable[[dict[str, Any]], None] | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        self.uv = tmp_path / "bin" / "uv"
        self.uv.parent.mkdir()
        self.uv.write_text("#!/bin/sh\nexit 1\n")
        self.uv.chmod(0o755)
        self.trust_bundle = tmp_path / "cacert.pem"
        self.trust_bundle.write_text("certificates\n")
        installed = {"3.14": (3, 14, 0)} if installed is None else installed
        self.pythons = {
            request: (tmp_path / f"python{request}" / "bin" / f"python{request}", list(info))
            for request, info in installed.items()
        }
        self.project_version = None if project_version is None else list(project_version)
        self.managed_dir = managed_dir
        self.lock_rewrite = lock_rewrite
        self.untracked = untracked
        default_origin = tmp_path / "checkout" / "src" / "pxapi" / "__init__.py"
        self.origin = default_origin if origin is None else origin
        self.envelope = _envelope() if envelope is None else envelope
        self.bundle_tamper = bundle_tamper
        self.report_tamper = report_tamper
        self.verifier = verifier
        self.synced: str | None = None
        self.calls: list[list[str]] = []
        self.cwds: list[Path] = []
        self.envs: list[dict[str, str]] = []

    def python(self, request: str) -> Path:
        return self.pythons[request][0]

    def search_path(self) -> str:
        """A ``PATH`` on which every installed interpreter is visible, as on a healthy host."""
        return os.pathsep.join(
            ["/usr/bin", *(str(path.parent) for path, _ in self.pythons.values())]
        )

    def _visible(self, request: str, env: Mapping[str, str]) -> bool:
        if _minor(request) not in self.pythons:
            return False
        entries = env.get("PATH", "").split(os.pathsep)
        return str(self.python(_minor(request)).parent) in entries

    def __call__(
        self, argv: Sequence[str], cwd: Path, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        argv = list(argv)
        self.calls.append(argv)
        self.cwds.append(Path(cwd))
        self.envs.append(dict(env))
        if argv[:3] == [str(self.uv), "python", "find"] and not self._visible(argv[-1], env):
            stderr = f"error: No interpreter found for Python {argv[-1]} in system path\n"
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr=stderr)
        if argv[:3] == [str(self.uv), "python", "dir"] and (
            "UV_CONFIG_FILE" in env or "UV_PROJECT" in env
        ):
            # Real uv exits 2 on an unreadable UV_CONFIG_FILE or a UV_PROJECT without a project.
            stderr = "error: Failed to parse the configured uv settings\n"
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr=stderr)
        stdout = self._answer(argv, Path(cwd), env)
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def _answer(self, argv: list[str], cwd: Path, env: Mapping[str, str]) -> str:
        if argv[:2] == ["git", "rev-parse"]:
            return SHA + "\n"
        if argv[:2] == ["git", "status"]:
            return self.untracked if "--untracked-files=all" in argv else ""
        if argv[0] == str(self.uv):
            if argv[1] == "--version":
                return "uv 0.9.99\n"
            if argv[1:3] == ["python", "find"]:
                return f"{self.python(_minor(argv[-1]))}\n"
            if argv[1:3] == ["python", "dir"]:
                install_dir = env.get("UV_PYTHON_INSTALL_DIR", self.managed_dir or "/nowhere")
                return f"{install_dir}\n"
            if argv[1] == "sync":
                self.synced = argv[argv.index("--python") + 1]
                if self.lock_rewrite is not None:
                    self.lock_rewrite[0].write_bytes(self.lock_rewrite[1])
                return ""
        if argv[1:4] == ["-I", "-c", proof.PROBE]:
            by_path = {str(path): info for path, info in self.pythons.values()}
            if argv[0] in by_path:
                prefix, info = "/usr/local", by_path[argv[0]]
            else:
                assert argv[0] == str(proof.venv_python(Path(env["UV_PROJECT_ENVIRONMENT"])))
                assert self.synced is not None, "the venv is probed only after uv sync"
                prefix = env["UV_PROJECT_ENVIRONMENT"]
                info = self.project_version or by_path[self.synced]
            version = ".".join(str(part) for part in info)
            probe = {"prefix": prefix, "version": version, "version_info": info}
            return json.dumps({"executable": argv[0], **probe}) + "\n"
        if argv[1:4] == ["-I", "-c", proof.CERTIFI_PROBE]:
            return f"{self.trust_bundle}\n"
        if argv[1:4] == ["-I", "-m", proof.CLI_MODULE]:
            output = Path(argv[-1])
            output.mkdir(parents=True)
            bundle = _bundle(self.envelope)
            if self.bundle_tamper is not None:
                self.bundle_tamper(bundle)
            files, stdout = _rendered(self.envelope, bundle)
            for name, data in files.items():
                (output / name).write_bytes(data)
            return stdout
        if argv[1:4] == ["-I", "-c", proof.CONTRACT_VERIFIER]:
            if self.verifier is not None:
                return self.verifier(argv, cwd, env)
            report = self._report(json.loads(argv[4]), argv[0])
            if self.report_tamper is not None:
                self.report_tamper(report)
            return json.dumps(report) + "\n"
        raise AssertionError(f"unexpected command {argv}")

    def _report(self, spec: dict[str, Any], executable: str) -> dict[str, Any]:
        """What the real verifier reports about a valid bundle, without running it."""
        canonical = Path(spec["canonical"])
        documents = {}
        for name, entry in spec["documents"].items():
            value = json.loads((canonical / name).read_bytes())
            count = len(value) if entry["plural"] else 1
            documents[name] = {"contract": entry["contract"], "count": count, "violations": []}
        return {
            "pxapi_origin": str(self.origin),
            "executable": executable,
            "isolated": True,
            "safe_path": True,
            "contract_root": spec["contract_root"],
            "documents": documents,
            "producer_violations": [],
            "problems": [],
        }


def _checkout(tmp_path: Path, requires: str = ">=3.13,<3.15") -> Path:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "pyproject.toml").write_text(f'[project]\nrequires-python = "{requires}"\n')
    (root / "uv.lock").write_bytes(b"version = 1\n")
    return root


WellKnown = Callable[[Sequence[int]], Sequence[Path]]


def _no_well_known(_wanted: Sequence[int]) -> list[Path]:
    """A host whose well-known directories add nothing: only the inherited ``PATH`` counts."""
    return []


def _run(
    root: Path,
    host: ScriptedHost,
    facts: dict[str, Any],
    *,
    path: str | None = None,
    well_known: WellKnown = _no_well_known,
    proof_dir: Path | None = None,
) -> None:
    proof.run_proof(
        root,
        root / proof.PROOF_DIR if proof_dir is None else proof_dir,
        facts,
        runner=host,
        environ={
            "PATH": host.search_path() if path is None else path,
            "HOME": SCRATCH_HOME,
            "VIRTUAL_ENV": "/elsewhere",
        },
        which=lambda _name: str(host.uv),
        executable=CONTROL,
        expected_sha=SHA,
        system_directories=well_known,
    )


def _cli_ran(host: ScriptedHost) -> bool:
    return any(call[1:4] == ["-I", "-m", proof.CLI_MODULE] for call in host.calls)


def _failed(
    root: Path,
    host: ScriptedHost,
    *,
    path: str | None = None,
    well_known: WellKnown = _no_well_known,
) -> tuple[proof.ProofFailure, dict[str, Any]]:
    facts: dict[str, Any] = {}
    with pytest.raises(proof.ProofFailure) as failure:
        _run(root, host, facts, path=path, well_known=well_known)
    assert not _cli_ran(host)
    return failure.value, facts


def _failed_after_the_cli(
    root: Path, host: ScriptedHost
) -> tuple[proof.ProofFailure, dict[str, Any]]:
    facts: dict[str, Any] = {}
    with pytest.raises(proof.ProofFailure) as failure:
        _run(root, host, facts)
    assert _cli_ran(host)
    return failure.value, facts


def _finds(host: ScriptedHost) -> list[str]:
    return [call[-1] for call in host.calls if call[1:3] == ["python", "find"]]


def _find_paths(host: ScriptedHost) -> list[str]:
    """The ``PATH`` each ``uv python find`` was given, in lookup order."""
    return [
        env.get("PATH", "")
        for call, env in zip(host.calls, host.envs, strict=True)
        if call[1:3] == ["python", "find"]
    ]


def _inherited_only(path: str) -> dict[str, list[str]]:
    """The search-path provenance when no well-known directory was considered."""
    return {
        "inherited": path.split(os.pathsep),
        "well_known": [],
        "added": [],
        "absent": [],
        "excluded": [],
        "already_present": [],
    }


def _synced(host: ScriptedHost) -> list[list[str]]:
    return [call for call in host.calls if call[1:2] == ["sync"]]


def test_a_passing_proof_receipt_preserves_every_recorded_fact(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path)
    proof_dir = root / proof.PROOF_DIR
    facts: dict[str, Any] = {}
    proof.run_proof(
        root,
        proof_dir,
        facts,
        runner=host,
        environ={"PATH": host.search_path()},
        which=lambda _name: str(host.uv),
        executable=CONTROL,
        expected_sha=SHA,
        system_directories=_no_well_known,
    )
    receipt = json.loads(json.dumps(proof.build_receipt(facts, None)))
    published = _bundle(host.envelope)[proof.CLI_RECEIPT]

    lock_digest = "sha256:" + hashlib.sha256(b"version = 1\n").hexdigest()
    assert receipt["verdict"] == "PASSED"
    assert receipt["failure"] is None
    assert receipt["exact_sha"] == SHA
    assert receipt["control_runtime"]["executable"] == CONTROL
    assert receipt["uv"] == {"path": str(host.uv), "version": "uv 0.9.99"}
    assert receipt["selected_python"] == {
        "path": str(host.python("3.14")),
        "version": "3.14.0",
        "requires_python": ">=3.13,<3.15",
    }
    assert receipt["python_candidates"] == [
        {
            "requested": "3.14",
            "request": ">=3.13,<3.15,==3.14.*",
            "search_path": _inherited_only(host.search_path()),
            "path": str(host.python("3.14")),
            "discovered_via": f"inherited PATH entry {host.python('3.14').parent}",
            "version": "3.14.0",
            "outcome": "selected",
        }
    ]
    assert receipt["project_runtime"]["version"] == "3.14.0"
    assert receipt["requires_python"] == ">=3.13,<3.15"
    assert receipt["lock"] == {
        "sha256_before": lock_digest,
        "sha256_after": lock_digest,
        "unchanged": True,
    }
    assert receipt["target"] == "https://www.rfc-editor.org/"
    assert receipt["max_selected_pages"] == 3
    argv = receipt["cli"]["argv"]
    assert argv[1:4] == ["-I", "-m", proof.CLI_MODULE]
    assert argv[4:7] == ["https://www.rfc-editor.org/", "--max-selected-pages", "3"]
    assert argv[-1] == str(proof_dir / proof.CANONICAL_DIR)
    assert receipt["isolation"]["untracked_forbidden_under"] == ["src", "contracts"]
    assert receipt["isolation"]["untracked_entries"] == []
    assert receipt["isolation"]["checkout_root_shadowing_entries"] == []
    assert receipt["isolation"]["interpreter_flags"] == ["-I"]
    workdir = Path(receipt["isolation"]["working_directory"])
    assert workdir.name == "cwd" and not workdir.is_relative_to(root)
    assert receipt["verification"]["bound_to"] == TRACKED_ORIGIN
    assert receipt["verification"]["pxapi_origin"] == str(host.origin)
    assert receipt["verification"]["contract_root"] == str(root / "contracts" / "v1")
    assert receipt["verification"]["producer_violations"] == []
    assert set(receipt["verification"]["documents"]) == set(proof.CANONICAL_FILES.values())
    assert receipt["pages"] == published["pages"]
    assert receipt["document_digests"] == published["document_digests"]
    assert receipt["recomputed_digests"]["sampling_manifest"] == {
        "input_digest": published["sampling_manifest"]["input_digest"],
        "output_digest": published["sampling_manifest"]["output_digest"],
    }
    assert receipt["run"]["inventory_input_digest"] == published["site_inventory"]["input_digest"]
    assert receipt["linked_page_refs"] == list(PAGES)
    assert receipt["problems"] == []
    assert receipt["evidence_ceiling"] == proof.EVIDENCE_CEILING
    assert set(receipt["file_digests"]) == {*proof.CANONICAL_FILES.values(), proof.CLI_RECEIPT}
    sync = next(call for call in host.calls if call[1:2] == ["sync"])
    assert sync[2] == "--locked"
    assert "--no-python-downloads" in sync


def test_the_real_locked_verifier_binds_the_origin_and_accepts_the_real_bundle(
    tmp_path: Path,
) -> None:
    """The proof over the repository's own checkout, with the verifier actually executed."""
    host = ScriptedHost(tmp_path, verifier=_real_verifier)
    facts: dict[str, Any] = {}
    _run(ROOT, host, facts, proof_dir=tmp_path / "proof")
    verification = facts["verification"]
    expected_origin = os.path.realpath(ROOT / "src" / "pxapi" / "__init__.py")
    assert verification["bound_to"] == TRACKED_ORIGIN
    assert verification["pxapi_origin"] == expected_origin
    assert verification["contract_root"] == os.path.realpath(CONTRACTS_DIR)
    assert verification["isolated"] is True and verification["safe_path"] is True
    assert verification["producer_violations"] == []
    assert facts["problems"] == []
    assert proof.build_receipt(facts, None)["verdict"] == "PASSED"


# --- isolation ----------------------------------------------------------------------------------


def test_every_python_runs_isolated_from_the_scratch_directory_with_a_clean_environment(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.14": (3, 14, 0), "3.13": (3, 13, 13)})
    facts: dict[str, Any] = {}
    proof.run_proof(
        root,
        root / proof.PROOF_DIR,
        facts,
        runner=host,
        environ={
            "PATH": host.search_path(),
            "PYTHONPATH": str(root),
            "PXAPI_CONTRACTS_DIR": str(tmp_path / "foreign-contracts"),
        },
        which=lambda _name: str(host.uv),
        executable=CONTROL,
        expected_sha=SHA,
        system_directories=_no_well_known,
    )
    workdir = Path(facts["isolation"]["working_directory"])
    pythons = [
        (call, cwd, env)
        for call, cwd, env in zip(host.calls, host.cwds, host.envs, strict=True)
        if call[0] not in ("git", str(host.uv))
    ]
    kinds = [call[1:3] for call, _cwd, _env in pythons]
    assert kinds == [["-I", "-c"], ["-I", "-c"], ["-I", "-c"], ["-I", "-m"], ["-I", "-c"]]
    for call, cwd, _env in pythons:
        assert call[1] == "-I"
        assert cwd == workdir
        assert not cwd.is_relative_to(root)
    for call, cwd in zip(host.calls, host.cwds, strict=True):
        if call[0] in ("git", str(host.uv)):
            assert cwd == root
    cli_env = next(env for call, env in zip(host.calls, host.envs, strict=True) if _is_cli(call))
    assert cli_env["SSL_CERT_FILE"] == str(host.trust_bundle)
    assert "PYTHONPATH" not in cli_env and "PXAPI_CONTRACTS_DIR" not in cli_env
    verifier_env = next(
        env for call, env in zip(host.calls, host.envs, strict=True) if _is_verifier(call)
    )
    assert verifier_env == cli_env


def _is_cli(call: list[str]) -> bool:
    return call[1:4] == ["-I", "-m", proof.CLI_MODULE]


def _is_verifier(call: list[str]) -> bool:
    return call[1:4] == ["-I", "-c", proof.CONTRACT_VERIFIER]


@pytest.mark.parametrize("shadow", ["pxapi", "pxapi.py", "pxapi.pyc"])
def test_an_untracked_checkout_root_pxapi_entry_fails_the_isolation_stage_before_any_run(
    tmp_path: Path, shadow: str
) -> None:
    root = _checkout(tmp_path)
    if shadow == "pxapi":
        (root / shadow).mkdir()
        (root / shadow / "__init__.py").write_text("raise SystemExit('shadow')\n")
    else:
        (root / shadow).write_text("raise SystemExit('shadow')\n")
    host = ScriptedHost(tmp_path)
    failure, facts = _failed(root, host)
    assert failure.stage == "isolation"
    assert shadow in failure.detail
    assert facts["isolation"]["checkout_root_shadowing_entries"] == [shadow]
    assert [call[0] for call in host.calls] == ["git", "git", "git"]
    receipt = proof.build_receipt(facts, failure)
    assert receipt["verdict"] == "FAILED"
    assert receipt["failure"]["stage"] == "isolation"


def test_an_untracked_entry_under_src_or_contracts_fails_the_isolation_stage(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    untracked = "?? src/pxapi/adapters/inbound/acquire_cli/__init__.py\n"
    host = ScriptedHost(tmp_path, untracked=untracked)
    failure, facts = _failed(root, host)
    assert failure.stage == "isolation"
    assert "untracked entries under src, contracts" in failure.detail
    assert facts["isolation"]["untracked_entries"] == [untracked.strip()]
    status = [call for call in host.calls if call[:2] == ["git", "status"]]
    assert status == [
        ["git", "status", "--porcelain", "--untracked-files=no"],
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "src", "contracts"],
    ]


def test_a_pxapi_imported_from_outside_the_locked_project_fails_the_isolation_stage(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    foreign = tmp_path / "elsewhere" / "pxapi" / "__init__.py"
    host = ScriptedHost(tmp_path, origin=foreign)
    failure, facts = _failed_after_the_cli(root, host)
    assert failure.stage == "isolation"
    assert "not the locked project" in failure.detail
    assert facts["verification"]["bound_to"] is None
    assert facts["verification"]["pxapi_origin"] == str(foreign)
    assert "problems" not in facts


def test_a_pxapi_installed_in_the_disposable_environment_is_bound(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    facts: dict[str, Any] = {}

    def installed(report: dict[str, Any]) -> None:
        environment = Path(report["executable"]).parent.parent
        report["pxapi_origin"] = str(
            environment / "lib" / "python3.14" / "site-packages" / "pxapi" / "__init__.py"
        )

    host = ScriptedHost(tmp_path, report_tamper=installed)
    _run(root, host, facts)
    assert facts["verification"]["bound_to"] == "locked disposable project environment"
    assert facts["problems"] == []


def test_a_runtime_that_was_not_isolated_fails_the_isolation_stage(tmp_path: Path) -> None:
    root = _checkout(tmp_path)

    def unisolated(report: dict[str, Any]) -> None:
        report["safe_path"] = False

    host = ScriptedHost(tmp_path, report_tamper=unisolated)
    failure, facts = _failed_after_the_cli(root, host)
    assert failure.stage == "isolation"
    assert facts["verification"]["safe_path"] is False


# --- contract and producer-invariant violations reported by the locked runtime ------------------


def test_a_schema_violation_reported_by_the_verifier_fails_the_contract_stage(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)

    def violated(report: dict[str, Any]) -> None:
        report["documents"]["site-inventory.json"]["violations"].append(
            {"index": 0, "pointer": "/schema_version", "keyword": "required"}
        )

    host = ScriptedHost(tmp_path, report_tamper=violated)
    failure, facts = _failed_after_the_cli(root, host)
    assert failure.stage == "contract"
    assert "1 contract or producer-invariant check(s) failed" in failure.detail
    assert facts["problems"] == [
        "site-inventory.json/0: violates site-inventory at /schema_version [required]"
    ]
    receipt = proof.build_receipt(facts, failure)
    assert receipt["verdict"] == "FAILED"
    assert receipt["pages"] == _bundle(host.envelope)[proof.CLI_RECEIPT]["pages"]


def test_a_producer_invariant_violation_reported_by_the_verifier_fails_the_contract_stage(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)

    def violated(report: dict[str, Any]) -> None:
        report["producer_violations"].append(
            {"pointer": "/page_acquisitions/1", "rule": "record_binds_manifest"}
        )

    host = ScriptedHost(tmp_path, report_tamper=violated)
    failure, facts = _failed_after_the_cli(root, host)
    assert failure.stage == "contract"
    assert facts["problems"] == ["page documents: /page_acquisitions/1 [record_binds_manifest]"]


def test_a_verifier_that_validated_nothing_fails_the_contract_stage(tmp_path: Path) -> None:
    root = _checkout(tmp_path)

    def silent(report: dict[str, Any]) -> None:
        report["documents"] = {}
        report["producer_violations"] = None

    host = ScriptedHost(tmp_path, report_tamper=silent)
    failure, facts = _failed_after_the_cli(root, host)
    assert failure.stage == "contract"
    assert facts["problems"][0] == "analysis-run-request.json: not validated"
    assert "page documents: the producer invariants were not applied" in facts["problems"]


def test_a_verifier_that_does_not_run_or_prints_no_report_fails_the_verification_stage(
    tmp_path: Path,
) -> None:
    def crashed(_argv: Sequence[str], _cwd: Path, _env: Mapping[str, str]) -> str:
        raise subprocess.SubprocessError("verifier crashed")

    # Each scenario is complete in its own parent: its own checkout root, host and proof
    # output, so the canonical artifacts the first command line publishes cannot make the
    # second scenario fail at publication instead of at verification.
    first = tmp_path / "crashed"
    first.mkdir()
    host = ScriptedHost(first, verifier=crashed)
    failure, _facts = _failed_after_the_cli(_checkout(first), host)
    assert failure.stage == "verification"

    def prose(_argv: Sequence[str], _cwd: Path, _env: Mapping[str, str]) -> str:
        return "Traceback (most recent call last):\n"

    second = tmp_path / "prose"
    second.mkdir()
    host = ScriptedHost(second, verifier=prose)
    failure, _facts = _failed_after_the_cli(_checkout(second), host)
    assert failure.stage == "verification"
    assert "printed no JSON" in failure.detail


def test_a_forged_bundle_published_by_the_command_line_fails_the_linkage_stage(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)

    def forged(bundle: dict[str, Any]) -> None:
        bundle[proof.CLI_RECEIPT]["document_digests"]["page_acquisitions"]["count"] = 4

    host = ScriptedHost(tmp_path, bundle_tamper=forged)
    failure, facts = _failed_after_the_cli(root, host)
    assert failure.stage == "linkage"
    assert facts["problems"] == [
        "receipt.json: document_digests does not describe the canonical documents"
    ]
    receipt = proof.build_receipt(facts, failure)
    assert receipt["verdict"] == "FAILED"
    assert receipt["failure"]["stage"] == "linkage"


def test_contract_problems_and_linkage_problems_are_both_recorded(tmp_path: Path) -> None:
    root = _checkout(tmp_path)

    def violated(report: dict[str, Any]) -> None:
        report["producer_violations"].append({"pointer": "/measurements/0", "rule": "x"})

    def forged(bundle: dict[str, Any]) -> None:
        bundle[proof.CLI_RECEIPT]["run_state"] = "FAILED"

    host = ScriptedHost(tmp_path, report_tamper=violated, bundle_tamper=forged)
    failure, facts = _failed_after_the_cli(root, host)
    assert failure.stage == "contract"
    assert facts["problems"] == [
        "page documents: /measurements/0 [x]",
        "receipt.json: run_state does not describe the canonical documents",
    ]


# --- interpreter selection ----------------------------------------------------------------------


def test_an_installed_3_14_is_preferred_over_an_installed_3_13(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.14": (3, 14, 1), "3.13": (3, 13, 13)})
    facts: dict[str, Any] = {}
    _run(root, host, facts)

    assert _finds(host) == [">=3.13,<3.15,==3.14.*"]
    assert facts["selected_python"]["path"] == str(host.python("3.14"))
    assert facts["selected_python"]["version"] == "3.14.1"
    (sync,) = _synced(host)
    assert sync[sync.index("--python") + 1] == str(host.python("3.14"))
    assert facts["project_runtime"]["version"] == "3.14.1"


def test_an_installed_3_13_is_the_automatic_fallback_when_3_14_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    monkeypatch.setattr(Path, "home", _forbidden)
    monkeypatch.setattr(os.path, "expanduser", _forbidden)
    facts: dict[str, Any] = {}
    _run(root, host, facts)
    receipt = json.loads(json.dumps(proof.build_receipt(facts, None)))

    assert receipt["verdict"] == "PASSED"
    assert _finds(host) == [">=3.13,<3.15,==3.14.*", ">=3.13,<3.15,==3.13.*"]
    assert receipt["python_candidates"] == [
        {
            "requested": "3.14",
            "request": ">=3.13,<3.15,==3.14.*",
            "search_path": _inherited_only(host.search_path()),
            "outcome": "not installed",
        },
        {
            "requested": "3.13",
            "request": ">=3.13,<3.15,==3.13.*",
            "search_path": _inherited_only(host.search_path()),
            "path": str(host.python("3.13")),
            "discovered_via": f"inherited PATH entry {host.python('3.13').parent}",
            "version": "3.13.13",
            "outcome": "selected",
        },
    ]
    assert receipt["selected_python"] == {
        "path": str(host.python("3.13")),
        "version": "3.13.13",
        "requires_python": ">=3.13,<3.15",
    }
    assert receipt["requires_python"] == ">=3.13,<3.15"
    assert receipt["project_runtime"]["version"] == "3.13.13"
    (sync,) = _synced(host)
    assert sync[sync.index("--python") + 1] == str(host.python("3.13"))
    assert receipt["pages"] == _bundle(host.envelope)[proof.CLI_RECEIPT]["pages"]
    assert receipt["evidence_ceiling"] == proof.EVIDENCE_CEILING


@pytest.mark.parametrize(
    ("requires", "installed", "outcome_3_14"),
    [
        # The 3.14 uv names reports another release: rejected, 3.13 taken.
        (">=3.13,<3.15", {"3.14": (3, 12, 9), "3.13": (3, 13, 13)}, "rejected: not Python 3.14"),
        # A checkout whose requires-python excludes 3.14 falls back to 3.13.
        (
            ">=3.13,<3.14",
            {"3.14": (3, 14, 0), "3.13": (3, 13, 13)},
            "rejected: does not satisfy >=3.13,<3.14",
        ),
    ],
    ids=["wrong-release", "outside-requires-python"],
)
def test_an_incompatible_3_14_falls_back_to_a_compatible_3_13(
    tmp_path: Path, requires: str, installed: dict[str, Sequence[int]], outcome_3_14: str
) -> None:
    root = _checkout(tmp_path, requires)
    host = ScriptedHost(tmp_path, installed)
    facts: dict[str, Any] = {}
    _run(root, host, facts)

    first, second = facts["python_candidates"]
    assert first["outcome"] == outcome_3_14
    assert second["outcome"] == "selected"
    assert facts["selected_python"]["path"] == str(host.python("3.13"))
    assert facts["requires_python"] == requires


def test_a_uv_managed_candidate_is_rejected(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(
        tmp_path,
        {"3.14": (3, 14, 0), "3.13": (3, 13, 13)},
        managed_dir=tmp_path / "python3.14",
    )
    host.python("3.14").parent.mkdir(parents=True)
    facts: dict[str, Any] = {}
    _run(root, host, facts)

    assert facts["python_candidates"][0]["outcome"] == "rejected: uv-managed Python"
    assert facts["selected_python"]["path"] == str(host.python("3.13"))
    assert not any(call[0] == str(host.python("3.14")) for call in host.calls)


@pytest.mark.parametrize(
    ("requires", "installed", "outcomes"),
    [
        (">=3.13,<3.15", {}, ["not installed", "not installed"]),
        (
            ">=3.13,<3.15",
            {"3.14": (3, 15, 0), "3.13": (3, 12, 9)},
            ["rejected: not Python 3.14", "rejected: not Python 3.13"],
        ),
        (
            ">=3.15",
            {"3.14": (3, 14, 0), "3.13": (3, 13, 13)},
            ["rejected: does not satisfy >=3.15", "rejected: does not satisfy >=3.15"],
        ),
    ],
    ids=["missing", "wrong-releases", "outside-requires-python"],
)
def test_no_compatible_installed_python_fails_the_bootstrap_before_any_sync(
    tmp_path: Path, requires: str, installed: dict[str, Sequence[int]], outcomes: list[str]
) -> None:
    root = _checkout(tmp_path, requires)
    host = ScriptedHost(tmp_path, installed)
    failure, facts = _failed(root, host)

    assert failure.stage == "bootstrap"
    assert "no installed system Python (3.14, 3.13) satisfies" in failure.detail
    assert [entry["outcome"] for entry in facts["python_candidates"]] == outcomes
    assert "selected_python" not in facts
    assert _synced(host) == []
    receipt = proof.build_receipt(facts, failure)
    assert receipt["verdict"] == "FAILED"
    assert receipt["failure"]["stage"] == "bootstrap"
    assert receipt["exact_sha"] == SHA
    assert receipt["requires_python"] == requires
    assert receipt["evidence_ceiling"] == proof.EVIDENCE_CEILING


def test_an_unsupported_requires_python_fails_the_bootstrap(tmp_path: Path) -> None:
    root = _checkout(tmp_path, "~=3.14")
    host = ScriptedHost(tmp_path)
    failure, _facts = _failed(root, host)
    assert failure.stage == "bootstrap"
    assert "unsupported" in failure.detail
    assert _finds(host) == []


def test_every_uv_call_is_locked_system_only_and_isolated(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    facts: dict[str, Any] = {}
    _run(root, host, facts)

    (sync,) = _synced(host)
    assert sync[2] == "--locked"
    assert sync[sync.index("--python-preference") + 1] == "only-system"
    assert "--no-python-downloads" in sync
    for call, env in zip(host.calls, host.envs, strict=True):
        if call[1:2] in (["python"], ["sync"]):
            assert env["UV_PYTHON_DOWNLOADS"] == "never"
            assert "VIRTUAL_ENV" not in env
            scratch = Path(env["UV_PROJECT_ENVIRONMENT"]).parent
            assert not scratch.is_relative_to(root)
            assert Path(env["UV_CACHE_DIR"]).parent == scratch
        if call[1:3] == ["python", "dir"]:
            assert call == proof.managed_dir_argv(host.uv)
            assert not proof.DISCOVERY_DROPPED & set(env)
        elif call[1:3] == ["python", "find"]:
            assert call[3:-1] == list(proof.SYSTEM_FIND)
            assert not proof.DISCOVERY_DROPPED & set(env)
        elif call[1:2] in (["python"], ["sync"]):
            assert env["UV_PYTHON_PREFERENCE"] == "only-system"
    assert facts["lock"]["unchanged"] is True


def test_the_discovery_argv_is_the_runner_proven_system_only_form() -> None:
    assert proof.SYSTEM_FIND == (
        "--no-config",
        "--no-project",
        "--system",
        "--no-managed-python",
        "--no-python-downloads",
    )
    assert proof.find_argv(Path("/opt/bin/uv"), ">=3.13,<3.15,==3.13.*") == [
        "/opt/bin/uv",
        "python",
        "find",
        "--no-config",
        "--no-project",
        "--system",
        "--no-managed-python",
        "--no-python-downloads",
        ">=3.13,<3.15,==3.13.*",
    ]
    assert proof.managed_dir_argv(Path("/opt/bin/uv")) == [
        "/opt/bin/uv",
        "python",
        "dir",
        "--no-config",
    ]
    assert "UV_PYTHON_INSTALL_DIR" in proof.DISCOVERY_DROPPED


@pytest.mark.parametrize(
    ("requires", "wanted", "python_request"),
    [
        (">=3.13,<3.15", (3, 14), ">=3.13,<3.15,==3.14.*"),
        (">=3.13,<3.15", (3, 13), ">=3.13,<3.15,==3.13.*"),
        (" >=3.13 , <3.15 ", (3, 13), ">=3.13,<3.15,==3.13.*"),
        (">=3.13,<3.14", (3, 14), ">=3.13,<3.14,==3.14.*"),
    ],
)
def test_the_discovery_request_intersects_requires_python_with_the_minor(
    requires: str, wanted: tuple[int, int], python_request: str
) -> None:
    assert proof.python_request(requires, wanted) == python_request


def test_discovery_ignores_host_uv_configuration_and_python_pins(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    (root / ".python-version").write_text("3.12\n")
    (root / "uv.toml").write_text('python-preference = "only-managed"\n')
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    environ = {
        "PATH": host.search_path(),
        "UV_PYTHON": "3.12",
        "UV_PYTHON_PREFERENCE": "only-managed",
        "UV_MANAGED_PYTHON": "1",
        "UV_NO_MANAGED_PYTHON": "0",
        "UV_CONFIG_FILE": str(root / "uv.toml"),
        "UV_PROJECT": str(root),
        # Would make every installed system Python look uv-managed.
        "UV_PYTHON_INSTALL_DIR": str(tmp_path),
    }
    facts: dict[str, Any] = {}
    proof.run_proof(
        root,
        root / proof.PROOF_DIR,
        facts,
        runner=host,
        environ=environ,
        which=lambda _name: str(host.uv),
        executable=CONTROL,
        expected_sha=SHA,
        system_directories=_no_well_known,
    )

    probes = [
        (call, env)
        for call, env in zip(host.calls, host.envs, strict=True)
        if call[1:3] == ["python", "dir"]
    ]
    assert [call for call, _env in probes] == [proof.managed_dir_argv(host.uv)]
    for _call, env in probes:
        assert not proof.DISCOVERY_DROPPED & set(env)
        assert env["UV_PYTHON_DOWNLOADS"] == "never"
    finds = [
        (call, env)
        for call, env in zip(host.calls, host.envs, strict=True)
        if call[1:3] == ["python", "find"]
    ]
    assert [call for call, _env in finds] == [
        proof.find_argv(host.uv, ">=3.13,<3.15,==3.14.*"),
        proof.find_argv(host.uv, ">=3.13,<3.15,==3.13.*"),
    ]
    for _call, env in finds:
        assert not proof.DISCOVERY_DROPPED & set(env)
        assert env["UV_PYTHON_DOWNLOADS"] == "never"
    assert facts["selected_python"]["path"] == str(host.python("3.13"))
    assert facts["selected_python"]["version"] == "3.13.13"


def test_a_lock_rewritten_by_the_sync_fails_the_bootstrap(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, lock_rewrite=(root / "uv.lock", b"version = 2\n"))
    failure, facts = _failed(root, host)
    assert failure.stage == "bootstrap"
    assert "uv.lock changed" in failure.detail
    assert facts["lock"]["unchanged"] is False
    assert facts["lock"]["sha256_before"] != facts["lock"]["sha256_after"]


@pytest.mark.parametrize(
    ("installed", "project_version", "detail"),
    [
        ({"3.14": (3, 14, 0)}, (3, 15, 0), "is outside >=3.13,<3.15"),
        ({"3.14": (3, 14, 0)}, (3, 12, 9), "is outside >=3.13,<3.15"),
        ({"3.14": (3, 14, 0)}, (3, 13, 13), "not the selected Python"),
        ({"3.13": (3, 13, 13)}, (3, 14, 0), "not the selected Python"),
    ],
)
def test_the_project_runtime_is_validated_against_requires_python(
    tmp_path: Path,
    installed: dict[str, Sequence[int]],
    project_version: Sequence[int],
    detail: str,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, installed, project_version=project_version)
    failure, facts = _failed(root, host)
    assert failure.stage == "runtime"
    assert detail in failure.detail
    expected = ".".join(str(part) for part in project_version)
    assert facts["project_runtime"]["version"] == expected


def test_a_project_runtime_on_another_patch_release_is_accepted(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 12)}, project_version=(3, 13, 13))
    facts: dict[str, Any] = {}
    _run(root, host, facts)
    assert facts["project_runtime"]["version"] == "3.13.13"
    assert facts["problems"] == []


# --- well-known system directories --------------------------------------------------------------

HOMEBREW_3_13 = Path("/opt/homebrew/opt/python@3.13/bin")
HOMEBREW_3_14 = Path("/opt/homebrew/opt/python@3.14/bin")
EMPTY_PROVENANCE: dict[str, list[str]] = {
    "inherited": [],
    "well_known": [],
    "added": [],
    "absent": [],
    "excluded": [],
    "already_present": [],
}


def _lay_out(host: ScriptedHost) -> None:
    """Create the installed interpreters' directories, so they can be well-known directories."""
    for path, _info in host.pythons.values():
        path.parent.mkdir(parents=True, exist_ok=True)


def _simulated_well_known(tmp_path: Path) -> WellKnown:
    """Well-known directories laid out like the scripted host's interpreters.

    ``<tmp>/python<minor>/bin`` plays Homebrew's minor-specific ``opt/python@<minor>/bin`` and
    ``<tmp>/usr/bin`` the generic system location; neither is on the sandbox ``PATH``.
    """

    def well_known(wanted: Sequence[int]) -> list[Path]:
        minor = ".".join(str(part) for part in wanted)
        return [tmp_path / f"python{minor}" / "bin", tmp_path / "usr" / "bin"]

    return well_known


def test_the_macos_well_known_directories_cover_homebrew_and_the_system_locations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", SCRATCH_HOME)
    monkeypatch.setattr(Path, "home", _forbidden)
    monkeypatch.setattr(os.path, "expanduser", _forbidden)

    for_3_13 = proof.system_python_directories((3, 13), "darwin")
    for_3_14 = proof.system_python_directories((3, 14), "darwin")

    assert for_3_13[0] == HOMEBREW_3_13
    assert for_3_14[0] == HOMEBREW_3_14
    assert Path("/usr/local/opt/python@3.14/bin") in for_3_14
    assert Path("/Library/Frameworks/Python.framework/Versions/3.14/bin") in for_3_14
    assert for_3_13[-4:] == [
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/opt/local/bin"),
        Path("/usr/bin"),
    ]
    assert for_3_13 == proof.system_python_directories((3, 13), "darwin")
    assert len(set(for_3_13)) == len(for_3_13)
    for directory in [*for_3_13, *for_3_14]:
        assert directory.is_absolute()
        assert not str(directory).startswith((SCRATCH_HOME, "/Users", "~"))
        assert not {".venv", ".python-version", ".local", ".agt-runner"} & set(directory.parts)


def test_the_other_platforms_name_fixed_system_locations_only() -> None:
    posix = [Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin")]
    assert proof.system_python_directories((3, 13), "linux") == posix
    assert proof.system_python_directories((3, 14), "freebsd14") == posix
    assert proof.system_python_directories((3, 14), "win32") == [
        Path("C:\\Program Files\\Python314"),
        Path("C:\\Python314"),
    ]
    assert proof.system_python_directories((3, 13)) == proof.system_python_directories(
        (3, 13), sys.platform
    )


def test_the_proof_uses_the_platform_well_known_directories_by_default() -> None:
    assert proof.run_proof.__kwdefaults__["system_directories"] is proof.system_python_directories
    assert proof.select_python.__defaults__ == (proof.system_python_directories, None)


def test_the_lookup_path_appends_existing_well_known_directories_once_in_order(
    tmp_path: Path,
) -> None:
    homebrew = tmp_path / "opt" / "homebrew" / "opt" / "python@3.14" / "bin"
    usr_local = tmp_path / "usr" / "local" / "bin"
    absent = tmp_path / "Library" / "Frameworks" / "Python.framework" / "Versions" / "3.14" / "bin"
    usr_bin = tmp_path / "usr" / "bin"
    for directory in (homebrew, usr_local, usr_bin):
        directory.mkdir(parents=True)
    inherited = [f"{usr_bin}{os.sep}", "/sandbox/bin"]

    search_path, provenance = proof.find_search_path(
        os.pathsep.join(inherited), [homebrew, usr_bin, absent, homebrew, usr_local], []
    )

    assert search_path == os.pathsep.join([*inherited, str(homebrew), str(usr_local)])
    assert provenance == {
        "inherited": inherited,
        "well_known": [str(homebrew), str(usr_bin), str(absent), str(usr_local)],
        "added": [str(homebrew), str(usr_local)],
        "absent": [str(absent)],
        "excluded": [],
        "already_present": [str(usr_bin)],
    }


def test_the_lookup_path_excludes_managed_and_project_environment_directories(
    tmp_path: Path,
) -> None:
    managed = tmp_path / "managed"
    managed_bin = managed / "cpython-3.14.0-macos-aarch64-none" / "bin"
    venv_bin = tmp_path / "scratch" / "venv" / "bin"
    system = tmp_path / "usr" / "bin"
    for directory in (managed_bin, venv_bin, system):
        directory.mkdir(parents=True)
    link = tmp_path / "opt" / "python@3.14"
    link.parent.mkdir()
    link.symlink_to(managed_bin.parent)
    excluded = [Path(os.path.realpath(managed)), Path(os.path.realpath(venv_bin.parent))]

    search_path, provenance = proof.find_search_path(
        "/sandbox/bin", [managed_bin, venv_bin, link / "bin", system], excluded
    )

    assert search_path == os.pathsep.join(["/sandbox/bin", str(system)])
    assert provenance["excluded"] == [str(managed_bin), str(venv_bin), str(link / "bin")]
    assert provenance["added"] == [str(system)]
    assert provenance["absent"] == []


def test_an_absent_inherited_path_yields_only_the_well_known_directories(tmp_path: Path) -> None:
    system = tmp_path / "usr" / "bin"
    system.mkdir(parents=True)
    missing = tmp_path / "missing"

    search_path, provenance = proof.find_search_path(None, [system, missing], [])

    assert search_path == str(system)
    assert provenance["inherited"] == []
    assert provenance["added"] == [str(system)]
    assert provenance["absent"] == [str(missing)]
    assert proof.find_search_path("", [], []) == ("", EMPTY_PROVENANCE)


def test_discovery_is_attributed_to_the_entry_that_names_the_interpreter(tmp_path: Path) -> None:
    cellar = tmp_path / "Cellar" / "python@3.13" / "3.13.13" / "bin"
    cellar.mkdir(parents=True)
    (cellar / "python3.13").write_text("")
    opt = tmp_path / "opt" / "python@3.13"
    opt.parent.mkdir()
    opt.symlink_to(cellar.parent)
    provenance = {"inherited": ["/usr/bin"], "added": [str(opt / "bin")]}

    well_known = f"well-known directory {opt / 'bin'}"
    assert proof.discovered_via(opt / "bin" / "python3.13", provenance) == well_known
    # uv may print the resolved interpreter; the link in the added directory still names it.
    assert proof.discovered_via(cellar / "python3.13", provenance) == well_known
    assert (
        proof.discovered_via(Path("/usr/bin/python3.13"), provenance)
        == "inherited PATH entry /usr/bin"
    )
    assert (
        proof.discovered_via(tmp_path / "elsewhere" / "python3.13", provenance)
        == "not attributable to a search-path entry"
    )


def test_a_path_that_hides_every_interpreter_is_augmented_for_each_lookup_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.14": (3, 14, 0), "3.13": (3, 13, 13)})
    _lay_out(host)
    usr_bin = tmp_path / "usr" / "bin"
    usr_bin.mkdir(parents=True)
    monkeypatch.setenv("HOME", SCRATCH_HOME)
    monkeypatch.setattr(Path, "home", _forbidden)
    monkeypatch.setattr(os.path, "expanduser", _forbidden)
    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path))
    receipt = json.loads(json.dumps(proof.build_receipt(facts, None)))

    assert receipt["verdict"] == "PASSED"
    homebrew_like = host.python("3.14").parent
    assert _find_paths(host) == [
        os.pathsep.join(["/sandbox/bin", str(homebrew_like), str(usr_bin)])
    ]
    assert receipt["python_candidates"] == [
        {
            "requested": "3.14",
            "request": ">=3.13,<3.15,==3.14.*",
            "search_path": {
                "inherited": ["/sandbox/bin"],
                "well_known": [str(homebrew_like), str(usr_bin)],
                "added": [str(homebrew_like), str(usr_bin)],
                "absent": [],
                "excluded": [],
                "already_present": [],
            },
            "path": str(host.python("3.14")),
            "discovered_via": f"well-known directory {homebrew_like}",
            "version": "3.14.0",
            "outcome": "selected",
        }
    ]
    assert receipt["selected_python"]["path"] == str(host.python("3.14"))
    # The interpreter uv named was still probed, and the sync still ran locked against it.
    assert [str(host.python("3.14")), "-I", "-c", proof.PROBE] in host.calls
    (sync,) = _synced(host)
    assert sync[2] == "--locked"
    assert sync[sync.index("--python") + 1] == str(host.python("3.14"))
    # Only the find lookups see the augmented PATH; every other command keeps the sandbox PATH.
    for call, env in zip(host.calls, host.envs, strict=True):
        if call[1:3] != ["python", "find"]:
            assert env["PATH"] == "/sandbox/bin"
    assert not any(SCRATCH_HOME in path for path in _find_paths(host))


def test_a_hidden_3_13_is_found_when_the_3_14_well_known_directory_is_absent(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    _lay_out(host)
    usr_bin = tmp_path / "usr" / "bin"
    usr_bin.mkdir(parents=True)
    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path))

    first, second = facts["python_candidates"]
    assert first["outcome"] == "not installed"
    assert first["search_path"]["absent"] == [str(tmp_path / "python3.14" / "bin")]
    assert first["search_path"]["added"] == [str(usr_bin)]
    assert "path" not in first
    homebrew_like = host.python("3.13").parent
    assert second["outcome"] == "selected"
    assert second["search_path"]["added"] == [str(homebrew_like), str(usr_bin)]
    assert second["search_path"]["absent"] == []
    assert second["discovered_via"] == f"well-known directory {homebrew_like}"
    paths = _find_paths(host)
    assert paths == [
        os.pathsep.join(["/sandbox/bin", str(usr_bin)]),
        os.pathsep.join(["/sandbox/bin", str(homebrew_like), str(usr_bin)]),
    ]
    assert facts["selected_python"] == {
        "path": str(host.python("3.13")),
        "version": "3.13.13",
        "requires_python": ">=3.13,<3.15",
    }
    (sync,) = _synced(host)
    assert sync[sync.index("--python") + 1] == str(host.python("3.13"))
    assert facts["project_runtime"]["version"] == "3.13.13"
    assert facts["problems"] == []


def test_a_well_known_directory_already_on_the_path_is_not_appended_twice(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    _lay_out(host)
    usr_bin = tmp_path / "usr" / "bin"
    usr_bin.mkdir(parents=True)
    homebrew_like = host.python("3.13").parent
    path = os.pathsep.join(["/sandbox/bin", str(homebrew_like)])
    facts: dict[str, Any] = {}
    _run(root, host, facts, path=path, well_known=_simulated_well_known(tmp_path))

    _first, second = facts["python_candidates"]
    assert second["search_path"]["already_present"] == [str(homebrew_like)]
    assert second["search_path"]["added"] == [str(usr_bin)]
    assert second["discovered_via"] == f"inherited PATH entry {homebrew_like}"
    assert _find_paths(host)[1] == os.pathsep.join([path, str(usr_bin)])
    assert facts["selected_python"]["path"] == str(host.python("3.13"))


def test_a_well_known_directory_under_the_managed_root_is_not_added(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(
        tmp_path,
        {"3.14": (3, 14, 0), "3.13": (3, 13, 13)},
        managed_dir=tmp_path / "python3.14",
    )
    _lay_out(host)
    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path))

    first, second = facts["python_candidates"]
    assert first["outcome"] == "not installed"
    assert first["search_path"]["excluded"] == [str(host.python("3.14").parent)]
    assert first["search_path"]["added"] == []
    assert "path" not in first
    assert not any(call[0] == str(host.python("3.14")) for call in host.calls)
    assert second["outcome"] == "selected"
    assert second["search_path"]["added"] == [str(host.python("3.13").parent)]
    assert facts["selected_python"]["path"] == str(host.python("3.13"))
    assert _find_paths(host)[0] == "/sandbox/bin"


def test_a_project_virtual_environment_is_never_added_as_a_well_known_directory(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    _lay_out(host)
    venv_bin = root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    simulated = _simulated_well_known(tmp_path)

    def well_known(wanted: Sequence[int]) -> list[Path]:
        return [venv_bin, *simulated(wanted)]

    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=well_known)

    for entry in facts["python_candidates"]:
        assert entry["search_path"]["well_known"][0] == str(venv_bin)
        assert entry["search_path"]["excluded"] == [str(venv_bin)]
    assert all(str(venv_bin) not in path.split(os.pathsep) for path in _find_paths(host))
    assert facts["selected_python"]["path"] == str(host.python("3.13"))


def test_a_named_interpreter_found_through_a_well_known_directory_is_still_checked(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.14": (3, 12, 9), "3.13": (3, 13, 13)})
    _lay_out(host)
    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path))

    first, second = facts["python_candidates"]
    assert first["discovered_via"] == f"well-known directory {host.python('3.14').parent}"
    assert first["outcome"] == "rejected: not Python 3.14"
    assert second["outcome"] == "selected"
    assert facts["selected_python"]["path"] == str(host.python("3.13"))


def test_no_interpreter_anywhere_fails_the_bootstrap_with_the_search_paths_recorded(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {})
    failure, facts = _failed(
        root, host, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path)
    )

    assert failure.stage == "bootstrap"
    assert "no installed system Python (3.14, 3.13) satisfies" in failure.detail
    for entry, minor in zip(facts["python_candidates"], ("3.14", "3.13"), strict=True):
        assert entry["outcome"] == "not installed"
        assert entry["search_path"]["inherited"] == ["/sandbox/bin"]
        assert entry["search_path"]["absent"] == [
            str(tmp_path / f"python{minor}" / "bin"),
            str(tmp_path / "usr" / "bin"),
        ]
        assert entry["search_path"]["added"] == []
    assert _find_paths(host) == ["/sandbox/bin", "/sandbox/bin"]
    receipt = proof.build_receipt(facts, failure)
    assert receipt["verdict"] == "FAILED"
    assert receipt["python_candidates"] == facts["python_candidates"]
