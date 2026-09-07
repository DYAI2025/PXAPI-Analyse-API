"""Runtime validation against the versioned contract registry.

This is the one place in the running system that reads ``manifest.json`` and turns a document
into a verdict. It holds no contract shape of its own: every rule it applies comes out of the
schemas, so there is exactly one contract authority and this module is not a second one.

It is deliberately an **adapter**. Validation is an edge concern — the transport boundary
checks what arrives and what leaves — and putting it here keeps the Domain, the Ports, the
Application and the Config layers free of a validator entirely, which
``tests/contracts/test_dependency_isolation.py`` enforces by an allowlist naming this module.

``tests/contracts/support.py`` builds its harness on this class rather than restating it, so
the validation the tests exercise is byte-for-byte the validation the service performs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

#: The contract whose documents this module produces when validation fails.
PROBLEM_CONTRACT = "problem"


class ContractNotFound(LookupError):
    """The named contract is not registered in the manifest."""

    code = "CONTRACT_NOT_FOUND"

    def __init__(self, name: str) -> None:
        # The offending name stays on the exception for logs. It is deliberately NOT rendered
        # into any client-facing text; see `to_problem`.
        super().__init__("contract not found")
        self.name = name


@dataclass(frozen=True)
class Violation:
    """One failed constraint: where (JSON pointer), which keyword, and the validator's text.

    ``message`` is the validator's raw output. It is never copied into a ``problem`` document,
    and ordering is by ``(pointer, keyword)`` alone so the free text cannot influence a result.
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


def loads_json(text: str) -> Any:
    """Parse JSON text, refusing the non-JSON constants Python's decoder accepts by default.

    A validator cannot save a document containing ``NaN``: numeric keywords silently compare
    False against it, so the value would pass every bound it was checked against.
    """
    return json.loads(text, parse_constant=_reject_non_json_constant)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_non_json_constant)


def _pointer(parts: Any) -> str:
    return "".join(f"/{str(part).replace('~', '~0').replace('/', '~1')}" for part in parts)


def violations_of(validator: Draft202012Validator, document: Any) -> tuple[Violation, ...]:
    """Every violation, ordered by ``(pointer, keyword)`` so the free text cannot reorder it."""
    found = [
        Violation(_pointer(error.absolute_path), str(error.validator), error.message)
        for error in validator.iter_errors(document)
    ]
    return tuple(sorted(found, key=lambda violation: violation.key))


@dataclass(frozen=True)
class ContractRegistry:
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

    # --- bounds read out of the contracts, never duplicated --------------------------

    def max_problem_errors(self) -> int:
        """The bound on ``problem.errors``, read from the contract rather than duplicated here.

        Reading it from the schema is what makes the bound a single fact: drop ``maxItems``
        from the contract and this raises, so the producer cannot quietly become unbounded.
        """
        schema = load_json(self.schema_path(PROBLEM_CONTRACT))
        return int(schema["properties"]["errors"]["maxItems"])

    def max_single_line_text(self) -> int:
        """The bound on a ``single_line_text`` value, read from the shared definition.

        A collector needs this to decide whether an observed text is representable at all.
        Reading it here means the number lives in exactly one place — the contract — so a
        later version that widens the bound cannot leave a stale constant behind in a
        collector, still silently discarding values the contract would now accept.
        """
        schema = load_json(self.schema_path("common"))
        return int(schema["$defs"]["single_line_text"]["maxLength"])

    # --- the problem producer --------------------------------------------------------

    def problem(self, code: str, title: str, detail: str, run_id: str | None = None) -> dict:
        """A ``problem`` document for a non-validation failure, from caller-fixed templates.

        ``title`` and ``detail`` are the caller's fixed strings for its own code; nothing
        derived from untrusted input, an exception or a path is accepted here.
        """
        document: dict[str, Any] = {
            "schema_version": self.entry(PROBLEM_CONTRACT)["version"],
            "code": code,
            "title": title,
            "detail": detail,
            "errors": [],
        }
        if run_id is not None:
            document["run_id"] = run_id
        return document

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
        # A present unsupported version fails `const`; an absent one fails `required`.
        version_rejected = any(v.key == ("/schema_version", "const") for v in found)
        code = "SCHEMA_VERSION_UNSUPPORTED" if version_rejected else "CONTRACT_VALIDATION_FAILED"
        title = "Schema version unsupported" if version_rejected else "Contract validation failed"
        subject = (
            "declares a schema version not supported by" if version_rejected else "does not satisfy"
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
