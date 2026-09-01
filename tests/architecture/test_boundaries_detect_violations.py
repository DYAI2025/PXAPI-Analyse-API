"""RED proofs: each forbidden edge must actually produce a violation.

A guard that has never been seen failing is `not_run`, not `passed`. Every rule
below is exercised against a throwaway tree in tmp_path, so nothing touches the
committed source.
"""

from pathlib import Path

import pytest

from tests.architecture.boundaries import LAYER_IMPORTS, check_tree


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    """Build a minimal pxapi package tree, then overlay `files` onto it."""
    root = tmp_path / "src" / "pxapi"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text('"""root."""\n', encoding="utf-8")
    for layer in LAYER_IMPORTS:
        (root / layer).mkdir()
        (root / layer / "__init__.py").write_text(f'"""{layer}."""\n', encoding="utf-8")
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_the_fixture_itself_is_clean(tmp_path: Path) -> None:
    """Guard the guard: the untouched fixture must be GREEN, or every RED below is meaningless."""
    assert check_tree(_tree(tmp_path, {})) == []


# --- AC3: domain imports no FastAPI, SQLAlchemy, S3 SDK, or adapter implementation ---


@pytest.mark.parametrize("banned", ["fastapi", "sqlalchemy", "boto3"])
def test_domain_may_not_import_ac3_banned_dependency(tmp_path: Path, banned: str) -> None:
    root = _tree(tmp_path, {"domain/thing.py": f"import {banned}\n"})
    violations = check_tree(root)
    assert len(violations) == 1
    assert violations[0].rule == f"AC3-banned-dependency: {banned}"
    assert violations[0].layer == "domain"


def test_domain_may_not_import_an_adapter_implementation(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"domain/thing.py": "from pxapi.adapters import storage\n"})
    violations = check_tree(root)
    assert len(violations) == 1
    assert violations[0].rule == "layer-boundary: domain -> adapters"


def test_domain_may_not_import_any_third_party(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"domain/thing.py": "import httpx\n"})
    assert [v.rule for v in check_tree(root)] == ["third-party-in-domain"]


# --- AC4: application depends only on domain + declared ports ---


def test_application_may_not_import_adapters(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"application/use_case.py": "from pxapi.adapters import s3\n"})
    violations = check_tree(root)
    assert len(violations) == 1
    assert violations[0].rule == "layer-boundary: application -> adapters"


def test_application_may_not_import_third_party(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"application/use_case.py": "import sqlalchemy\n"})
    assert [v.rule for v in check_tree(root)] == ["AC3-banned-dependency: sqlalchemy"]


def test_application_may_import_domain_and_ports(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "application/use_case.py": (
                "from pxapi.domain import model\nfrom pxapi.ports import store\n"
            )
        },
    )
    assert check_tree(root) == []


# --- inward-only, in both directions ---


def test_ports_may_not_import_application(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"ports/store.py": "from pxapi.application import use_case\n"})
    assert [v.rule for v in check_tree(root)] == ["layer-boundary: ports -> application"]


def test_config_is_a_leaf(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"config/settings.py": "from pxapi.domain import model\n"})
    assert [v.rule for v in check_tree(root)] == ["layer-boundary: config -> domain"]


def test_adapters_may_depend_inward(tmp_path: Path) -> None:
    """The permitted direction must NOT be flagged, or the guard is just noise."""
    root = _tree(
        tmp_path,
        {
            "adapters/s3.py": (
                "import boto3\n"
                "from pxapi.application import use_case\n"
                "from pxapi.ports import store\n"
                "from pxapi.domain import model\n"
                "from pxapi.config import settings\n"
            )
        },
    )
    assert check_tree(root) == []


# --- import syntax coverage: a rule that only catches one spelling is a hole ---


def test_relative_parent_import_is_resolved_and_caught(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"domain/sub/thing.py": "from ...adapters import storage\n"})
    assert [v.rule for v in check_tree(root)] == ["layer-boundary: domain -> adapters"]


def test_from_package_import_layer_is_caught(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"domain/thing.py": "from pxapi import adapters\n"})
    assert [v.rule for v in check_tree(root)] == ["layer-boundary: domain -> adapters"]


def test_import_nested_inside_a_function_is_caught(tmp_path: Path) -> None:
    """A deferred import is still a dependency."""
    root = _tree(
        tmp_path,
        {"domain/thing.py": "def f():\n    import fastapi\n    return fastapi\n"},
    )
    assert [v.rule for v in check_tree(root)] == ["AC3-banned-dependency: fastapi"]


# --- no ungoverned zone: the root package and undeclared siblings are governed too ---


def test_root_package_may_not_import_third_party(tmp_path: Path) -> None:
    """pxapi/__init__.py is not exempt: an import here would bind every layer."""
    root = _tree(tmp_path, {"__init__.py": '"""root."""\nimport fastapi\n'})
    assert [v.rule for v in check_tree(root)] == ["AC3-banned-dependency: fastapi"]


def test_root_package_may_not_import_a_layer(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"__init__.py": '"""root."""\nfrom pxapi.adapters import s3\n'})
    assert [v.rule for v in check_tree(root)] == ["layer-boundary: <root> -> adapters"]


def test_undeclared_sibling_package_is_refused(tmp_path: Path) -> None:
    """A package outside the five layers would be an ungoverned laundering channel."""
    root = _tree(tmp_path, {"services/__init__.py": '"""svc."""\nimport fastapi\n'})
    assert [v.rule for v in check_tree(root)] == [
        "ungoverned-package: every module under pxapi must live in a declared layer"
    ]


def test_application_may_not_import_an_undeclared_sibling_package(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "services/__init__.py": '"""svc."""\n',
            "application/use_case.py": "from pxapi.services import gateway\n",
        },
    )
    rules = sorted(v.rule for v in check_tree(root))
    assert rules == [
        "ungoverned-package-import: pxapi.services is not a declared layer",
        "ungoverned-package: every module under pxapi must live in a declared layer",
    ]


def test_bare_package_import_is_refused(tmp_path: Path) -> None:
    """`import pxapi` reaches every layer by attribute access."""
    root = _tree(tmp_path, {"domain/thing.py": "import pxapi\n"})
    assert [v.rule for v in check_tree(root)] == [
        "bare-package-import: import a declared layer, not the pxapi package"
    ]


# --- the third-party ban is proven for every inner layer, not just domain ---


@pytest.mark.parametrize("layer", ["ports", "config"])
def test_remaining_inner_layers_may_not_import_third_party(tmp_path: Path, layer: str) -> None:
    root = _tree(tmp_path, {f"{layer}/thing.py": "import httpx\n"})
    assert [v.rule for v in check_tree(root)] == [f"third-party-in-{layer}"]


def test_stdlib_and_future_imports_are_never_violations(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "domain/thing.py": (
                "from __future__ import annotations\nimport json\nfrom pathlib import Path\n"
            )
        },
    )
    assert check_tree(root) == []
