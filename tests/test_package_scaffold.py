"""Assertions about what the package is, and what it deliberately is not."""

import ast
import importlib
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "pxapi"
LAYERS = ("domain", "ports", "application", "adapters", "config")

#: Modules under ``src/pxapi`` that a slice has explicitly authorised to hold executable
#: behavior, mapped to the slice that authorised them. Every other module must still be a
#: docstring and nothing else.
#:
#: This replaces the A3 rule that *no* module anywhere may contain an executable statement.
#: That rule was a scope gate: it made it impossible for scoring, measurement, SERP,
#: synthesis, projection, rendering, persistence or an adapter implementation to appear by
#: accident. The gate is kept and narrowed rather than dropped — widening this mapping is the
#: same deliberate, reviewable act the old rule forced, and the tests below make an entry that
#: is stale, unearned or blanket fail on its own.
BEHAVIOR_ALLOWED: dict[str, str] = {
    "domain/run_state.py": "PXK-60",
    "domain/observations.py": "PXK-67",
    "domain/findings.py": "PXK-20",
    "ports/page_fetch.py": "PXK-67",
    "ports/html_observation.py": "PXK-67",
    "application/analyze_homepage.py": "PXK-67",
    "application/derive_findings.py": "PXK-20",
    "adapters/contracts/registry.py": "PXK-67",
    "adapters/web/target_policy.py": "PXK-67",
    "adapters/web/page_fetcher.py": "PXK-67",
    "adapters/web/html_observations.py": "PXK-67",
    "adapters/inbound/http_api.py": "PXK-67",
    "adapters/inbound/cli.py": "PXK-67",
    "adapters/composition.py": "PXK-67",
    "config/contract_root.py": "PXK-67",
    "config/fetch_limits.py": "PXK-67",
}

SOURCE_FILES = sorted(SRC.rglob("*.py"))
ALLOWLIST_IDS = sorted(BEHAVIOR_ALLOWED)


def _is_docstring_only(py_file: Path) -> bool:
    """Whether the module's body is at most one string expression — a docstring and no code."""
    body = ast.parse(py_file.read_text(encoding="utf-8")).body
    return len(body) == 0 or (
        len(body) == 1
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    )


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_is_importable(layer: str) -> None:
    assert importlib.import_module(f"pxapi.{layer}") is not None


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_documents_its_own_rule(layer: str) -> None:
    doc = importlib.import_module(f"pxapi.{layer}").__doc__
    assert doc and doc.strip(), f"pxapi.{layer} must document what it may import"


def test_package_is_marked_typed() -> None:
    assert (SRC / "py.typed").is_file()


# --- the scope gate --------------------------------------------------------------------------


def test_the_source_tree_is_not_empty() -> None:
    """Canary: an empty file list would make the scan below vacuously green."""
    assert SOURCE_FILES, f"no Python source found under {SRC}"


def test_the_behavior_detector_sees_behavior_where_it_exists(tmp_path: Path) -> None:
    """Canary for the detector itself: it must recognise what the gate exists to forbid."""
    docstring_only = tmp_path / "quiet.py"
    docstring_only.write_text('"""Only a docstring."""\n', encoding="utf-8")
    empty = tmp_path / "empty.py"
    empty.write_text("", encoding="utf-8")
    with_code = tmp_path / "loud.py"
    with_code.write_text('"""Doc."""\n\nVALUE = 1\n', encoding="utf-8")
    assert _is_docstring_only(docstring_only) is True
    assert _is_docstring_only(empty) is True
    assert _is_docstring_only(with_code) is False


def test_only_authorised_modules_declare_behavior() -> None:
    """Scope gate: behavior exists only where a slice put it on the record.

    No scoring, measurement, SERP, synthesis, projection, rendering, persistence or adapter
    implementation can appear by accident, because a module that is not named here may not
    contain an executable statement at all.
    """
    offenders = [
        str(path.relative_to(SRC))
        for path in SOURCE_FILES
        if str(path.relative_to(SRC)) not in BEHAVIOR_ALLOWED and not _is_docstring_only(path)
    ]
    assert offenders == [], f"unauthorised behavior under src/pxapi: {offenders}"


@pytest.mark.parametrize("relative", ALLOWLIST_IDS, ids=ALLOWLIST_IDS)
def test_every_authorised_module_exists(relative: str) -> None:
    """A stale entry would silently exempt a path that nobody reviews and nothing checks."""
    assert (SRC / relative).is_file(), f"{relative} is authorised but absent"


@pytest.mark.parametrize("relative", ALLOWLIST_IDS, ids=ALLOWLIST_IDS)
def test_every_authorised_module_earns_its_entry(relative: str) -> None:
    """An authorised module that holds no behavior does not need the exemption; drop it."""
    assert not _is_docstring_only(SRC / relative), (
        f"{relative} holds no behavior; remove it from BEHAVIOR_ALLOWED"
    )


@pytest.mark.parametrize("relative", ALLOWLIST_IDS, ids=ALLOWLIST_IDS)
def test_every_authorised_module_names_its_slice_and_lives_in_a_layer(relative: str) -> None:
    """Behavior is attributable and inside the architecture, never in an ungoverned corner."""
    assert BEHAVIOR_ALLOWED[relative].strip(), f"{relative}: name the slice that authorised it"
    parts = Path(relative).parts
    assert len(parts) >= 2 and parts[0] in LAYERS, f"{relative}: not inside a declared layer"
    assert parts[-1] != "__init__.py", (
        f"{relative}: a layer package stays a docstring; behavior belongs in a named module"
    )


def test_the_allowlist_is_not_a_blanket_exemption() -> None:
    """Canary: the gate must still be scanning real, unlisted modules."""
    scanned = {str(path.relative_to(SRC)) for path in SOURCE_FILES}
    assert scanned - set(BEHAVIOR_ALLOWED), "every module is authorised; the gate is vacuous"
