"""Test-side harness for the PXAPI v1 contracts.

Everything here is test code. It reads a contract *registry* — ``manifest.json`` under a
contract root — and derives its whole inventory from that data: which contracts exist, what
each one is called, which version it is at, where its schema and examples live. The harness
holds no list of contract names and no contract count, so a slice that registers a new
contract is picked up without editing this module (``test_registry_evolution`` proves it).

Validation runs on the Draft 2020-12 reference validator against a ``referencing`` registry
built from every schema's ``$id``, **without** a format checker: every constraint the
contracts rely on is an assertion keyword (``pattern``, ``const``, ``enum``, ``required``,
``if``/``then``), so the same document fails the same way on every run and offline.

The registry reader, the validator and the ``problem`` producer are **not** defined here.
PXK-67 promoted them to ``pxapi.adapters.contracts.registry``, because the running service now
validates at its transport boundary and the validation the tests exercise must be the same code
the service executes, not a second implementation that can drift from it. This module imports
them and adds only what is test-only: the schema meta-rule walk and the invalid-fixture index.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from referencing import Registry

from pxapi.adapters.contracts.registry import (
    PROBLEM_CONTRACT,
    ContractNotFound,
    ContractRegistry,
    Violation,
    load_json,
    violations_of,
)

#: Re-exported so the test modules keep one import site for the harness surface.
__all__ = [
    "CONTRACTS",
    "CONTRACTS_DIR",
    "EXPECTATIONS_FILENAME",
    "FIXTURES_DIR",
    "PROBLEM_CONTRACT",
    "REQUIRED_ENTRY_MEMBERS",
    "REQUIRED_SHARED_MEMBERS",
    "ContractNotFound",
    "ContractRoot",
    "InvalidCase",
    "SchemaWalk",
    "Violation",
    "contract_entries",
    "contract_names",
    "declares_object",
    "invalid_fixture_cases",
    "is_nullable",
    "iter_patterns",
    "iter_refs",
    "load_json",
    "manifest",
    "to_problem",
    "validate",
    "violations_of",
]

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = ROOT / "contracts" / "v1"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "invalid"

#: The per-contract-directory expectation index for invalid fixtures. One file per contract
#: directory, never one sidecar per case.
EXPECTATIONS_FILENAME = "expectations.json"

#: Members every registry entry must carry. This is a *shape*, not an inventory: it says what
#: an entry looks like, never which or how many entries exist.
REQUIRED_ENTRY_MEMBERS: tuple[str, ...] = (
    "name",
    "id",
    "version",
    "role",
    "status",
    "owner_slice",
    "schema",
    "examples",
)

#: Members every shared-definition entry must carry.
REQUIRED_SHARED_MEMBERS: tuple[str, ...] = ("name", "id", "version", "schema")


class ContractRoot(ContractRegistry):
    """The runtime contract registry plus the test-only invalid-fixture index.

    Everything about reading the registry and validating a document is inherited, so the
    harness and the service cannot disagree about what a contract means. Only the fixture
    index below is test-only: invalid documents are proofs about the schemas and are
    deliberately not part of the published contract surface.
    """

    # --- invalid fixtures ------------------------------------------------------------

    def invalid_fixture_cases(self, fixtures_dir: Path) -> list[InvalidCase]:
        """Every ``(contract, case)`` under ``fixtures_dir``, paired with its expectation.

        A contract directory holds ``<case>.json`` documents plus one ``expectations.json``
        index; a case whose expectation is missing (or an expectation whose case is missing)
        is reported as such rather than skipped, so orphans cannot hide.
        """
        cases: list[InvalidCase] = []
        if not fixtures_dir.is_dir():
            return cases
        for contract_dir in sorted(p for p in fixtures_dir.iterdir() if p.is_dir()):
            index_path = contract_dir / EXPECTATIONS_FILENAME
            index = load_json(index_path) if index_path.is_file() else {}
            expectations = dict(index.get("cases", {}))
            documents = {
                path.stem: path
                for path in sorted(contract_dir.glob("*.json"))
                if path.name != EXPECTATIONS_FILENAME
            }
            for case in sorted(set(documents) | set(expectations)):
                cases.append(
                    InvalidCase(
                        contract=contract_dir.name,
                        case=case,
                        document_path=documents.get(case),
                        expectation=expectations.get(case),
                        index_path=index_path,
                    )
                )
        return cases


@dataclass(frozen=True)
class InvalidCase:
    """One targeted invalid document and the structural violation it is expected to produce.

    ``document_path`` is ``None`` for an expectation with no document, and ``expectation`` is
    ``None`` for a document with no expectation; the parity test asserts neither happens.
    """

    contract: str
    case: str
    document_path: Path | None
    expectation: dict[str, Any] | None
    index_path: Path

    @property
    def id(self) -> str:
        return f"{self.contract}/{self.case}"

    def expected_keys(self) -> set[tuple[str, str]]:
        expectation = self.expectation or {}
        return {(v["pointer"], v["keyword"]) for v in expectation.get("violations", [])}


# --- schema meta-rules, shared by the repository tests and the evolution proof -----------

#: Keywords whose subschemas constrain the SAME instance as the owning object, so a
#: ``properties`` / ``required`` inside them refers to the owner's members.
SAME_INSTANCE_APPLICATORS = ("allOf", "anyOf", "oneOf", "if", "then", "else", "not")


def declares_object(node: dict[str, Any]) -> bool:
    """``type: object`` or ``type: [object, null]`` — a node that owns its properties."""
    declared = node.get("type")
    return declared == "object" or (isinstance(declared, list) and "object" in declared)


def is_nullable(sub: dict[str, Any]) -> bool:
    declared = sub.get("type")
    if declared == "null" or (isinstance(declared, list) and "null" in declared):
        return True
    return any(
        branch.get("type") == "null"
        for key in ("anyOf", "oneOf")
        for branch in sub.get(key, [])
        if isinstance(branch, dict)
    )


def iter_refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            yield node["$ref"]
        for value in node.values():
            yield from iter_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_refs(value)


def iter_patterns(node: Any, path: str = "#") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        if isinstance(node.get("pattern"), str):
            yield path, node["pattern"]
        for key, value in node.items():
            yield from iter_patterns(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_patterns(value, f"{path}/{index}")


class SchemaWalk:
    """Walks one schema file, checking object closure and property categories.

    ``owner`` is the ``properties`` mapping of the nearest declaring object (``type: object``)
    whose instance the current subschema constrains. Inside a same-instance applicator
    (``if``/``then``/``allOf``/``not``…) a subschema may only name members of that owner; when
    it descends into ``properties/<member>`` there, the member's declared schema (resolved
    through ``$ref``) becomes the new owner, so nested conditional constraints are checked
    against real members.
    """

    def __init__(self, name: str, schema: dict[str, Any], registry: Registry) -> None:
        self.name = name
        self.schema = schema
        self.resolver = registry.resolver().lookup(schema["$id"]).resolver
        self.declaring_objects = 0
        self.conditionals = 0
        self.errors: list[str] = []

    def run(self) -> SchemaWalk:
        self._walk(self.schema, owner=None, in_applicator=False, path="#")
        return self

    def _declared_properties(self, sub: Any) -> dict[str, Any] | None:
        """The ``properties`` of the object a property schema declares, following ``$ref``."""
        if not isinstance(sub, dict):
            return None
        if isinstance(sub.get("$ref"), str):
            sub = self.resolver.lookup(sub["$ref"]).contents
        if isinstance(sub, dict) and declares_object(sub):
            return sub.get("properties", {})
        return None

    def _walk(
        self, node: Any, *, owner: dict[str, Any] | None, in_applicator: bool, path: str
    ) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                self._walk(item, owner=owner, in_applicator=in_applicator, path=f"{path}/{index}")
            return
        if not isinstance(node, dict):
            return

        if declares_object(node):
            owner = self._check_declaring_object(node, path)
            in_applicator = False
        elif "properties" in node or "required" in node:
            if not in_applicator or owner is None:
                self.errors.append(
                    f"{path}: names properties/required without being a declared object "
                    "or an applicator of one"
                )
            else:
                named = set(node.get("properties", {})) | set(node.get("required", []))
                if not named <= set(owner):
                    self.errors.append(
                        f"{path}: names members outside the owner: {sorted(named - set(owner))}"
                    )

        for key, value in node.items():
            child_path = f"{path}/{key}"
            if key == "properties":
                for member, sub in value.items():
                    member_path = f"{child_path}/{member}"
                    if in_applicator and owner is not None and member in owner:
                        # A constraint on an existing member: its declared object (if any)
                        # is the owner for anything the constraint names.
                        nested = self._declared_properties(owner[member])
                        self._walk(sub, owner=nested, in_applicator=True, path=member_path)
                    else:
                        self._walk(sub, owner=None, in_applicator=False, path=member_path)
            elif key == "$defs":
                for member, sub in value.items():
                    self._walk(sub, owner=None, in_applicator=False, path=f"{child_path}/{member}")
            elif key in ("items", "prefixItems", "contains"):
                self._walk(value, owner=None, in_applicator=False, path=child_path)
            elif key in SAME_INSTANCE_APPLICATORS:
                if key == "if":
                    self.conditionals += 1
                self._walk(value, owner=owner, in_applicator=True, path=child_path)

    def _check_declaring_object(self, node: dict[str, Any], path: str) -> dict[str, Any]:
        self.declaring_objects += 1
        properties: dict[str, Any] = node.get("properties", {})
        if properties and node.get("additionalProperties") is not False:
            self.errors.append(f"{path}: declares properties but is not closed")
        required = node.get("required", [])
        if not set(required) <= set(properties):
            undeclared = sorted(set(required) - set(properties))
            self.errors.append(f"{path}: requires undeclared members {undeclared}")
        conditionally_required = self._conditionally_required(node)
        for member, sub in properties.items():
            member_path = f"{path}/properties/{member}"
            nullable = is_nullable(sub)
            description = sub.get("description", "")
            if member in required:
                expected = "Required, nullable." if nullable else "Required."
            elif nullable:
                self.errors.append(f"{member_path}: optional AND nullable — pick one category")
                continue
            elif member in conditionally_required:
                expected = "Conditional."
            else:
                expected = "Optional."
            if not description.startswith(expected):
                self.errors.append(f"{member_path}: description must start with {expected!r}")
        return properties

    @staticmethod
    def _conditionally_required(node: dict[str, Any]) -> set[str]:
        found: set[str] = set()

        def collect(sub: Any) -> None:
            if isinstance(sub, dict):
                found.update(sub.get("required", []))
                for key, value in sub.items():
                    if key in SAME_INSTANCE_APPLICATORS:
                        collect(value)
            elif isinstance(sub, list):
                for item in sub:
                    collect(item)

        for key in SAME_INSTANCE_APPLICATORS:
            if key in node:
                collect(node[key])
        return found


# --- the repository's own contract root --------------------------------------------------

CONTRACTS = ContractRoot(CONTRACTS_DIR)


@lru_cache(maxsize=1)
def _repo_cases() -> tuple[InvalidCase, ...]:
    return tuple(CONTRACTS.invalid_fixture_cases(FIXTURES_DIR))


def contract_entries() -> list[dict[str, Any]]:
    return CONTRACTS.entries()


def contract_names() -> list[str]:
    return CONTRACTS.names()


def manifest() -> dict[str, Any]:
    return CONTRACTS.manifest()


def validate(name: str, document: Any) -> tuple[Violation, ...]:
    return CONTRACTS.validate(name, document)


def to_problem(name: str, found: tuple[Violation, ...]) -> dict[str, Any]:
    return CONTRACTS.to_problem(name, found)


def invalid_fixture_cases() -> list[InvalidCase]:
    return list(_repo_cases())
