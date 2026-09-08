"""The fetcher against a real HTTP server, and against every way a fetch can fail.

These are integration tests: a genuine socket, a genuine HTTP exchange, genuine redirects.
What they do not use is the internet — the server is on loopback and every name resolves
through an injected resolver, so the suite is deterministic and offline.
"""

from __future__ import annotations

import pytest

from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.adapters.web.target_policy import PublicTargetPolicy
from pxapi.config.fetch_limits import FetchLimits
from pxapi.ports.page_fetch import FetchFailureKind, PageFetchFailure, PageFetchOutcome
from tests.adapters.http_test_server import ControlledHttpServer, Route, loopback_policy

HTML = b"<html><head><title>Hello</title></head><body>hi</body></html>"
HTML_HEADERS = {"Content-Type": "text/html; charset=utf-8"}


def fetcher(**kwargs: object) -> SafePageFetcher:
    limits = kwargs.pop("limits", FetchLimits())
    return SafePageFetcher(policy=loopback_policy(), limits=limits)  # type: ignore[arg-type]


# --- the happy path -----------------------------------------------------------------------


def test_a_real_response_is_returned_with_its_observable_facts() -> None:
    with ControlledHttpServer({"/": Route(body=HTML, headers=HTML_HEADERS)}) as server:
        result = fetcher().fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome)
    assert result.status_code == 200
    assert result.body == HTML
    assert result.content_type == "text/html; charset=utf-8"
    assert result.declared_charset == "utf-8"
    assert result.is_https is False
    assert result.redirect_count == 0
    assert result.truncated is False
    assert result.final_url == server.url("/")


def test_a_query_string_reaches_the_server() -> None:
    with ControlledHttpServer({"/p?a=1": Route(body=b"ok", headers=HTML_HEADERS)}) as server:
        result = fetcher().fetch(server.url("/p?a=1"))
    assert isinstance(result, PageFetchOutcome)
    assert result.body == b"ok"


# --- redirects ----------------------------------------------------------------------------


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_to_a_permitted_target_is_followed(status: int) -> None:
    routes = {
        "/from": Route(status=status, headers={"Location": "/to"}),
        "/to": Route(body=HTML, headers=HTML_HEADERS),
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/from"))

    assert isinstance(result, PageFetchOutcome)
    assert result.body == HTML
    assert result.redirect_count == 1
    assert result.final_url == server.url("/to")


def test_the_redirect_chain_is_bounded() -> None:
    routes = {f"/{n}": Route(status=302, headers={"Location": f"/{n + 1}"}) for n in range(10)}
    with ControlledHttpServer(routes) as server:
        result = fetcher(limits=FetchLimits(max_redirects=2)).fetch(server.url("/0"))

    assert result == PageFetchFailure(FetchFailureKind.TOO_MANY_REDIRECTS)


def test_a_redirect_without_a_location_is_refused() -> None:
    with ControlledHttpServer({"/": Route(status=302)}) as server:
        result = fetcher().fetch(server.url("/"))
    assert result == PageFetchFailure(FetchFailureKind.INVALID_REDIRECT)


@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1:1/",  # permitted by the test policy, so the port is what fails
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://192.168.0.1/admin",
        "http://[::1]:9/",
        "ftp://example.com/",
        "file:///etc/passwd",
    ],
)
def test_a_redirect_is_validated_before_it_is_followed(location: str) -> None:
    """The redirect target gets the full check, not a weaker one than the original URL."""
    with ControlledHttpServer({"/": Route(status=302, headers={"Location": location})}) as server:
        result = fetcher().fetch(server.url("/"))

    assert isinstance(result, PageFetchFailure)
    assert result.kind in {
        FetchFailureKind.BLOCKED_TARGET,
        FetchFailureKind.CONNECTION_FAILURE,
    }


def test_a_redirect_to_a_forbidden_target_is_blocked_before_any_connection() -> None:
    """The decisive case: metadata endpoints are refused by policy, never merely unreachable."""
    metadata = "http://169.254.169.254/latest/meta-data/"
    with ControlledHttpServer({"/": Route(status=302, headers={"Location": metadata})}) as server:
        result = fetcher().fetch(server.url("/"))

    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)


def test_every_redirect_hop_is_resolved_again() -> None:
    """A hop that skipped re-resolution would let a name rebind between check and connect."""
    resolved: list[str] = []

    class RecordingPolicy(PublicTargetPolicy):
        def _permits(self, address: str) -> bool:
            return address in {"127.0.0.1", "::1"} or super()._permits(address)

    def resolve(host: str, port: int) -> list[str]:
        resolved.append(host)
        return ["127.0.0.1"]

    routes = {
        "/a": Route(status=302, headers={"Location": "/b"}),
        "/b": Route(status=302, headers={"Location": "/c"}),
        "/c": Route(body=HTML, headers=HTML_HEADERS),
    }
    # A hostname, not a literal: only a name is resolved, and the connection then goes to the
    # address that resolution returned, which is what makes the re-resolution observable.
    with ControlledHttpServer(routes) as server:
        result = SafePageFetcher(policy=RecordingPolicy(resolve=resolve)).fetch(
            f"http://page.test:{server.port}/a"
        )

    assert isinstance(result, PageFetchOutcome)
    assert result.redirect_count == 2
    # One resolution for the original URL and one for each hop actually taken.
    assert resolved == ["page.test", "page.test", "page.test"], (
        f"expected a fresh resolution per hop, got {resolved}"
    )


def test_an_address_literal_is_classified_without_being_resolved() -> None:
    """There is nothing to resolve, and resolving anyway would be a second chance to be lied to."""
    asked: list[str] = []

    def resolve(host: str, port: int) -> list[str]:
        asked.append(host)
        return ["127.0.0.1"]

    class Loopback(PublicTargetPolicy):
        def _permits(self, address: str) -> bool:
            return address == "127.0.0.1" or super()._permits(address)

    with ControlledHttpServer({"/": Route(body=HTML, headers=HTML_HEADERS)}) as server:
        result = SafePageFetcher(policy=Loopback(resolve=resolve)).fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome)
    assert asked == []


def test_the_connection_goes_to_the_resolved_address_not_the_name() -> None:
    """The name never reaches the socket layer; if it did, this could not connect at all."""

    class Loopback(PublicTargetPolicy):
        def _permits(self, address: str) -> bool:
            return address == "127.0.0.1" or super()._permits(address)

    with ControlledHttpServer({"/": Route(body=HTML, headers=HTML_HEADERS)}) as server:
        policy = Loopback(resolve=lambda host, port: ["127.0.0.1"])
        result = SafePageFetcher(policy=policy).fetch(f"http://nowhere.invalid:{server.port}/")

    # `.invalid` is guaranteed never to resolve, so a fetcher that connected by hostname could
    # not have reached the server at all.
    assert isinstance(result, PageFetchOutcome)
    assert result.body == HTML


# --- blocked targets, before any socket ----------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/",
        "http://[::1]/",
        "http://10.1.2.3/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://172.16.0.1/",
        "https://user:secret@example.com/",
        "ftp://example.com/",
    ],
)
def test_a_forbidden_url_is_refused_by_the_strict_policy(url: str) -> None:
    """The shipped policy, not the test one: nothing here reaches the network."""
    strict = SafePageFetcher(policy=PublicTargetPolicy(resolve=lambda h, p: ["127.0.0.1"]))
    result = strict.fetch(url)
    assert result == PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)


def test_a_name_that_does_not_resolve_is_a_dns_failure() -> None:
    import socket as socket_module

    def failing(host: str, port: int) -> list[str]:
        raise socket_module.gaierror("no such host")

    result = SafePageFetcher(policy=PublicTargetPolicy(resolve=failing)).fetch(
        "https://nx.example/"
    )
    assert result == PageFetchFailure(FetchFailureKind.DNS_FAILURE)


def test_a_refused_connection_is_a_connection_failure() -> None:
    with ControlledHttpServer({}) as server:
        dead_port = server.port
    # The server is closed; the port is now almost certainly refusing.
    result = fetcher().fetch(f"http://127.0.0.1:{dead_port}/")
    assert isinstance(result, PageFetchFailure)
    assert result.kind is FetchFailureKind.CONNECTION_FAILURE


# --- bounds --------------------------------------------------------------------------------


def test_a_slow_response_is_a_timeout() -> None:
    routes = {"/slow": Route(body=HTML, headers=HTML_HEADERS, delay=2.0)}
    with ControlledHttpServer(routes) as server:
        result = fetcher(limits=FetchLimits(read_timeout_seconds=0.25)).fetch(server.url("/slow"))

    assert result == PageFetchFailure(FetchFailureKind.TIMEOUT)


def test_an_exhausted_overall_deadline_is_a_timeout() -> None:
    routes = {"/slow": Route(body=HTML, headers=HTML_HEADERS, delay=1.0)}
    limits = FetchLimits(total_deadline_seconds=0.25, read_timeout_seconds=5.0)
    with ControlledHttpServer(routes) as server:
        result = fetcher(limits=limits).fetch(server.url("/slow"))

    assert result == PageFetchFailure(FetchFailureKind.TIMEOUT)


def test_an_oversized_body_is_bounded_and_flagged() -> None:
    big = b"<html><head><title>x</title></head><body>" + (b"a" * 50_000) + b"</body></html>"
    with ControlledHttpServer({"/": Route(body=big, headers=HTML_HEADERS)}) as server:
        result = fetcher(limits=FetchLimits(max_response_bytes=1_000)).fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome)
    assert len(result.body) == 1_000, "the body must be bounded, not read in full"
    assert result.truncated is True


def test_a_body_inside_the_bound_is_not_flagged_as_truncated() -> None:
    """Canary: the truncation flag must not be stuck on."""
    with ControlledHttpServer({"/": Route(body=HTML, headers=HTML_HEADERS)}) as server:
        result = fetcher(limits=FetchLimits(max_response_bytes=1_000_000)).fetch(server.url("/"))
    assert isinstance(result, PageFetchOutcome)
    assert result.truncated is False


# --- statuses and content types are reported, never judged ----------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 418, 500, 502, 503])
def test_a_4xx_or_5xx_is_a_returned_response_and_not_a_failure(status: int) -> None:
    with ControlledHttpServer({"/": Route(status=status, headers=HTML_HEADERS)}) as server:
        result = fetcher().fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome), "an error status is still a real observation"
    assert result.status_code == status


@pytest.mark.parametrize(
    "content_type",
    ["application/pdf", "application/json", "image/png", "text/plain"],
)
def test_a_non_html_content_type_is_reported_as_it_arrived(content_type: str) -> None:
    routes = {"/": Route(body=b"...", headers={"Content-Type": content_type})}
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome)
    assert result.content_type == content_type


def test_a_response_without_a_content_type_reports_none() -> None:
    with ControlledHttpServer({"/": Route(body=b"x", headers={"Content-Type": ""})}) as server:
        result = fetcher().fetch(server.url("/"))
    assert isinstance(result, PageFetchOutcome)
    assert result.declared_charset is None


# --- X-Robots-Tag survives the wire, one entry per physical header line ------------------------


def fetch_with_robots_headers(lines: list[str]) -> PageFetchOutcome:
    routes = {
        "/": Route(
            body=HTML,
            headers=HTML_HEADERS,
            repeated_headers=tuple(("X-Robots-Tag", line) for line in lines),
        )
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/"))
    assert isinstance(result, PageFetchOutcome)
    return result


def test_a_response_without_the_header_reports_no_field_values() -> None:
    with ControlledHttpServer({"/": Route(body=HTML, headers=HTML_HEADERS)}) as server:
        result = fetcher().fetch(server.url("/"))
    assert isinstance(result, PageFetchOutcome)
    assert result.x_robots_tag == ()


def test_one_header_line_arrives_as_one_field_value() -> None:
    assert fetch_with_robots_headers(["noindex"]).x_robots_tag == ("noindex",)


def test_a_single_line_carrying_several_directives_is_not_split() -> None:
    """Splitting is the domain's decision; the port carries the field value as it arrived."""
    assert fetch_with_robots_headers(["noindex, nofollow"]).x_robots_tag == ("noindex, nofollow",)


def test_repeated_header_lines_each_survive_as_their_own_field_value() -> None:
    """The property the whole tuple exists for, proven on a real socket rather than a stub.

    Three physical lines must arrive as three entries. Folded into one comma-separated string
    they would be indistinguishable from a single crawler-scoped value, which is how a generic
    directive stops looking generic.
    """
    lines = ["googlebot: follow", "noindex", "bingbot: noindex"]
    assert fetch_with_robots_headers(lines).x_robots_tag == tuple(lines)


def test_the_field_values_are_an_immutable_tuple() -> None:
    """An observation that could be edited after it was made is not an observation."""
    assert isinstance(fetch_with_robots_headers(["noindex"]).x_robots_tag, tuple)


def test_the_header_name_is_matched_case_insensitively_on_the_wire() -> None:
    routes = {
        "/": Route(
            body=HTML,
            headers=HTML_HEADERS,
            repeated_headers=(("x-robots-tag", "noindex"), ("X-ROBOTS-TAG", "nofollow")),
        )
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/"))
    assert isinstance(result, PageFetchOutcome)
    assert result.x_robots_tag == ("noindex", "nofollow")


def test_the_header_is_read_off_the_final_response_and_not_a_redirect() -> None:
    """A directive on a hop we passed through is not a directive on the page we analysed."""
    routes = {
        "/from": Route(
            status=302,
            headers={"Location": "/final"},
            repeated_headers=(("X-Robots-Tag", "noindex"),),
        ),
        "/final": Route(body=HTML, headers=HTML_HEADERS),
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/from"))

    assert isinstance(result, PageFetchOutcome)
    assert result.redirect_count == 1, "canary: the redirect must actually have been followed"
    assert result.x_robots_tag == ()


# --- a failure carries a category and nothing else --------------------------------------------


def test_a_failure_carries_no_free_text_at_all() -> None:
    """Whatever a provider or our runtime said, only the category survives."""

    def failing(host: str, port: int) -> list[str]:
        raise OSError("connect to 10.1.2.3 failed: /var/secrets/token.pem unreadable")

    result = SafePageFetcher(policy=PublicTargetPolicy(resolve=failing)).fetch("https://x.example/")
    assert isinstance(result, PageFetchFailure)
    rendered = repr(result)
    for fragment in ("10.1.2.3", "token.pem", "/var/secrets", "unreadable"):
        assert fragment not in rendered, f"leaked {fragment!r}"


# --- the read itself is bounded, not merely the value we keep ---------------------------------


def test_the_body_is_read_under_a_bound_rather_than_in_full(monkeypatch) -> None:
    """Bounding the value we keep is not the same as bounding what we pull off the socket.

    A fetcher that read an unbounded body and then sliced it would satisfy every assertion
    about the resulting record while still letting a hostile server decide our memory use.
    """
    import http.client

    requested: list[int | None] = []
    original = http.client.HTTPResponse.read

    def spy(self, amt=None):
        requested.append(amt)
        return original(self, amt)

    monkeypatch.setattr(http.client.HTTPResponse, "read", spy)

    big = b"a" * 200_000
    with ControlledHttpServer({"/": Route(body=big, headers=HTML_HEADERS)}) as server:
        result = fetcher(limits=FetchLimits(max_response_bytes=1_000)).fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome)
    assert requested, "canary: the spy saw no read at all"
    assert all(amt is not None for amt in requested), (
        f"the body was read without a bound: read({requested})"
    )
    assert max(amt for amt in requested if amt is not None) <= 1_001


# --- TLS pins the address and still verifies the hostname ---------------------------------------


def test_the_tls_connection_dials_the_pinned_address_and_verifies_the_hostname(monkeypatch) -> None:
    """The two halves of the rebinding defence, asserted separately.

    Dialling the pinned address is what closes the gap between check and connect; verifying
    the certificate against the *hostname* is what stops that pinning from silently disabling
    TLS identity. A fetcher that did the first without the second would be worse than neither.
    """
    import socket as socket_module

    from pxapi.adapters.web.page_fetcher import PinnedHTTPSConnection

    dialled: list[tuple[str, int]] = []
    wrapped: list[str] = []

    class FakeSocket:
        def close(self) -> None: ...

    def fake_create_connection(address, timeout=None, *args, **kwargs):
        dialled.append(address)
        return FakeSocket()

    class FakeContext:
        def wrap_socket(self, sock, server_hostname=None):
            wrapped.append(server_hostname)
            return sock

    monkeypatch.setattr(socket_module, "create_connection", fake_create_connection)

    connection = PinnedHTTPSConnection(
        "example.test",
        "93.184.216.34",
        443,
        5.0,
        FakeContext(),  # type: ignore[arg-type]
    )
    connection.connect()

    assert dialled == [("93.184.216.34", 443)], "the socket must dial the validated address"
    assert wrapped == ["example.test"], "the certificate must still be checked against the name"


def test_the_plain_connection_also_dials_the_pinned_address(monkeypatch) -> None:
    import socket as socket_module

    from pxapi.adapters.web.page_fetcher import PinnedHTTPConnection

    dialled: list[tuple[str, int]] = []

    def fake_create_connection(address, timeout=None, *args, **kwargs):
        dialled.append(address)
        return object()

    monkeypatch.setattr(socket_module, "create_connection", fake_create_connection)

    PinnedHTTPConnection("example.test", "93.184.216.34", 80, 5.0).connect()
    assert dialled == [("93.184.216.34", 80)]


# --- content encoding ---------------------------------------------------------------------


def _gzipped(payload: bytes) -> bytes:
    import gzip

    return gzip.compress(payload)


def _deflated(payload: bytes) -> bytes:
    import zlib

    return zlib.compress(payload)


def test_a_gzip_encoded_body_is_decoded() -> None:
    """Servers compress even when asked not to, so this is the ordinary case, not an edge one."""
    routes = {
        "/": Route(
            body=_gzipped(HTML),
            headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
        )
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome)
    assert result.body == HTML
    assert result.undecodable is False


def test_a_deflate_encoded_body_is_decoded() -> None:
    routes = {
        "/": Route(
            body=_deflated(HTML),
            headers={"Content-Type": "text/html", "Content-Encoding": "deflate"},
        )
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/"))
    assert isinstance(result, PageFetchOutcome)
    assert result.body == HTML


@pytest.mark.parametrize("encoding", ["br", "zstd", "gzip, br", "exotic"])
def test_an_encoding_we_cannot_decode_is_reported_rather_than_guessed(encoding: str) -> None:
    """We do not hold the document, and saying so is the only honest answer."""
    routes = {
        "/": Route(
            body=b"\x00\x01\x02compressed",
            headers={"Content-Type": "text/html", "Content-Encoding": encoding},
        )
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome)
    assert result.undecodable is True
    assert result.body == b"", "an undecodable body must not be handed on as if it were the page"
    assert result.status_code == 200, "the transport facts are still real"


def test_an_identity_encoding_is_passed_through() -> None:
    routes = {
        "/": Route(body=HTML, headers={"Content-Type": "text/html", "Content-Encoding": "identity"})
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher().fetch(server.url("/"))
    assert isinstance(result, PageFetchOutcome)
    assert result.body == HTML
    assert result.undecodable is False


def test_a_decompression_bomb_is_bounded_like_any_other_body() -> None:
    """A small compressed body can inflate without limit; the output is capped too."""
    bomb = _gzipped(b"a" * 5_000_000)
    routes = {
        "/": Route(body=bomb, headers={"Content-Type": "text/html", "Content-Encoding": "gzip"})
    }
    with ControlledHttpServer(routes) as server:
        result = fetcher(limits=FetchLimits(max_response_bytes=10_000)).fetch(server.url("/"))

    assert isinstance(result, PageFetchOutcome)
    assert len(result.body) <= 10_000, "decompression must not exceed the byte bound"
    assert result.truncated is True
