"""Hostile or merely sloppy input never escapes as an exception: it becomes a neutral state.

An exception is not an outcome. A discovery that raises produces no run state, no inventory and
no record of why, and a crash in the middle of a run is exactly the kind of technical failure
PXAPI-19 requires to stay neutral rather than vanish. Every input below reached a real code path
that raised before this file existed; each now ends in the contract's closed vocabulary.
"""

from __future__ import annotations

from typing import Any

from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.adapters.web.site_discovery import HttpSiteDiscovery
from pxapi.domain.site_discovery import BootstrapFailure
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure
from tests.adapters.http_test_server import ControlledHttpServer, Route, loopback_policy
from tests.adapters.test_site_discovery_adapter import discover, home, outcomes

PAGE = Route(body=b"<html></html>", headers={"Content-Type": "text/html"})


def fetch_after_redirect(location: str) -> Any:
    with ControlledHttpServer({"/": Route(status=302, headers={"Location": location})}) as server:
        return SafePageFetcher(policy=loopback_policy()).fetch(server.url("/"))


def test_a_redirect_to_a_raw_non_ascii_path_is_a_protocol_error_not_a_crash() -> None:
    """A server that writes ``Location: /über`` unescaped is common and not an attack; the
    request line http.client cannot encode is a request we could not make."""
    assert fetch_after_redirect("/über") == PageFetchFailure(FetchFailureKind.PROTOCOL_ERROR)


def test_a_redirect_the_standard_library_cannot_split_is_an_invalid_redirect() -> None:
    assert fetch_after_redirect("http://[::1") == PageFetchFailure(
        FetchFailureKind.INVALID_REDIRECT
    )


def test_a_target_the_standard_library_cannot_split_is_refused() -> None:
    result = SafePageFetcher(policy=loopback_policy()).fetch("http://[::1")
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)


def test_a_robots_file_declaring_an_unknown_charset_is_still_read() -> None:
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": Route(
                body=f"Sitemap: {b}/s.xml\n".encode(),
                headers={"Content-Type": "text/plain; charset=x-no-such-codec"},
            ),
        }
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "USED"


class _Exploding:
    """A fetcher that raises: a provider or runtime defect nobody anticipated."""

    def fetch(self, url: str) -> Any:
        raise RuntimeError("an unanticipated defect")


def test_a_source_whose_read_raises_is_our_runtime_error_and_the_others_continue() -> None:
    def factory(scope: Any) -> Any:
        return _Exploding() if scope is not None else SafePageFetcher(policy=loopback_policy())

    report, base = discover(lambda b: {"/": home(("/a", "A"))}, fetcher_factory=factory)
    assert report.target_origin == base + "/"
    assert outcomes(report)["ROBOTS_DECLARATION"] == "RUNTIME_ERROR"
    assert outcomes(report)["SITEMAP"] == "RUNTIME_ERROR"
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "USED"


def test_a_bootstrap_whose_fetch_raises_establishes_nothing_and_says_why() -> None:
    report = HttpSiteDiscovery(fetcher_factory=lambda scope: _Exploding()).discover(
        "https://example.com/"
    )
    assert report.target_origin is None
    assert report.bootstrap_failure is BootstrapFailure.RUNTIME_ERROR
