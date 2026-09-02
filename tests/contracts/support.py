"""Test-side harness for the PXAPI v1 contracts.

Everything here is test code. It loads the manifest under ``contracts/v1``, builds one
``referencing`` registry from every schema's ``$id`` and validates documents with the
Draft 2020-12 reference validator **without** a format checker — every constraint the
contracts rely on is an assertion keyword (``pattern``, ``const``, ``enum``, ``required``,
``if``/``then``), so the same document fails the same way on every run.

Nothing under ``src/`` imports this module or ``jsonschema``: A4 ships no runtime validator,
no port and no adapter. ``to_problem`` exists so the tests can prove that a ``problem``
document built from validator output stays sanitised; the templates it uses are the producer
rule published in ``contracts/README.md`` for the slice that will implement a real producer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = ROOT / "contracts" / "v1"
MANIFEST_PATH = CONTRACTS_DIR / "manifest.json"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "invalid"

CONTRACTS_VERSION = "1.0.0"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
ID_NAMESPACE = "urn:pxapi:schema:"

#: The eleven canonical contract names in the order of Confluence 39846055 §17.
CANONICAL_CONTRACT_NAMES: tuple[str, ...] = (
    "analysis-run-request",
    "measurement-record",
    "website-evidence",
    "business-context",
    "business-intent-set",
    "contextual-diagnosis",
    "scorecard",
    "product-diagnosis",
    "internal-analysis-record",
    "client-report-model",
    "delivery-record",
)

#: The four support contracts A4 is allowed to add.
SUPPORT_CONTRACT_NAMES: tuple[str, ...] = (
    "analysis-run-state",
    "stage-execution-record",
    "artifact-descriptor",
    "problem",
)

#: The problem codes that must be registered at contracts version 1.0.0.
REQUIRED_PROBLEM_CODES: tuple[str, ...] = (
    "CONTRACT_VALIDATION_FAILED",
    "CONTRACT_NOT_FOUND",
    "SCHEMA_VERSION_UNSUPPORTED",
    "ILLEGAL_RUN_TRANSITION",
)


class ContractNotFound(LookupError):
    """The named contract is not listed in the manifest."""

    code = "CONTRACT_NOT_FOUND"

    def __init__(self, name: str) -> None:
        super().__init__(f"contract not found: {name}")
        self.name = name


@dataclass(frozen=True, order=True)
class Violation:
    """One failed constraint: where (JSON pointer), which keyword, and the validator's text."""

    pointer: str
    keyword: str
    message: str


def _reject_non_json_constant(token: str) -> Any:
    """``NaN``/``Infinity`` are not JSON; a bound like ``maximum`` compares False against NaN."""
    raise ValueError(f"non-JSON constant in document: {token}")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_non_json_constant)


def manifest() -> dict[str, Any]:
    return load_json(MANIFEST_PATH)


def contract_entries() -> list[dict[str, Any]]:
    """Canonical followed by support entries, in manifest order."""
    data = manifest()
    return [*data["canonical"], *data["support"]]


def contract_entry(name: str) -> dict[str, Any]:
    for entry in contract_entries():
        if entry["name"] == name:
            return entry
    raise ContractNotFound(name)


def schema_id(name: str) -> str:
    return f"{ID_NAMESPACE}{name}:{CONTRACTS_VERSION}"


def schema_path(name: str) -> Path:
    if name == "common":
        return CONTRACTS_DIR / manifest()["shared_definitions"][0]["schema"]
    return CONTRACTS_DIR / contract_entry(name)["schema"]


def all_schema_paths() -> list[Path]:
    """Every schema file the manifest names: shared definitions first, then every contract."""
    data = manifest()
    paths = [CONTRACTS_DIR / shared["schema"] for shared in data["shared_definitions"]]
    paths.extend(CONTRACTS_DIR / entry["schema"] for entry in contract_entries())
    return paths


def example_paths(name: str) -> list[Path]:
    return [CONTRACTS_DIR / rel for rel in contract_entry(name)["examples"]]


def registry() -> Registry:
    resources = []
    for path in all_schema_paths():
        schema = load_json(path)
        resources.append(
            (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def validator_for(name: str) -> Draft202012Validator:
    """A validator for the contract ``name`` — resolved by name only.

    v1 has exactly one version per name, so a document with a wrong or missing
    ``schema_version`` is an ordinary ``const`` / ``required`` violation against that one
    schema. There is no second lookup keyed by version and therefore no second code path.
    """
    schema = load_json(schema_path(name))
    return Draft202012Validator(schema, registry=registry())


def validator_for_definition(definition: str) -> Draft202012Validator:
    """A validator for one entry of ``common.v1.json#/$defs``."""
    schema = {"$schema": DIALECT, "$ref": f"{schema_id('common')}#/$defs/{definition}"}
    return Draft202012Validator(schema, registry=registry())


def _pointer(parts: Any) -> str:
    return "".join(f"/{str(part).replace('~', '~0').replace('/', '~1')}" for part in parts)


def violations_of(validator: Draft202012Validator, document: Any) -> tuple[Violation, ...]:
    found = [
        Violation(_pointer(error.absolute_path), str(error.validator), error.message)
        for error in validator.iter_errors(document)
    ]
    return tuple(sorted(found))


def validate(name: str, document: Any) -> tuple[Violation, ...]:
    """All violations of ``document`` against contract ``name``, sorted for determinism."""
    return violations_of(validator_for(name), document)


def to_problem(name: str, found: tuple[Violation, ...]) -> dict[str, Any]:
    """Build a ``problem`` document from violations using fixed templates only.

    The validator's free-text ``message`` is never copied: ``detail`` and every
    ``errors[].message`` are rendered from ``(name, pointer, keyword)`` alone, which is what
    keeps tracebacks, paths and internal exception text out of the document by construction.
    """
    version_rejected = any(v.pointer == "/schema_version" and v.keyword == "const" for v in found)
    code = "SCHEMA_VERSION_UNSUPPORTED" if version_rejected else "CONTRACT_VALIDATION_FAILED"
    title = "Schema version unsupported" if version_rejected else "Contract validation failed"
    return {
        "schema_version": CONTRACTS_VERSION,
        "code": code,
        "title": title,
        "detail": f"Document does not satisfy contract '{name}' ({len(found)} violation(s)).",
        "errors": [
            {
                "pointer": v.pointer,
                "keyword": v.keyword,
                "message": f"Constraint '{v.keyword}' violated at '{v.pointer or '/'}'.",
            }
            for v in found
        ],
    }


def invalid_fixture_cases() -> list[tuple[str, str, Path, Path]]:
    """``(contract, case, document_path, expectation_path)`` for every invalid fixture.

    A case is ``fixtures/invalid/<contract>/<case>.json`` with a sidecar
    ``<case>.expect.json``; the sidecar is excluded from case discovery by suffix.
    """
    cases = []
    for contract_dir in sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir()):
        for document in sorted(contract_dir.glob("*.json")):
            if document.name.endswith(".expect.json"):
                continue
            expectation = document.with_name(f"{document.stem}.expect.json")
            cases.append((contract_dir.name, document.stem, document, expectation))
    return cases
