"""Assertions about what the A3 scaffold is, and what it deliberately is not."""

import ast
import importlib
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


def test_scaffold_declares_no_behavior() -> None:
    """A3 holds no implementation — every module is a docstring and nothing else.

    This is an intentional scope gate for AC5: no scoring, measurement, SERP,
    synthesis, projection or rendering implementation can be present, because no
    executable statement can be present at all. The slice that adds the first
    real module is expected to replace this test — deliberately, in review, not
    by accident.
    """
    offenders = []
    for py_file in sorted(SRC.rglob("*.py")):
        body = ast.parse(py_file.read_text(encoding="utf-8")).body
        docstring_only = len(body) == 0 or (
            len(body) == 1
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        )
        if not docstring_only:
            offenders.append(str(py_file.relative_to(SRC)))
    assert offenders == [], f"A3 scaffold must contain no behavior, found code in: {offenders}"
