"""A JSON Schema validator lives in exactly one adapter, and never in an inner layer.

PXK-59 shipped contract *data* plus a test harness and could therefore keep ``jsonschema`` and
``referencing`` out of ``src/`` entirely. PXK-67 makes the transport boundary validate at
runtime, so that blanket rule no longer states the truth. It is **narrowed rather than
dropped**, the same way PXK-60 narrowed the behavior gate instead of deleting it.

What actually matters is unchanged and is what this module now enforces: the Domain, the Ports,
the Application and the Config layers may never import a validator. A validator inside them
would let contract shapes leak into business logic and become a second authority beside the
schemas. Validation is an edge concern, so it lives at the edge — in one named adapter, on an
allowlist, so it cannot spread quietly.

The check is static (``ast``): it never imports the modules it inspects, and it reads
``pyproject.toml`` rather than the installed environment, so it does not depend on how the run
was provisioned and it uses no Git.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "pxapi"
PYPROJECT = ROOT / "pyproject.toml"

#: The distributions that provide a JSON Schema validator.
VALIDATOR_DISTRIBUTIONS = ("jsonschema", "referencing")

#: Import roots those distributions provide.
VALIDATOR_IMPORT_ROOTS = frozenset({"jsonschema", "jsonschema_specifications", "referencing"})

#: The layers that may never import a validator, whatever a later slice needs. This is the
#: invariant PXK-59 was protecting; only the blanket phrasing changed.
VALIDATOR_FREE_LAYERS = ("domain", "ports", "application", "config")

#: The only modules under ``src/pxapi`` permitted to import a validator, and the slice that
#: authorised each. A module absent from this mapping may not import one; an entry that no
#: longer imports one is stale and fails on its own, so the list cannot rot into a blanket
#: exemption for the whole adapters layer.
VALIDATOR_ALLOWED: dict[str, str] = {
    "adapters/contracts/registry.py": "PXK-67",
}

SOURCE_FILES = sorted(SRC.rglob("*.py"))
ALLOWED_IDS = sorted(VALIDATOR_ALLOWED)


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _requirement_names(entries: list[str]) -> set[str]:
    """The distribution name of each requirement string, without its version specifier."""
    names = set()
    for entry in entries:
        name = entry.split(";", 1)[0].strip()
        for separator in ("[", "=", "<", ">", "!", "~", " "):
            name = name.split(separator, 1)[0]
        names.add(name.strip().lower())
    return names


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _layer_of(path: Path) -> str:
    return path.relative_to(SRC).parts[0]


def test_the_source_tree_is_not_empty() -> None:
    """Canary: an empty file list would make every import scan below vacuously green."""
    assert SOURCE_FILES, f"no Python source found under {SRC}"


def test_the_requirement_reader_resolves_a_declared_requirement() -> None:
    """Canary for the reader the dependency assertions below read through."""
    declared = ["jsonschema>=4.26,<5", "referencing[x]==0.36.2; python_version >= '3.13'"]
    assert _requirement_names(declared) == {"jsonschema", "referencing"}


def test_the_import_scanner_sees_imports_where_they_exist(tmp_path: Path) -> None:
    """Canary for the scanner itself: it must detect what it is meant to forbid."""
    probe = tmp_path / "probe.py"
    probe.write_text("import jsonschema\nfrom referencing import Registry\n", encoding="utf-8")
    assert _imported_roots(probe) & VALIDATOR_IMPORT_ROOTS == {"jsonschema", "referencing"}


@pytest.mark.parametrize("distribution", VALIDATOR_DISTRIBUTIONS)
def test_the_validator_is_declared_as_a_runtime_dependency(distribution: str) -> None:
    """Shipped code imports it, so it is a runtime dependency and must say so."""
    runtime = _requirement_names(_project()["project"]["dependencies"])
    assert distribution in runtime, f"{distribution} must be declared in [project].dependencies"


@pytest.mark.parametrize("distribution", VALIDATOR_DISTRIBUTIONS)
def test_the_validator_is_not_declared_twice(distribution: str) -> None:
    """A runtime dependency is available to the tests already; declaring it again states one
    fact in two places, and the two can then disagree."""
    dev = _requirement_names(_project()["dependency-groups"]["dev"])
    assert distribution not in dev, f"{distribution} is a runtime dependency; drop the dev entry"


INNER_FILES = [path for path in SOURCE_FILES if _layer_of(path) in VALIDATOR_FREE_LAYERS]
INNER_IDS = [str(path.relative_to(SRC)) for path in INNER_FILES]


def test_the_inner_layers_actually_hold_modules() -> None:
    """Canary: the inner-layer scan must not pass by inspecting nothing."""
    assert INNER_FILES, f"no module found in any of {VALIDATOR_FREE_LAYERS}"


@pytest.mark.parametrize("path", INNER_FILES, ids=INNER_IDS)
def test_no_inner_layer_module_imports_a_validator(path: Path) -> None:
    """The Domain, Ports, Application and Config rings stay free of a validator entirely."""
    leaked = sorted(_imported_roots(path) & VALIDATOR_IMPORT_ROOTS)
    assert leaked == [], f"{path.relative_to(ROOT)} imports validator distribution(s) {leaked}"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=[str(p.relative_to(SRC)) for p in SOURCE_FILES])
def test_only_an_allowlisted_module_imports_a_validator(path: Path) -> None:
    relative = str(path.relative_to(SRC))
    leaked = sorted(_imported_roots(path) & VALIDATOR_IMPORT_ROOTS)
    if relative in VALIDATOR_ALLOWED:
        return
    assert leaked == [], (
        f"{relative} imports {leaked} but is not on the validator allowlist; "
        "validation belongs at the transport edge, in one named adapter"
    )


@pytest.mark.parametrize("relative", ALLOWED_IDS, ids=ALLOWED_IDS)
def test_every_allowlisted_module_exists(relative: str) -> None:
    """A stale entry would silently exempt a path that nobody reviews and nothing checks."""
    assert (SRC / relative).is_file(), f"{relative} is allowlisted but absent"


@pytest.mark.parametrize("relative", ALLOWED_IDS, ids=ALLOWED_IDS)
def test_every_allowlisted_module_earns_its_entry(relative: str) -> None:
    """An entry for a module that imports no validator is an unearned exemption."""
    leaked = _imported_roots(SRC / relative) & VALIDATOR_IMPORT_ROOTS
    assert leaked, f"{relative} is allowlisted but imports no validator; drop the entry"


@pytest.mark.parametrize("relative", ALLOWED_IDS, ids=ALLOWED_IDS)
def test_every_allowlisted_module_is_an_adapter(relative: str) -> None:
    """The allowlist may never be used to open a hole in an inner layer."""
    layer = Path(relative).parts[0]
    assert layer == "adapters", f"{relative} is in {layer!r}; only an adapter may validate"
