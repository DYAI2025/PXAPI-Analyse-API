"""What the package is, and what it deliberately is not (A3 scaffold rules, A4 scope gate)."""

import ast
import importlib
import shutil
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "pxapi"
LAYERS = ("domain", "ports", "application", "adapters", "config")


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_is_importable(layer: str) -> None:
    assert importlib.import_module(f"pxapi.{layer}") is not None


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_documents_its_own_rule(layer: str) -> None:
    doc = importlib.import_module(f"pxapi.{layer}").__doc__
    assert doc and doc.strip(), f"pxapi.{layer} must document what it may import"


def test_package_is_marked_typed() -> None:
    assert (SRC / "py.typed").is_file()


#: The executable production modules slice A4 is allowed to add, relative to ``src/pxapi``.
#: Exact allowlist, not a keyword scan: a module is "executable" when its body holds anything
#: beyond a docstring. Widening this set is a deliberate, reviewable edit of the slice that adds
#: the module — never a side effect of adding a file.
A4_EXECUTABLE_MODULES: frozenset[str] = frozenset(
    {
        "domain/run_state.py",
        "domain/stage_execution.py",
    }
)


def _is_docstring_only(body: list[ast.stmt]) -> bool:
    return len(body) == 0 or (
        len(body) == 1
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    )


def executable_modules(package_root: Path) -> set[str]:
    """Every ``.py`` under ``package_root`` whose body is more than a docstring."""
    found = set()
    for py_file in sorted(package_root.rglob("*.py")):
        body = ast.parse(py_file.read_text(encoding="utf-8")).body
        if not _is_docstring_only(body):
            found.add(py_file.relative_to(package_root).as_posix())
    return found


def test_only_approved_a4_modules_are_executable() -> None:
    """Scope gate for PXK-17 AC7: the executable surface is exactly the A4 allowlist.

    It fails in both directions — an unexpected executable module (scoring, measurement,
    synthesis, rendering, a port, an adapter …) and an allowlisted module that has gone
    missing or has become docstring-only — so it can neither be widened by accident nor
    rot into a vacuous pass. The proofs that it fires live in the tests below.
    """
    actual = executable_modules(SRC)
    unexpected = sorted(actual - A4_EXECUTABLE_MODULES)
    missing = sorted(A4_EXECUTABLE_MODULES - actual)
    assert unexpected == [], f"executable modules outside the A4 allowlist: {unexpected}"
    assert missing == [], f"allowlisted A4 modules that are not executable: {missing}"


def test_layer_packages_themselves_stay_docstring_only() -> None:
    """The five ``__init__.py`` files and the root package carry documentation, not code."""
    for layer in LAYERS:
        assert (SRC / layer / "__init__.py").as_posix() not in {
            str(SRC / m) for m in executable_modules(SRC)
        }
    assert "__init__.py" not in executable_modules(SRC)


def _scaffold(tmp_path: Path, extra: dict[str, str]) -> Path:
    """A throwaway copy of the real package tree, with ``extra`` files overlaid."""
    root = tmp_path / "src" / "pxapi"
    shutil.copytree(SRC, root, ignore=shutil.ignore_patterns("__pycache__"))
    for rel, body in extra.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_guard_fixture_reproduces_the_real_verdict(tmp_path: Path) -> None:
    """Guard the guard: the untouched copy must equal the allowlist, or every RED below is void."""
    assert executable_modules(_scaffold(tmp_path, {})) == A4_EXECUTABLE_MODULES


@pytest.mark.parametrize(
    "module",
    [
        "domain/scoring.py",
        "domain/measurement.py",
        "domain/synthesis.py",
        "adapters/rendering.py",
        "application/run_analysis.py",
        "ports/run_store.py",
    ],
)
def test_guard_fires_on_an_unexpected_executable_module(tmp_path: Path, module: str) -> None:
    root = _scaffold(tmp_path, {module: '"""doc."""\n\n\ndef compute():\n    return 1\n'})
    unexpected = executable_modules(root) - A4_EXECUTABLE_MODULES
    assert unexpected == {module}


def test_guard_ignores_a_docstring_only_module(tmp_path: Path) -> None:
    root = _scaffold(tmp_path, {"domain/notes.py": '"""Only a docstring: not executable."""\n'})
    assert executable_modules(root) == A4_EXECUTABLE_MODULES


def test_guard_fires_when_an_allowlisted_module_stops_being_executable(tmp_path: Path) -> None:
    root = _scaffold(tmp_path, {"domain/run_state.py": '"""hollowed out."""\n'})
    assert A4_EXECUTABLE_MODULES - executable_modules(root) == {"domain/run_state.py"}


def test_guard_sees_a_single_statement_as_executable(tmp_path: Path) -> None:
    """A bare assignment, import or call counts — not only ``def``/``class``."""
    for body in ("import json\n", "X = 1\n", "print(1)\n", '"""doc."""\nX = 1\n'):
        root = _scaffold(tmp_path / body.replace("\n", "_").replace('"', ""), {"config/x.py": body})
        assert "config/x.py" in executable_modules(root), body
