"""One egress authority, and no second one growing up beside it.

``PublicTargetPolicy`` decides which destinations a public analysis may connect to, and it is
the only place that decides it. PXAPI-19.B added a *credential* refusal at the application
boundary — a data-minimisation rule, expressed with the Domain's URL identity rules, that keeps
a schema-valid request carrying userinfo from being copied into emitted output before anything
is fetched. The risk that addition creates is not the rule itself but its neighbourhood: a
later edit that starts classifying addresses at the same boundary would leave two answers to
one question, and two answers disagree eventually.

This module locks the shape that prevents it. The application layer holds no address primitive
at all, so it cannot acquire an opinion about reachability without this file being edited in
the same change — which is the review moment a second SSRF authority deserves.

The lock is deliberately *not* "no inner layer imports ``ipaddress``": ``domain.site_identity``
imports it to compress an IPv6 literal into its canonical written form, which is a question
about identity and not about reachability. Banning it there would ban the wrong thing and
teach the next reader that the two questions are the same one.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pxapi"
APPLICATION = SRC / "application"

#: The standard-library modules an address or egress decision is written with. Neither can be
#: used for such a decision without being imported, which is what makes the scan sufficient.
ADDRESS_PRIMITIVES = frozenset({"ipaddress", "socket"})

#: The one module that may hold the address rule, relative to ``src/pxapi``.
EGRESS_AUTHORITY = "adapters/web/target_policy.py"


def imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_application_layer_holds_no_address_primitive() -> None:
    """An egress opinion in the use case would be a second authority beside the policy."""
    offenders = {
        str(path.relative_to(SRC)): sorted(
            imported_roots(path.read_text("utf-8")) & ADDRESS_PRIMITIVES
        )
        for path in sorted(APPLICATION.rglob("*.py"))
    }
    assert {path: found for path, found in offenders.items() if found} == {}


def test_the_address_rule_is_declared_in_exactly_one_module() -> None:
    """``is_public_address`` is the rule itself. Two definitions would be two policies."""
    declaring = [
        str(path.relative_to(SRC))
        for path in sorted(SRC.rglob("*.py"))
        if any(
            isinstance(node, ast.FunctionDef) and node.name == "is_public_address"
            for node in ast.walk(ast.parse(path.read_text("utf-8")))
        )
    ]
    assert declaring == [EGRESS_AUTHORITY]


def test_the_scan_inspected_real_application_modules() -> None:
    """Canary: a walk over zero files would report zero offenders just as happily."""
    scanned = sorted(p.name for p in APPLICATION.rglob("*.py"))
    assert "discover_site.py" in scanned
    assert len(scanned) >= 3, scanned


def test_the_import_scan_sees_a_planted_address_primitive() -> None:
    """Canary: the lock is proved to detect what it exists to forbid, in both import forms."""
    assert imported_roots("import socket\n") & ADDRESS_PRIMITIVES == {"socket"}
    assert imported_roots("import ipaddress\n") & ADDRESS_PRIMITIVES == {"ipaddress"}
    assert imported_roots("from ipaddress import ip_address\n") & ADDRESS_PRIMITIVES == {
        "ipaddress"
    }
    assert imported_roots("import json\n") & ADDRESS_PRIMITIVES == set()
