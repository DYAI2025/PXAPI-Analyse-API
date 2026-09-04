"""Registering a new contract is additive: the harness picks it up with no code change.

This is the durable proof that the inventory lives in the registry and nowhere else. The test
builds a throwaway contract root in ``tmp_path`` holding the repository's real shared
definitions and Problem contract plus one synthetic second contract — registry entry, schema
and valid example — and then runs the *same* harness against it.

Nothing in ``support.py`` or in any other test module mentions the synthetic contract; the
last test in this file asserts that mechanically, so the proof cannot rot into a special case.

The complement matters as much as the property: this file deliberately contains no test that
the repository registry holds a particular set or number of contracts. Such a test would make
the next slice's additive change red, which is exactly the failure this file exists to prevent.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.contracts import support
from tests.contracts.support import (
    CONTRACTS,
    ContractRoot,
    SchemaWalk,
    load_json,
)

#: A name no PXAPI slice will ever register, so its presence anywhere in the harness would be
#: a hard-coded special case rather than data-driven discovery.
SYNTHETIC = "harness-evolution-probe"
SYNTHETIC_VERSION = "3.7.1"

HARNESS_DIR = Path(support.__file__).resolve().parent


def _synthetic_schema(namespace: str, dialect: str, common_id: str) -> dict:
    return {
        "$schema": dialect,
        "$id": f"{namespace}{SYNTHETIC}:{SYNTHETIC_VERSION}",
        "title": "Harness evolution probe",
        "description": "A synthetic contract used only to prove additive registry evolution.",
        "type": "object",
        "properties": {
            "schema_version": {
                "type": "string",
                "const": SYNTHETIC_VERSION,
                "description": f"Required. Always {SYNTHETIC_VERSION} for this contract.",
            },
            "probe_id": {
                "$ref": f"{common_id}#/$defs/id",
                "description": "Required. An opaque identifier for the probe.",
            },
            "label": {
                "$ref": f"{common_id}#/$defs/single_line_label",
                "description": "Optional. A single-line label for the probe.",
            },
        },
        "required": ["schema_version", "probe_id"],
        "additionalProperties": False,
    }


@pytest.fixture
def evolved_root(tmp_path: Path) -> ContractRoot:
    """The repository's contract root, copied, plus one additionally registered contract."""
    root = tmp_path / "v1"
    shutil.copytree(CONTRACTS.path, root)

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    namespace = manifest["registry"]["id_namespace"]
    dialect = manifest["registry"]["dialect"]
    common = next(s for s in manifest["shared_definitions"] if s["name"] == "common")

    schema = _synthetic_schema(namespace, dialect, common["id"])
    (root / "schemas" / f"{SYNTHETIC}.v1.json").write_text(
        json.dumps(schema, indent=2) + "\n", encoding="utf-8"
    )
    example = {"schema_version": SYNTHETIC_VERSION, "probe_id": "probe-0001", "label": "probe"}
    (root / "examples" / f"{SYNTHETIC}.example.json").write_text(
        json.dumps(example, indent=2) + "\n", encoding="utf-8"
    )
    manifest["contracts"].append(
        {
            "name": SYNTHETIC,
            "id": schema["$id"],
            "version": SYNTHETIC_VERSION,
            "role": manifest["registry"]["roles"][0],
            "status": manifest["registry"]["statuses"][0],
            "owner_slice": "PXK-59-TEST",
            "schema": f"schemas/{SYNTHETIC}.v1.json",
            "examples": [f"examples/{SYNTHETIC}.example.json"],
        }
    )
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return ContractRoot(root)


def test_the_synthetic_contract_is_discovered_from_registry_data_alone(
    evolved_root: ContractRoot,
) -> None:
    assert SYNTHETIC not in CONTRACTS.names(), "the probe must not be a real registered contract"
    assert SYNTHETIC in evolved_root.names()
    assert len(evolved_root.entries()) == len(CONTRACTS.entries()) + 1


def test_the_synthetic_contract_resolves_its_schema_and_example(
    evolved_root: ContractRoot,
) -> None:
    assert evolved_root.schema_path(SYNTHETIC).is_file()
    paths = evolved_root.example_paths(SYNTHETIC)
    assert paths and all(path.is_file() for path in paths)
    entry = evolved_root.entry(SYNTHETIC)
    assert entry["id"] == evolved_root.expected_schema_id(SYNTHETIC, entry["version"])


def test_the_synthetic_example_validates_through_the_unchanged_harness(
    evolved_root: ContractRoot,
) -> None:
    document = load_json(evolved_root.example_paths(SYNTHETIC)[0])
    assert evolved_root.validate(SYNTHETIC, document) == ()


def test_the_synthetic_contract_obeys_the_same_meta_rules(evolved_root: ContractRoot) -> None:
    schema = load_json(evolved_root.schema_path(SYNTHETIC))
    walk = SchemaWalk(SYNTHETIC, schema, evolved_root.jsonschema_registry()).run()
    assert walk.errors == []
    assert walk.declaring_objects >= 1


def test_the_synthetic_contract_carries_its_own_version_not_a_global_one(
    evolved_root: ContractRoot,
) -> None:
    """The probe sits at 3.7.1 beside contracts at other versions, and every rule still holds."""
    versions = {entry["version"] for entry in evolved_root.entries()}
    assert SYNTHETIC_VERSION in versions
    assert len(versions) > 1, "the probe must differ in version from the existing contracts"

    document = load_json(evolved_root.example_paths(SYNTHETIC)[0])
    for foreign in ("1.0.0", "3.7.0", "4.0.0"):
        candidate = dict(document, schema_version=foreign)
        found = evolved_root.validate(SYNTHETIC, candidate)
        assert ("/schema_version", "const") in {violation.key for violation in found}


def test_the_pre_existing_contracts_are_untouched_by_the_addition(
    evolved_root: ContractRoot,
) -> None:
    """Additive means additive: every previously registered contract keeps its meaning."""
    for entry in CONTRACTS.entries():
        name = entry["name"]
        assert evolved_root.entry(name) == entry
        for path in evolved_root.example_paths(name):
            assert evolved_root.validate(name, load_json(path)) == ()


def test_no_harness_module_mentions_the_synthetic_contract() -> None:
    """The mechanical proof that discovery was data-driven and not a hard-coded special case."""
    offenders = []
    for path in sorted(HARNESS_DIR.glob("*.py")):
        if path.name == Path(__file__).name:
            continue
        if SYNTHETIC in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert offenders == [], f"the probe name is hard-coded in: {offenders}"


def test_no_harness_module_encodes_a_contract_count_or_name_inventory() -> None:
    """No permanent test may pin the registry to today's slice.

    A literal count of the registered contracts, or a set literal of their names, would make
    the next slice's additive registration red. The inventory belongs in ``manifest.json``.
    """
    names = set(CONTRACTS.names())
    total = len(CONTRACTS.entries())
    offenders: list[str] = []
    for path in sorted(HARNESS_DIR.glob("*.py")):
        if path.name == Path(__file__).name:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            # A single registered name is legitimate (the Problem producer names its own
            # contract); an assertion pinning the whole inventory is not.
            names_a_contract = any(f'"{name}"' in code or f"'{name}'" in code for name in names)
            compares_inventory = "entries()" in code or "names()" in code
            if names_a_contract and "==" in code and compares_inventory:
                offenders.append(f"{path.name}:{number}: {line.strip()}")
            if f"== {total}" in code and ("entries()" in code or "names()" in code):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == [], "harness pins the contract inventory:\n" + "\n".join(offenders)
