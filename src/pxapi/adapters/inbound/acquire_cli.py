"""The operator entry point for multi-page acquisition: one URL and an explicit page budget in.

It exists so a bounded multi-page acquisition can be run and read back without standing up a
server, which is what the PXAPI-20 Real-Boundary gate needs. It drives the production
composition under the same strict target policy as every other entry point.

``--max-selected-pages N`` is **required** and has no default (D-20-A). It is the sampling
manifest's declared selection budget and nothing else: every page the resulting manifest selects
is attempted exactly once, and no second truncation exists anywhere between the manifest and the
acquisition records.

Every document the run produced is validated against the contract registry before anything is
printed or written; a document this service built that fails its own contract is withheld and
reported as ``CANONICAL_OUTPUT_INVALID``, which names a defect in this service and never the
website. With ``--output-dir`` each canonical document set is also written as a file, read back
from disk, re-validated and re-checked against the producer invariants, and summarised as a
per-page ``receipt.json`` that follows the evidence chain the contracts define.

Run it as ``python -m pxapi.adapters.inbound.acquire_cli <url> --max-selected-pages N``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pxapi.adapters.composition import build_site_acquisition, default_registry
from pxapi.adapters.contracts.registry import ContractRegistry
from pxapi.adapters.inbound.cli import REQUEST_CONTRACT, build_request
from pxapi.domain.acquisition_digests import digest_of
from pxapi.domain.page_acquisition import acquisition_violations
from pxapi.domain.sampling_policy import SelectionBudgets
from pxapi.domain.site_identity import UrlRefusal, refuse

#: ``envelope member -> (the contract every document under it must satisfy, artifact file)``.
#: A list member is checked item by item and written as one JSON array.
PRODUCED_DOCUMENTS: dict[str, tuple[str, str]] = {
    "analysis_run_request": ("analysis-run-request", "analysis-run-request.json"),
    "analysis_run_state": ("analysis-run-state", "analysis-run-state.json"),
    "stage_executions": ("stage-execution-record", "stage-execution-records.json"),
    "site_inventory": ("site-inventory", "site-inventory.json"),
    "sampling_manifest": ("sampling-manifest", "sampling-manifest.json"),
    "page_acquisitions": ("page-acquisition-record", "page-acquisition-records.json"),
    "measurements": ("measurement-record", "measurement-records.json"),
    "website_evidence": ("website-evidence", "website-evidence.json"),
}

RECEIPT_FILE = "receipt.json"


def page_budget(text: str) -> int:
    """The declared selection budget: a whole number of at least one, written in ASCII digits."""
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        raise argparse.ArgumentTypeError("must be a whole number of at least 1")
    return int(text)


def invalid_documents(registry: ContractRegistry, envelope: dict[str, Any]) -> list[str]:
    """The contract name of every produced document that fails its contract."""
    failures: list[str] = []
    for member, (contract, _file) in PRODUCED_DOCUMENTS.items():
        if member not in envelope:
            continue
        value = envelope[member]
        documents = value if isinstance(value, list) else [value]
        failures += [contract for document in documents if registry.validate(contract, document)]
    return failures


def page_receipt(envelope: dict[str, Any]) -> dict[str, Any]:
    """A human-inspectable summary of one run, read off the canonical documents alone.

    Each page row is found by following the contracts' own chain in the reading direction a
    consumer uses — evidence to measurement to the one acquisition record naming it — so the
    receipt shows the linkage rather than restating it. Nothing here is a judgement: outcomes,
    statuses and ``not_assessed_reason`` tokens are copied, never interpreted.
    """
    state = envelope.get("analysis_run_state", {})
    receipt: dict[str, Any] = {
        "run_id": state.get("run_id"),
        "run_state": state.get("state"),
    }
    if "failure" in state:
        receipt["failure_code"] = state["failure"].get("code")

    inventory = envelope.get("site_inventory")
    if isinstance(inventory, dict):
        receipt["site_inventory"] = {
            "inventory_id": inventory.get("inventory_id"),
            "target_origin": inventory.get("target_origin"),
            "candidate_count": len(inventory.get("candidates", [])),
            "input_digest": inventory.get("input_digest"),
            "output_digest": inventory.get("output_digest"),
        }

    manifest = envelope.get("sampling_manifest")
    if isinstance(manifest, dict):
        receipt["sampling_manifest"] = {
            "sampling_manifest_id": manifest.get("sampling_manifest_id"),
            "inventory_ref": manifest.get("inventory_ref"),
            "inventory_output_digest": manifest.get("inventory_output_digest"),
            "budgets": manifest.get("budgets"),
            "mode": manifest.get("mode"),
            "selection_complete": manifest.get("selection_complete"),
            "incompleteness": manifest.get("incompleteness"),
            "selected_count": len(manifest.get("selections", [])),
            "exclusions": manifest.get("exclusions"),
            "input_digest": manifest.get("input_digest"),
            "output_digest": manifest.get("output_digest"),
        }

    receipt["document_digests"] = {
        member: {"count": len(envelope[member]), "digest": digest_of(envelope[member])}
        for member in ("page_acquisitions", "measurements", "website_evidence")
        if member in envelope
    }

    ranks = {
        selection.get("url_key"): selection.get("selection_rank")
        for selection in (manifest or {}).get("selections", [])
        if isinstance(selection, dict)
    }
    measurements = {m["measurement_id"]: m for m in envelope.get("measurements", [])}
    evidence_for: dict[str, list[str]] = {}
    for item in envelope.get("website_evidence", []):
        for ref in item.get("measurement_refs", []):
            evidence_for.setdefault(ref, []).append(item["evidence_id"])

    rows: list[dict[str, Any]] = []
    for record in envelope.get("page_acquisitions", []):
        refs = record.get("measurement_refs", [])
        reasons = sorted(
            {
                measurements[ref]["assessment"]["not_assessed_reason"]
                for ref in refs
                if ref in measurements and "not_assessed_reason" in measurements[ref]["assessment"]
            }
        )
        rows.append(
            {
                "selection_rank": ranks.get(record.get("url_key")),
                "url_key": record.get("url_key"),
                "acquisition_id": record.get("acquisition_id"),
                "acquisition_outcome": record.get("acquisition_outcome"),
                "http_status": record.get("http_status"),
                "final_url_key": record.get("final_url_key"),
                "redirect_count": record.get("redirect_count"),
                "body_truncated": record.get("body_truncated"),
                "body_decoded": record.get("body_decoded"),
                "body_digest": record.get("body_digest"),
                "measurement_refs": list(refs),
                "evidence_refs": [e for ref in refs for e in evidence_for.get(ref, [])],
                "not_assessed_reasons": reasons,
                "measurements_withheld_reason": record.get("measurements_withheld_reason"),
            }
        )
    receipt["pages"] = rows
    return receipt


def write_artifacts(directory: Path, envelope: dict[str, Any]) -> None:
    """Every produced document set as one readable JSON file, and the receipt beside them."""
    directory.mkdir(parents=True, exist_ok=True)
    for member, (_contract, file_name) in PRODUCED_DOCUMENTS.items():
        if member in envelope:
            _write_json(directory / file_name, envelope[member])
    _write_json(directory / RECEIPT_FILE, page_receipt(envelope))


def read_back_problems(directory: Path, registry: ContractRegistry) -> list[str]:
    """Everything wrong with the artifacts *as read back from disk*, or nothing.

    Re-validates every document against its contract and re-applies the acquisition producer
    invariants to the set, so what a reader opens is what was checked — not merely what was
    held in memory before it was written.
    """
    loaded: dict[str, Any] = {}
    for member, (_contract, file_name) in PRODUCED_DOCUMENTS.items():
        path = directory / file_name
        if path.is_file():
            loaded[member] = json.loads(path.read_text(encoding="utf-8"))
    problems = invalid_documents(registry, loaded)
    if "page_acquisitions" in loaded:
        found = acquisition_violations(
            loaded["page_acquisitions"],
            loaded.get("sampling_manifest", {}),
            loaded.get("measurements", []),
            loaded.get("website_evidence", []),
        )
        problems += [f"{v.pointer} [{v.rule}]" for v in found]
    return problems


def _write_json(path: Path, value: Any) -> None:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def _emit(value: Any) -> None:
    json.dump(value, sys.stdout, indent=2)
    sys.stdout.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pxapi-acquire",
        description=(
            "Discover one public site, select at most N pages, and acquire every selected page "
            "over static HTTP into page-scoped canonical documents."
        ),
    )
    parser.add_argument("url", help="an absolute public http(s) URL")
    parser.add_argument(
        "--max-selected-pages",
        type=page_budget,
        required=True,
        metavar="N",
        help="the declared selection budget; required, no default",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="also write every document set, and a per-page receipt, into this directory",
    )
    arguments = parser.parse_args(argv)

    if refuse(arguments.url) is UrlRefusal.CREDENTIALS_PRESENT:
        # Refused before a request document exists, so the credential is never echoed.
        sys.stderr.write(
            "pxapi-acquire: a target carrying credentials in its authority is refused.\n"
        )
        return 2

    registry = default_registry()
    request = build_request(arguments.url)
    found = registry.validate(REQUEST_CONTRACT, request)
    if found:
        _emit(registry.to_problem(REQUEST_CONTRACT, found))
        return 2

    budgets = SelectionBudgets(max_selected_pages=arguments.max_selected_pages)
    envelope = build_site_acquisition(budgets, registry).run(request)
    if invalid_documents(registry, envelope):
        _emit(
            registry.problem(
                "CANONICAL_OUTPUT_INVALID",
                "Canonical output invalid",
                "A document this service produced does not satisfy its contract and was withheld.",
                run_id=request["run_id"],
            )
        )
        return 3

    if arguments.output_dir is not None:
        write_artifacts(arguments.output_dir, envelope)
        problems = read_back_problems(arguments.output_dir, registry)
        if problems:
            sys.stderr.write(f"pxapi-acquire: written artifacts failed read-back: {problems}\n")
            return 3

    _emit(envelope)
    # A run whose pages failed technically is still a correctly produced result, so the exit
    # status reports whether the command worked, never what the website is like.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
