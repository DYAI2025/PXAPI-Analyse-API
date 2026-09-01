"""Repository-native import-boundary checker for the pxapi modular monolith.

Standard library only, and purely static: it parses source with ``ast`` and never
imports the modules it inspects. That is what lets it flag a forbidden
``import fastapi`` inside ``pxapi.domain`` even though FastAPI is not installed
at all — something an import-time or runtime check structurally cannot do.

``check_tree`` is a pure function over a directory, so the identical function
runs against the real ``src/pxapi`` and against throwaway trees built in a
pytest ``tmp_path``. The RED proofs therefore never touch the committed tree.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PACKAGE = "pxapi"

#: Each layer, and the pxapi-internal layers it is allowed to import.
#: Dependencies point inward only: nothing inner may name an outer layer.
LAYER_IMPORTS: dict[str, frozenset[str]] = {
    "domain": frozenset({"domain"}),
    "ports": frozenset({"ports", "domain"}),
    "application": frozenset({"application", "ports", "domain"}),
    "adapters": frozenset({"adapters", "application", "ports", "domain", "config"}),
    "config": frozenset({"config"}),
}

#: Layers permitted to import third-party distributions at all. Adapters exist to
#: talk to the outside world; every inner layer stays framework-free.
THIRD_PARTY_ALLOWED: frozenset[str] = frozenset({"adapters"})

#: Deliberately empty. A future slice may widen one inner layer here, but only as
#: an explicit, reviewable edit — never by accident.
THIRD_PARTY_ALLOWLIST: dict[str, frozenset[str]] = {}

#: Named bans mirroring PXK-16 AC3 one-to-one, so a violation names the acceptance
#: criterion instead of only reporting "third-party import".
AC3_BANNED_ROOTS: frozenset[str] = frozenset(
    {
        "fastapi",
        "starlette",
        "sqlalchemy",
        "alembic",
        "boto3",
        "botocore",
        "aiobotocore",
        "s3transfer",
    }
)


@dataclass(frozen=True)
class Violation:
    module: str
    layer: str
    imported: str
    lineno: int
    rule: str

    def __str__(self) -> str:
        return (
            f"{self.module}:{self.lineno}: {self.layer} may not import "
            f"{self.imported} [{self.rule}]"
        )


def _module_name(py_file: Path, package_root: Path) -> str:
    parts = list(py_file.relative_to(package_root.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _layer_of(module_name: str) -> str | None:
    parts = module_name.split(".")
    if len(parts) < 2 or parts[0] != PACKAGE:
        return None
    return parts[1] if parts[1] in LAYER_IMPORTS else None


def _iter_imports(
    tree: ast.Module, module_name: str, is_package: bool
) -> Iterator[tuple[str, int]]:
    """Yield (dotted import target, lineno), with relative imports resolved."""
    package = module_name if is_package else module_name.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                parts = package.split(".") if package else []
                kept = parts[: len(parts) - (node.level - 1)]
                base = ".".join([*kept, node.module]) if node.module else ".".join(kept)
            for alias in node.names:
                # Always append the imported name: `from pxapi import adapters`
                # is an edge to pxapi.adapters, not to the bare package.
                yield ".".join(p for p in (base, alias.name) if p), node.lineno


def _judge(module_name: str, layer: str, target: str, lineno: int) -> list[Violation]:
    root = target.split(".")[0]

    if root == PACKAGE:
        parts = target.split(".")
        if len(parts) < 2 or parts[1] not in LAYER_IMPORTS:
            return []  # bare `import pxapi`, or a name we do not govern
        target_layer = parts[1]
        if target_layer not in LAYER_IMPORTS[layer]:
            return [
                Violation(
                    module_name,
                    layer,
                    target,
                    lineno,
                    f"layer-boundary: {layer} -> {target_layer}",
                )
            ]
        return []

    if root in sys.stdlib_module_names:
        return []

    if root in AC3_BANNED_ROOTS and layer not in THIRD_PARTY_ALLOWED:
        return [Violation(module_name, layer, target, lineno, f"AC3-banned-dependency: {root}")]

    if layer in THIRD_PARTY_ALLOWED:
        return []

    if root in THIRD_PARTY_ALLOWLIST.get(layer, frozenset()):
        return []

    return [Violation(module_name, layer, target, lineno, f"third-party-in-{layer}")]


def collect_module_names(package_root: Path) -> set[str]:
    """Every dotted module the checker would inspect. Used as a green-canary."""
    return {_module_name(p, package_root) for p in package_root.rglob("*.py")}


def check_tree(package_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for py_file in sorted(package_root.rglob("*.py")):
        module_name = _module_name(py_file, package_root)
        layer = _layer_of(module_name)
        if layer is None:
            continue  # pxapi/__init__.py itself belongs to no layer
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        is_package = py_file.name == "__init__.py"
        for target, lineno in _iter_imports(tree, module_name, is_package):
            violations.extend(_judge(module_name, layer, target, lineno))
    return violations
