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

The output directory is one run's bundle and nothing else. It must not exist beforehand: it is
created atomically, every file in it is created exclusively, and an existing directory — even an
empty one — is refused rather than reused, so artifacts of two runs can never be mixed. The
read-back then requires the exact bundle this run emitted: every expected file present with
exactly the bytes written, no other entry, and every document bound to this one run.

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
#: A plural member (see :data:`CONTAINER_SHAPES`) is checked item by item and written as one
#: JSON array.
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

#: ``envelope member -> its top-level container``: ``dict`` is exactly one JSON object, ``list``
#: exactly one JSON array of objects. A member in any other shape is canonical output invalid.
CONTAINER_SHAPES: dict[str, type] = {
    "analysis_run_request": dict,
    "analysis_run_state": dict,
    "stage_executions": list,
    "site_inventory": dict,
    "sampling_manifest": dict,
    "page_acquisitions": list,
    "measurements": list,
    "website_evidence": list,
}
_CONTAINER_WORDING = {dict: "one JSON object", list: "a JSON array of objects"}

RECEIPT_FILE = "receipt.json"


def page_budget(text: str) -> int:
    """The declared selection budget: a whole number of at least one, written in ASCII digits."""
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        raise argparse.ArgumentTypeError("must be a whole number of at least 1")
    return int(text)


def has_container_shape(member: str, value: Any) -> bool:
    """Whether ``value`` has the top-level container :data:`CONTAINER_SHAPES` names for it."""
    if CONTAINER_SHAPES[member] is list:
        return isinstance(value, list) and all(isinstance(item, dict) for item in value)
    return isinstance(value, dict)


def container_problems(envelope: dict[str, Any]) -> list[str]:
    """One problem for every produced member whose top-level container has the wrong shape."""
    problems: list[str] = []
    for member, (_contract, file_name) in PRODUCED_DOCUMENTS.items():
        if member in envelope and not has_container_shape(member, envelope[member]):
            expected = _CONTAINER_WORDING[CONTAINER_SHAPES[member]]
            problems.append(f"{file_name}: container is not {expected}")
    return problems


def invalid_documents(registry: ContractRegistry, envelope: dict[str, Any]) -> list[str]:
    """Every member whose container has the wrong shape, then the contract name of every
    produced document that fails its contract.

    A member in the wrong container is reported by :func:`container_problems` and its items are
    not validated: a singleton wrapped in a list, or a plural member given as one object, is
    this service's own defect however valid the items inside it are.
    """
    failures = container_problems(envelope)
    for member, (contract, _file) in PRODUCED_DOCUMENTS.items():
        if member not in envelope or not has_container_shape(member, envelope[member]):
            continue
        value = envelope[member]
        documents = value if CONTAINER_SHAPES[member] is list else [value]
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


def expected_bundle(envelope: dict[str, Any]) -> dict[str, Any]:
    """``file name -> value`` for exactly the files this run publishes, receipt included."""
    bundle = {
        file_name: envelope[member]
        for member, (_contract, file_name) in PRODUCED_DOCUMENTS.items()
        if member in envelope
    }
    bundle[RECEIPT_FILE] = page_receipt(envelope)
    return bundle


def write_artifacts(directory: Path, envelope: dict[str, Any]) -> None:
    """Publish this run's bundle into a directory created for it, and only for it.

    ``mkdir`` without ``exist_ok`` is the atomic create: it raises ``FileExistsError`` for any
    existing entry, an empty directory included, so no earlier run's files can be merged with
    this one's. Each file is then created exclusively, never overwritten.
    """
    directory.mkdir(parents=True)
    for file_name, value in expected_bundle(envelope).items():
        with (directory / file_name).open("x", encoding="utf-8") as handle:
            handle.write(_serialise(value))


def read_back_problems(
    directory: Path, registry: ContractRegistry, envelope: dict[str, Any]
) -> list[str]:
    """Everything wrong with the bundle *as read back from disk*, or nothing.

    The bundle is checked against the one ``envelope`` it was written from: every expected file
    must be present with exactly the bytes this run wrote, and no other entry may exist. What
    was read must have its member's container shape, and is then re-validated against its
    contract, bound to this run, and re-checked against the acquisition producer invariants, so
    what a reader opens is what was checked. An unreadable or malformed file is reported, never
    raised.
    """
    expected = expected_bundle(envelope)
    try:
        present = sorted(entry.name for entry in directory.iterdir())
    except OSError as error:
        return [f"{directory.name}: output directory unreadable ({type(error).__name__})"]
    unexpected = [name for name in present if name not in expected]
    problems = [f"{name}: not part of this run's bundle" for name in unexpected]

    on_disk: dict[str, Any] = {}
    for file_name, value in expected.items():
        path = directory / file_name
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            problems.append(f"{file_name}: missing")
            continue
        except OSError as error:
            problems.append(f"{file_name}: unreadable ({type(error).__name__})")
            continue
        if raw != _serialise(value).encode("utf-8"):
            problems.append(f"{file_name}: differs from what this run wrote")
        try:
            on_disk[file_name] = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            problems.append(f"{file_name}: not valid JSON")

    loaded = {
        member: on_disk[file_name]
        for member, (_contract, file_name) in PRODUCED_DOCUMENTS.items()
        if file_name in on_disk
    }
    # The container shape is checked first; a misshapen member reaches no helper below.
    problems += container_problems(loaded)
    shaped = {member: v for member, v in loaded.items() if has_container_shape(member, v)}
    problems += invalid_documents(registry, shaped)
    problems += _binding_problems(shaped, envelope.get("analysis_run_state", {}).get("run_id"))

    if "page_acquisitions" in envelope:
        manifest = shaped.get("sampling_manifest")
        records = shaped.get("page_acquisitions", [])
        measurements = shaped.get("measurements", [])
        evidence = shaped.get("website_evidence", [])
        page_members = ("page_acquisitions", "measurements", "website_evidence")
        misshapen = any(member in loaded and member not in shaped for member in page_members)
        if isinstance(manifest, dict) and not misshapen:
            found = acquisition_violations(records, manifest, measurements, evidence)
            problems += [f"{v.pointer} [{v.rule}]" for v in found]
        else:
            problems.append("page documents: the producer invariants cannot be applied")

    if RECEIPT_FILE in on_disk:
        try:
            derived = page_receipt(loaded) if len(shaped) == len(loaded) else None
        except (AttributeError, KeyError, TypeError, ValueError):
            derived = None
        if on_disk[RECEIPT_FILE] != derived:
            problems.append(f"{RECEIPT_FILE}: does not summarise the documents beside it")
    return problems


def _binding_problems(loaded: dict[str, Any], run_id: Any) -> list[str]:
    """Every document read back that does not belong to this one run and its own bundle."""
    problems: list[str] = []
    for member, value in loaded.items():
        file_name = PRODUCED_DOCUMENTS[member][1]
        documents = value if isinstance(value, list) else [value]
        for index, document in enumerate(documents):
            if not isinstance(document, dict) or document.get("run_id") != run_id:
                problems.append(f"{file_name}/{index}: does not belong to run {run_id}")

    manifest = loaded.get("sampling_manifest")
    if isinstance(manifest, dict):
        inventory = loaded.get("site_inventory")
        if not (
            isinstance(inventory, dict)
            and manifest.get("inventory_ref") == inventory.get("inventory_id")
            and manifest.get("inventory_output_digest") == inventory.get("output_digest")
        ):
            problems.append("sampling-manifest.json: not bound to this bundle's site inventory")
    return problems


def _serialise(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _refuse_output_dir(directory: Path) -> int:
    sys.stderr.write(
        f"pxapi-acquire: output directory {directory} already exists; "
        "every run publishes into a fresh one and nothing is reused.\n"
    )
    return 2


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
        help=(
            "also write every document set, and a per-page receipt, into this directory; it "
            "must not exist yet and is created for this run alone"
        ),
    )
    arguments = parser.parse_args(argv)

    if refuse(arguments.url) is UrlRefusal.CREDENTIALS_PRESENT:
        # Refused before a request document exists, so the credential is never echoed.
        sys.stderr.write(
            "pxapi-acquire: a target carrying credentials in its authority is refused.\n"
        )
        return 2

    output_dir: Path | None = arguments.output_dir
    if output_dir is not None and output_dir.exists(follow_symlinks=False):
        # Refused before any request is made; the atomic create below is what guarantees it.
        return _refuse_output_dir(output_dir)

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

    if output_dir is not None:
        try:
            write_artifacts(output_dir, envelope)
        except FileExistsError:
            return _refuse_output_dir(output_dir)
        except OSError as error:
            # The output location failed, not the website; the target is never echoed.
            sys.stderr.write(
                f"pxapi-acquire: artifacts could not be written ({type(error).__name__}).\n"
            )
            return 3
        problems = read_back_problems(output_dir, registry, envelope)
        if problems:
            sys.stderr.write(f"pxapi-acquire: written artifacts failed read-back: {problems}\n")
            return 3

    _emit(envelope)
    # A run whose pages failed technically is still a correctly produced result, so the exit
    # status reports whether the command worked, never what the website is like.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
