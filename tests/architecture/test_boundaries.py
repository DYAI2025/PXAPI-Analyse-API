"""GREEN proof: the real src/pxapi tree satisfies every layer rule."""

from pathlib import Path

from tests.architecture.boundaries import LAYER_IMPORTS, check_tree, collect_module_names

SRC = Path(__file__).resolve().parents[2] / "src" / "pxapi"


def test_real_package_has_no_boundary_violations() -> None:
    violations = check_tree(SRC)
    assert violations == [], "\n".join(str(v) for v in violations)


def test_every_declared_layer_exists_on_disk() -> None:
    for layer in LAYER_IMPORTS:
        assert (SRC / layer / "__init__.py").is_file(), f"missing layer package: {layer}"


def test_checker_actually_inspected_the_real_package() -> None:
    """Canary against a vacuously green guard.

    A checker that walked zero files would also report zero violations. This
    asserts it really visited every layer module, so the green above means
    something.
    """
    seen = collect_module_names(SRC)
    assert seen >= {f"pxapi.{layer}" for layer in LAYER_IMPORTS}
