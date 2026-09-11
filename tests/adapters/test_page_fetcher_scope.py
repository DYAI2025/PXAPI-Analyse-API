"""The fetcher's origin scope: it can only refuse, and it refuses before the policy is asked.

The ordering claim is the load-bearing one. "Refused before an off-origin connection" is proved
here by a policy that records every URL it was asked to validate: a connection can only be
opened to a target the policy validated, so a URL the policy never saw is a URL no socket was
ever opened to.
"""

from __future__ import annotations

from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.adapters.web.target_policy import PublicTargetPolicy, ValidatedTarget
from pxapi.domain.site_identity import canonical_url_key, is_same_origin
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure, PageFetchOutcome
from tests.adapters.http_test_server import (
    ControlledHttpServer,
    LoopbackTargetPolicy,
    Route,
)


class RecordingPolicy(LoopbackTargetPolicy):
    """The loopback test policy, recording every URL handed to ``validate``."""

    def __init__(self) -> None:
        super().__init__(resolve=lambda host, port: ["127.0.0.1"])
        self.validated: list[str] = []

    def validate(self, url: str) -> ValidatedTarget:
        self.validated.append(url)
        return super().validate(url)


def scoped_to(base: str):  # type: ignore[no-untyped-def]
    origin = base + "/"

    def in_origin(url: str) -> bool:
        key = canonical_url_key(url)
        return key is not None and is_same_origin(key, origin)

    return in_origin


PAGE = Route(body=b"<html></html>", headers={"Content-Type": "text/html"})


def test_without_a_scope_the_fetcher_behaves_exactly_as_before() -> None:
    with ControlledHttpServer({"/": PAGE}) as server:
        result = SafePageFetcher(policy=RecordingPolicy()).fetch(server.url("/"))
    assert isinstance(result, PageFetchOutcome) and result.status_code == 200


def test_a_same_origin_redirect_is_followed_under_the_scope() -> None:
    routes = {"/a": Route(status=302, headers={"Location": "/b"}), "/b": PAGE}
    with ControlledHttpServer(routes) as server:
        result = SafePageFetcher(policy=RecordingPolicy(), scope=scoped_to(server.base_url)).fetch(
            server.url("/a")
        )
    assert isinstance(result, PageFetchOutcome)
    assert result.redirect_count == 1 and result.final_url == server.url("/b")


def test_an_off_scope_first_url_is_refused_without_the_policy_ever_being_asked() -> None:
    policy = RecordingPolicy()
    with ControlledHttpServer({"/": PAGE}) as server:
        result = SafePageFetcher(policy=policy, scope=scoped_to(server.base_url)).fetch(
            "http://evil.test/"
        )
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)
    assert policy.validated == []


def _redirect_refused(location_for) -> tuple[object, list[str], str]:  # type: ignore[no-untyped-def]
    policy = RecordingPolicy()
    routes: dict[str, Route] = {}
    with ControlledHttpServer(routes) as server:
        routes["/"] = Route(status=302, headers={"Location": location_for(server)})
        result = SafePageFetcher(policy=policy, scope=scoped_to(server.base_url)).fetch(
            server.url("/")
        )
    return result, policy.validated, server.url("/")


def test_a_redirect_to_another_host_is_refused_before_it_is_validated_or_resolved() -> None:
    result, validated, first = _redirect_refused(lambda s: "http://evil.test/steal")
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)
    assert validated == [first]


def test_a_scheme_relative_redirect_to_another_host_is_refused() -> None:
    result, validated, first = _redirect_refused(lambda s: "//evil.test/steal")
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)
    assert validated == [first]


def test_a_backslash_smuggled_authority_is_refused() -> None:
    """WHATWG reads ``\\`` as a path separator; an authority carrying one is not our origin."""
    result, validated, first = _redirect_refused(lambda s: f"{s.base_url}\\@evil.test/")
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)
    assert validated == [first]


def test_a_redirect_to_the_same_host_on_another_port_is_another_origin() -> None:
    with ControlledHttpServer({"/": PAGE}) as other:
        result, validated, first = _redirect_refused(lambda s: other.url("/"))
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)
    assert validated == [first]


def test_a_redirect_downgrading_the_scheme_is_another_origin() -> None:
    result, validated, first = _redirect_refused(
        lambda s: s.base_url.replace("http://", "https://") + "/x"
    )
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)
    assert validated == [first]


def test_a_scope_that_admits_everything_cannot_widen_the_shipped_policy() -> None:
    """The scope only narrows: loopback stays refused under ``PublicTargetPolicy``."""
    with ControlledHttpServer({"/": PAGE}) as server:
        result = SafePageFetcher(policy=PublicTargetPolicy(), scope=lambda url: True).fetch(
            server.url("/")
        )
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)
