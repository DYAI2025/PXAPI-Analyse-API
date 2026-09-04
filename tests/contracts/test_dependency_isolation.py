"""``jsonschema`` and ``referencing`` are test-only, and stay that way.

PXK-59 ships contract *data* plus a test harness. Nothing under ``src/pxapi`` may import a
validator: doing so would make a JSON Schema implementation a runtime dependency of the
domain, which the A3 boundary rules forbid and which no slice has yet decided to accept.

The check is static (``ast``), so it flags an import that would fail at runtime anyway and it
never imports the modules it inspects. It reads ``pyproject.toml`` rather than the installed
environment, so it does not depend on how the test run was provisioned, and it uses no Git.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "pxapi"
PYPROJECT = ROOT / "pyproject.toml"

#: The distributions the contract harness needs, none of which may become a runtime dependency.
TEST_ONLY_DISTRIBUTIONS = ("jsonschema", "referencing")

#: Import roots those distributions provide.
TEST_ONLY_IMPORT_ROOTS = frozenset({"jsonschema", "jsonschema_specifications", "referencing"})

SOURCE_FILES = sorted(SRC.rglob("*.py"))


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


def test_the_source_tree_is_not_empty() -> None:
    """Canary: an empty file list would make the import scan below vacuously green."""
    assert SOURCE_FILES, f"no Python source found under {SRC}"


@pytest.mark.parametrize("distribution", TEST_ONLY_DISTRIBUTIONS)
def test_the_harness_dependency_is_declared_in_the_dev_group(distribution: str) -> None:
    """Declared in its own right — `referencing` is imported directly, not merely transitively."""
    dev = _requirement_names(_project()["dependency-groups"]["dev"])
    assert distribution in dev, f"{distribution} must be declared in [dependency-groups].dev"


def test_the_requirement_reader_resolves_a_declared_requirement() -> None:
    """Canary: with no runtime dependency declared today, the checks below read through this."""
    declared = ["jsonschema>=4.26,<5", "referencing[x]==0.36.2; python_version >= '3.13'"]
    assert _requirement_names(declared) == {"jsonschema", "referencing"}


@pytest.mark.parametrize("distribution", TEST_ONLY_DISTRIBUTIONS)
def test_the_harness_dependency_is_not_a_runtime_dependency(distribution: str) -> None:
    runtime = _requirement_names(_project()["project"]["dependencies"])
    assert distribution not in runtime
    optional = _project()["project"].get("optional-dependencies", {})
    for extra, entries in optional.items():
        assert distribution not in _requirement_names(entries), (
            f"{distribution} leaked into the optional extra {extra!r}"
        )


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_the_import_scanner_sees_imports_where_they_exist(tmp_path: Path) -> None:
    """Canary for the scanner itself: it must detect what it is meant to forbid."""
    probe = tmp_path / "probe.py"
    probe.write_text("import jsonschema\nfrom referencing import Registry\n", encoding="utf-8")
    assert _imported_roots(probe) & TEST_ONLY_IMPORT_ROOTS == {"jsonschema", "referencing"}


@pytest.mark.parametrize("path", SOURCE_FILES, ids=[str(p.relative_to(SRC)) for p in SOURCE_FILES])
def test_no_source_module_imports_a_validator(path: Path) -> None:
    leaked = sorted(_imported_roots(path) & TEST_ONLY_IMPORT_ROOTS)
    assert leaked == [], f"{path.relative_to(ROOT)} imports test-only distribution(s) {leaked}"
