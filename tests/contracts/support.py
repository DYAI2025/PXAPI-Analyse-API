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

Nothing under ``src/`` imports this module, ``jsonschema`` or ``referencing``; PXK-59 ships
no runtime validator, no port and no adapter (``test_dependency_isolation`` proves it).
``to_problem`` exists so the tests can prove that a ``problem`` document built from validator
output stays sanitised; the templates it uses are the producer rule published in
``contracts/README.md`` for the slice that will implement a real producer.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

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

#: The one contract the harness itself produces documents for. This names the producer helper
#: below, not an inventory of the registry: `to_problem` has to know which contract its own
#: output must validate against.
PROBLEM_CONTRACT = "problem"


class ContractNotFound(LookupError):
    """The named contract is not registered in the manifest."""

    code = "CONTRACT_NOT_FOUND"

    def __init__(self, name: str) -> None:
        # The offending name stays on the exception for tests and logs. It is deliberately
        # NOT rendered into any client-facing text; see `to_problem`.
        super().__init__("contract not found")
        self.name = name


@dataclass(frozen=True)
class Violation:
    """One failed constraint: where (JSON pointer), which keyword, and the validator's text.

    ``message`` is the validator's raw output. It is kept here so tests can feed hostile text
    through the producer, and it is never copied into a ``problem`` document; ordering below
    is by ``(pointer, keyword)`` alone so the free text cannot influence the result either.
    """

    pointer: str
    keyword: str
    message: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.pointer, self.keyword)


def _reject_non_json_constant(token: str) -> Any:
    """``NaN``/``Infinity`` are not JSON; a bound like ``maximum`` compares False against NaN."""
    raise ValueError(f"non-JSON constant in document: {token}")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_non_json_constant)


def _pointer(parts: Any) -> str:
    return "".join(f"/{str(part).replace('~', '~0').replace('/', '~1')}" for part in parts)


@dataclass(frozen=True)
class ContractRoot:
    """One contract root directory: a ``manifest.json`` plus the files it names.

    Every accessor derives from the manifest, so the same code runs against the repository's
    ``contracts/v1`` and against a throwaway root built in a pytest ``tmp_path``.
    """

    path: Path

    # --- registry data ---------------------------------------------------------------

    @property
    def manifest_path(self) -> Path:
        return self.path / "manifest.json"

    def manifest(self) -> dict[str, Any]:
        return load_json(self.manifest_path)

    def registry_meta(self) -> dict[str, Any]:
        return self.manifest()["registry"]

    def dialect(self) -> str:
        return self.registry_meta()["dialect"]

    def id_namespace(self) -> str:
        return self.registry_meta()["id_namespace"]

    def roles(self) -> tuple[str, ...]:
        """The role vocabulary the registry declares — data, so a later slice may extend it."""
        return tuple(self.registry_meta()["roles"])

    def statuses(self) -> tuple[str, ...]:
        return tuple(self.registry_meta()["statuses"])

    def entries(self) -> list[dict[str, Any]]:
        """Every registered contract, in manifest order. The only source of the inventory."""
        return list(self.manifest()["contracts"])

    def names(self) -> list[str]:
        return [entry["name"] for entry in self.entries()]

    def has_contract(self, name: str) -> bool:
        return any(entry["name"] == name for entry in self.entries())

    def entry(self, name: str) -> dict[str, Any]:
        for entry in self.entries():
            if entry["name"] == name:
                return entry
        raise ContractNotFound(name)

    def shared_definitions(self) -> list[dict[str, Any]]:
        return list(self.manifest()["shared_definitions"])

    def problem_codes(self) -> list[dict[str, Any]]:
        return list(self.manifest()["problem_codes"])

    # --- files -----------------------------------------------------------------------

    def schema_path(self, name: str) -> Path:
        for shared in self.shared_definitions():
            if shared["name"] == name:
                return self.path / shared["schema"]
        return self.path / self.entry(name)["schema"]

    def all_schema_paths(self) -> list[Path]:
        """Every schema file the manifest names: shared definitions first, then contracts."""
        paths = [self.path / shared["schema"] for shared in self.shared_definitions()]
        paths.extend(self.path / entry["schema"] for entry in self.entries())
        return paths

    def example_paths(self, name: str) -> list[Path]:
        return [self.path / rel for rel in self.entry(name)["examples"]]

    def expected_schema_id(self, name: str, version: str) -> str:
        return f"{self.id_namespace()}{name}:{version}"

    # --- validation ------------------------------------------------------------------

    def jsonschema_registry(self) -> Registry:
        """One offline registry keyed by each schema's own ``$id``. No network lookups."""
        resources = []
        for path in self.all_schema_paths():
            schema = load_json(path)
            resources.append(
                (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012))
            )
        return Registry().with_resources(resources)

    def validator_for(self, name: str) -> Draft202012Validator:
        """A validator for the contract ``name`` — resolved by name only.

        Each contract pins its own version with a ``const`` on ``schema_version``, so a
        document with a wrong or missing version is an ordinary ``const`` / ``required``
        violation against that one schema. There is no second lookup keyed by version and
        therefore no second code path.
        """
        return Draft202012Validator(
            load_json(self.schema_path(name)), registry=self.jsonschema_registry()
        )

    def validator_for_definition(
        self, definition: str, shared: str = "common"
    ) -> Draft202012Validator:
        """A validator for one entry of a shared definition file's ``$defs``."""
        entry = next(s for s in self.shared_definitions() if s["name"] == shared)
        schema = {"$schema": self.dialect(), "$ref": f"{entry['id']}#/$defs/{definition}"}
        return Draft202012Validator(schema, registry=self.jsonschema_registry())

    def validate(self, name: str, document: Any) -> tuple[Violation, ...]:
        """All violations of ``document`` against contract ``name``, deterministically ordered."""
        return violations_of(self.validator_for(name), document)

    # --- the problem producer --------------------------------------------------------

    def max_problem_errors(self) -> int:
        """The bound on ``problem.errors``, read from the contract rather than duplicated here.

        Reading it from the schema is what makes the bound a single fact: drop ``maxItems``
        from the contract and this raises, so the producer cannot quietly become unbounded.
        """
        schema = load_json(self.schema_path(PROBLEM_CONTRACT))
        return int(schema["properties"]["errors"]["maxItems"])

    def to_problem(self, name: str, found: tuple[Violation, ...]) -> dict[str, Any]:
        """Build a ``problem`` document from violations using fixed templates only.

        Three rules make the output safe by construction, not by filtering:

        * the validator's free-text ``message`` is never read here;
        * the contract name is echoed only after the registry resolved it, and the echoed
          string is the manifest's own value — an unregistered name is reported as
          ``CONTRACT_NOT_FOUND`` and never appears in the document;
        * ``errors`` is truncated to the contract's own bound, and the untruncated count is
          reported as a number.
        """
        problem_version = self.entry(PROBLEM_CONTRACT)["version"]
        total = len(found)

        if not self.has_contract(name):
            return {
                "schema_version": problem_version,
                "code": "CONTRACT_NOT_FOUND",
                "title": "Contract not found",
                "detail": "The requested contract is not registered in this contract registry.",
                "errors": [],
            }

        safe_name = self.entry(name)["name"]
        reported = sorted(found, key=lambda violation: violation.key)[: self.max_problem_errors()]
        version_rejected = any(v.key == ("/schema_version", "const") for v in found)
        code = "SCHEMA_VERSION_UNSUPPORTED" if version_rejected else "CONTRACT_VALIDATION_FAILED"
        title = "Schema version unsupported" if version_rejected else "Contract validation failed"
        subject = (
            "does not declare a supported schema version of"
            if version_rejected
            else "does not satisfy"
        )
        return {
            "schema_version": problem_version,
            "code": code,
            "title": title,
            "detail": (
                f"Document {subject} contract '{safe_name}': "
                f"{total} violation(s), {len(reported)} reported."
            ),
            "errors": [{"pointer": v.pointer, "keyword": v.keyword} for v in reported],
        }

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


def violations_of(validator: Draft202012Validator, document: Any) -> tuple[Violation, ...]:
    """Every violation, ordered by ``(pointer, keyword)`` so the free text cannot reorder it."""
    found = [
        Violation(_pointer(error.absolute_path), str(error.validator), error.message)
        for error in validator.iter_errors(document)
    ]
    return tuple(sorted(found, key=lambda violation: violation.key))


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
