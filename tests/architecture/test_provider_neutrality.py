"""No crawler or browser provider can reach the product, and the discovery port stays neutral.

D-PXAPI-007 says providers must not decide which pages become diagnosis-relevant, and
D-PXAPI-010 keeps Crawl4AI an adapter candidate rather than an authority. The layer checker
already forbids every third party in the inner layers; this module adds the architecture lock
that names the rejected designs themselves, tree-wide, so that even the adapters layer cannot
acquire one of them without this file being edited in the same change — which is the review
moment a browser or crawler dependency deserves, and which PXAPI-19.B explicitly excludes.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

from pxapi.domain.site_discovery import DiscoveryObservation, DiscoveryReport, SourceAttempt

SRC = Path(__file__).resolve().parents[2] / "src" / "pxapi"
PORT = SRC / "ports" / "site_discovery.py"

#: Crawler, browser-automation and rendering providers. None is a dependency of this project,
#: and none may become one without this lock being edited deliberately.
BANNED_PROVIDERS = frozenset(
    {"crawl4ai", "playwright", "selenium", "pyppeteer", "scrapy", "requests_html", "splinter"}
)


def imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_module_imports_a_crawler_or_browser_provider() -> None:
    offenders = {
        str(path.relative_to(SRC)): sorted(
            imported_roots(path.read_text("utf-8")) & BANNED_PROVIDERS
        )
        for path in sorted(SRC.rglob("*.py"))
    }
    assert {path: found for path, found in offenders.items() if found} == {}


def test_the_scan_sees_a_planted_provider_import() -> None:
    """Canary: the lock is proved to detect what it exists to forbid, in both import forms."""
    assert imported_roots("import playwright.sync_api\n") & BANNED_PROVIDERS == {"playwright"}
    assert imported_roots("from crawl4ai import AsyncWebCrawler\n") & BANNED_PROVIDERS == {
        "crawl4ai"
    }


def test_the_discovery_port_imports_nothing_but_the_domain_and_the_standard_library() -> None:
    roots = imported_roots(PORT.read_text("utf-8"))
    assert roots <= {"__future__", "typing", "pxapi"}, roots


def test_nothing_transport_shaped_crosses_the_discovery_port() -> None:
    """A body, a header or a status code crossing the port would let a provider's view of a
    page reach the methodology. The boundary shapes carry observations and outcomes only."""
    assert {f.name for f in dataclasses.fields(DiscoveryReport)} == {
        "target_origin",
        "observations",
        "attempts",
        "bootstrap_failure",
    }
    assert {f.name for f in dataclasses.fields(DiscoveryObservation)} == {
        "observed_form",
        "source_id",
        "label",
    }
    assert {f.name for f in dataclasses.fields(SourceAttempt)} == {"source_id", "outcome"}
