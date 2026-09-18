"""The static-HTTP discovery provider, against a real HTTP server on loopback.

Every source state PXAPI-19 names is produced here by a real server answering real requests, so
the outcome recorded is the one the adapter reached through the fetcher, the policy and the
parser — not one a fake was told to return. The loopback policy is the test-only subclass the
fetcher's own tests use; the shipped policy still refuses loopback, which the bootstrap tests at
the bottom prove against the real ``PublicTargetPolicy``.
"""

from __future__ import annotations

import gzip
from collections.abc import Callable
from typing import Any

import pytest

from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.adapters.web.site_discovery import HttpSiteDiscovery
from pxapi.adapters.web.target_policy import PublicTargetPolicy
from pxapi.config.discovery_limits import DiscoveryLimits
from pxapi.config.fetch_limits import FetchLimits
from pxapi.domain.site_discovery import BootstrapFailure, DiscoveryReport
from tests.adapters.http_test_server import (
    ControlledHttpServer,
    LoopbackTargetPolicy,
    Route,
    loopback_policy,
)

HTML = {"Content-Type": "text/html; charset=utf-8"}
TEXT = {"Content-Type": "text/plain"}
XML = {"Content-Type": "application/xml"}
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def home(*links: tuple[str, str]) -> Route:
    anchors = "".join(f'<a href="{href}">{label}</a>' for href, label in links)
    return Route(body=f"<html><body>{anchors}</body></html>".encode(), headers=HTML)


def urlset(*locs: str) -> Route:
    entries = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
    return Route(body=f'<?xml version="1.0"?><urlset {NS}>{entries}</urlset>'.encode(), headers=XML)


def robots(*lines: str) -> Route:
    return Route(body=("\n".join(lines) + "\n").encode(), headers=TEXT)


class Recorder:
    """A resolver that records every name it was asked for and answers loopback."""

    def __init__(self) -> None:
        self.hosts: list[str] = []

    def __call__(self, host: str, port: int) -> list[str]:
        self.hosts.append(host)
        return ["127.0.0.1"]


def discover(
    routes_for: Callable[[str], dict[str, Route]],
    *,
    limits: DiscoveryLimits | None = None,
    fetch_limits: FetchLimits | None = None,
    policy: PublicTargetPolicy | None = None,
    fetcher_factory: Any = None,
    clock: Any = None,
) -> tuple[DiscoveryReport, str]:
    routes: dict[str, Route] = {}
    with ControlledHttpServer(routes) as server:
        routes.update(routes_for(server.base_url))
        kwargs: dict[str, Any] = {"policy": policy or loopback_policy()}
        if limits is not None:
            kwargs["limits"] = limits
        if fetch_limits is not None:
            kwargs["fetch_limits"] = fetch_limits
        if fetcher_factory is not None:
            kwargs["fetcher_factory"] = fetcher_factory
        if clock is not None:
            kwargs["clock"] = clock
        report = HttpSiteDiscovery(**kwargs).discover(server.base_url + "/")
    return report, server.base_url


def outcomes(report: DiscoveryReport) -> dict[str, str]:
    return {attempt.source_id: attempt.outcome.value for attempt in report.attempts}


def forms(report: DiscoveryReport, source: str) -> list[str]:
    return [o.observed_form for o in report.observations if o.source_id == source]


# --- the seed and its links -----------------------------------------------------------------


def test_the_origin_is_established_and_the_seed_reported_as_an_observation() -> None:
    report, base = discover(lambda b: {"/": home()})
    assert report.target_origin == base + "/"
    assert forms(report, "CANONICAL_SEED") == [base + "/"]
    assert outcomes(report)["CANONICAL_SEED"] == "USED"


def test_same_origin_links_become_observations_and_nothing_else_does() -> None:
    report, base = discover(
        lambda b: {
            "/": home(
                ("/leistungen", "Leistungen"),
                ("https://facebook.com/x", "fb"),
                ("mailto:a@b.test", "mail"),
                ("javascript:void(0)", "js"),
                (b.replace("http://", "http://user:pw@") + "/geheim", "cred"),
            )
        }
    )
    assert forms(report, "SAME_ORIGIN_PAGE_LINKS") == [base + "/leistungen"]
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "USED"


def test_a_link_carries_its_bounded_label_to_the_boundary() -> None:
    report, _ = discover(lambda b: {"/": home(("/seite-7", "  Kontakt \n aufnehmen "))})
    (link,) = [o for o in report.observations if o.source_id == "SAME_ORIGIN_PAGE_LINKS"]
    assert link.label == "Kontakt aufnehmen"


def test_a_seed_whose_links_all_leave_the_origin_was_read_and_admitted_nothing() -> None:
    """USED with zero admitted, not EMPTY: the page did declare links, just none of this kind,
    and the contract reserves EMPTY for a source that was well formed and declared nothing."""
    report, _ = discover(lambda b: {"/": home(("https://elsewhere.test/", "x"))})
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "USED"
    assert forms(report, "SAME_ORIGIN_PAGE_LINKS") == []


def test_a_seed_document_without_any_link_is_empty() -> None:
    report, _ = discover(lambda b: {"/": home()})
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "EMPTY"


def test_the_link_budget_stops_the_read_and_says_so() -> None:
    limits = DiscoveryLimits(max_page_links=2)
    links = [(f"/p{i}", "x") for i in range(5)]
    report, _ = discover(lambda b: {"/": home(*links)}, limits=limits)
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "BUDGET_EXHAUSTED"
    assert len(forms(report, "SAME_ORIGIN_PAGE_LINKS")) == 2


@pytest.mark.parametrize(
    ("route", "outcome"),
    [
        (Route(status=404, body=b"", headers=HTML), "ABSENT"),
        (Route(status=500, body=b"", headers=HTML), "PROVIDER_FAILURE"),
        (Route(body=b"plain", headers=TEXT), "MALFORMED"),
    ],
)
def test_a_seed_that_is_not_a_readable_page_still_establishes_the_origin(
    route: Route, outcome: str
) -> None:
    """A response arrived from a safe public origin: that is the bootstrap. What the page is
    becomes a neutral link-source state, never a verdict and never a missing inventory."""
    report, base = discover(lambda b: {"/": route})
    assert report.target_origin == base + "/"
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == outcome


# --- robots.txt -------------------------------------------------------------------------


def test_a_missing_robots_file_is_absent_and_the_conventional_sitemap_is_tried() -> None:
    report, base = discover(lambda b: {"/": home(), "/sitemap.xml": urlset(b + "/a")})
    assert outcomes(report)["ROBOTS_DECLARATION"] == "ABSENT"
    assert outcomes(report)["SITEMAP"] == "USED"
    assert forms(report, "SITEMAP") == [base + "/a"]


def test_a_robots_file_without_a_sitemap_declaration_says_exactly_that() -> None:
    report, _ = discover(
        lambda b: {"/": home(), "/robots.txt": robots("User-agent: *", "Disallow:")}
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "NO_SITEMAP_DECLARATION"


def test_a_same_origin_sitemap_declaration_is_followed() -> None:
    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/karte.xml"),
            "/karte.xml": urlset(b + "/leistungen", b + "/kontakt"),
        }
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "USED"
    assert outcomes(report)["SITEMAP"] == "USED"
    assert forms(report, "SITEMAP") == [base + "/leistungen", base + "/kontakt"]


def test_robots_directives_other_than_sitemap_are_never_applied() -> None:
    """``Disallow: /`` would forbid everything under a compliance reading; this slice claims
    none, so the declared sitemap is read and nothing is filtered by the directive."""
    report, base = discover(
        lambda b: {
            "/": home(("/leistungen", "L")),
            "/robots.txt": robots(
                "User-agent: *", "Disallow: /", "Crawl-delay: 99", f"Sitemap: {b}/s.xml"
            ),
            "/s.xml": urlset(b + "/kontakt"),
        }
    )
    assert forms(report, "SITEMAP") == [base + "/kontakt"]
    assert forms(report, "SAME_ORIGIN_PAGE_LINKS") == [base + "/leistungen"]


def test_an_off_origin_sitemap_declaration_is_refused_without_ever_being_resolved() -> None:
    recorder = Recorder()
    report, _ = discover(
        lambda b: {"/": home(), "/robots.txt": robots("Sitemap: http://evil.test/sitemap.xml")},
        policy=LoopbackTargetPolicy(resolve=recorder),
    )
    assert outcomes(report)["REFUSED_SITEMAP"] == "TARGET_POLICY_REFUSED"
    assert "evil.test" not in recorder.hosts
    assert not any("evil.test" in o.observed_form for o in report.observations)
    # A refused declaration never takes a sitemap slot: it is not planned at all, so the
    # conventional /sitemap.xml is still tried and its own state is what SITEMAP reports.
    # Planning it and letting the scope refuse it later would leave SITEMAP naming the
    # refusal instead — a second, downstream layer doing the first layer's job.
    assert outcomes(report)["SITEMAP"] == "ABSENT"


def test_a_repeated_declaration_is_fetched_once() -> None:
    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/s.xml", f"Sitemap: {b}/s.xml"),
            "/s.xml": urlset(b + "/x"),
        }
    )
    assert forms(report, "SITEMAP") == [base + "/x"]


@pytest.mark.parametrize(
    ("route", "outcome"),
    [
        (Route(body=b"<!doctype html><html><p>not found</p></html>", headers=HTML), "MALFORMED"),
        (Route(body=b"<html><p>soft 404</p></html>", headers=TEXT), "MALFORMED"),
        (Route(status=500, body=b"", headers=TEXT), "PROVIDER_FAILURE"),
        (Route(status=403, body=b"", headers=TEXT), "PROVIDER_FAILURE"),
    ],
)
def test_a_robots_file_that_cannot_be_read_is_a_neutral_state(route: Route, outcome: str) -> None:
    report, _ = discover(lambda b: {"/": home(), "/robots.txt": route})
    assert outcomes(report)["ROBOTS_DECLARATION"] == outcome


def test_a_robots_redirect_leaving_the_origin_is_refused_before_any_lookup() -> None:
    recorder = Recorder()
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": Route(status=302, headers={"Location": "http://evil.test/robots.txt"}),
        },
        policy=LoopbackTargetPolicy(resolve=recorder),
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "TARGET_POLICY_REFUSED"
    assert "evil.test" not in recorder.hosts


# --- sitemaps -----------------------------------------------------------------------------


def test_a_missing_sitemap_is_absent() -> None:
    report, _ = discover(lambda b: {"/": home()})
    assert outcomes(report)["SITEMAP"] == "ABSENT"


def test_a_malformed_sitemap_admits_nothing() -> None:
    """Even the complete entry that came before the error is discarded: a source reported
    MALFORMED is structurally pinned to zero admitted, so keeping it would contradict itself."""
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/sitemap.xml": Route(
                body=f"<urlset><url><loc>{b}/ok</loc></url><url><loc>x".encode(), headers=XML
            ),
        }
    )
    assert outcomes(report)["SITEMAP"] == "MALFORMED"
    assert forms(report, "SITEMAP") == []


def test_a_document_that_is_not_a_sitemap_is_malformed() -> None:
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/sitemap.xml": Route(body=b"<?xml version='1.0'?><rss/>", headers=XML),
        }
    )
    assert outcomes(report)["SITEMAP"] == "MALFORMED"


def test_an_empty_valid_sitemap_is_empty() -> None:
    report, _ = discover(lambda b: {"/": home(), "/sitemap.xml": urlset()})
    assert outcomes(report)["SITEMAP"] == "EMPTY"


def test_a_sitemap_declaring_entities_is_not_parsed_at_all() -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>&lol2;</loc></url></urlset>'
    )
    report, _ = discover(lambda b: {"/": home(), "/sitemap.xml": Route(body=bomb, headers=XML)})
    assert outcomes(report)["SITEMAP"] == "MALFORMED"
    assert forms(report, "SITEMAP") == []


def test_a_gzip_sitemap_is_inflated_and_read() -> None:
    def routes(b: str) -> dict[str, Route]:
        xml = urlset(b + "/gz").body
        return {
            "/": home(),
            "/sitemap.xml": Route(
                body=gzip.compress(xml), headers={"Content-Type": "application/x-gzip"}
            ),
        }

    report, base = discover(routes)
    assert forms(report, "SITEMAP") == [base + "/gz"]


def test_a_sitemap_index_is_followed_and_its_off_origin_children_refused() -> None:
    def routes(b: str) -> dict[str, Route]:
        index = (
            f'<?xml version="1.0"?><sitemapindex {NS}><sitemap><loc>{b}/child.xml</loc></sitemap>'
            f"<sitemap><loc>http://evil.test/c.xml</loc></sitemap></sitemapindex>"
        )
        return {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/index.xml"),
            "/index.xml": Route(body=index.encode(), headers=XML),
            "/child.xml": urlset(b + "/aus-dem-index"),
        }

    report, base = discover(routes)
    assert forms(report, "SITEMAP") == [base + "/aus-dem-index"]
    assert outcomes(report)["SITEMAP"] == "USED"
    assert outcomes(report)["REFUSED_SITEMAP"] == "TARGET_POLICY_REFUSED"


def test_an_off_origin_sitemap_entry_is_recorded_for_the_domain_to_exclude() -> None:
    report, _ = discover(lambda b: {"/": home(), "/sitemap.xml": urlset("https://cdn.test/x")})
    assert forms(report, "SITEMAP") == ["https://cdn.test/x"]


# --- every bound is ours ------------------------------------------------------------------


def test_a_sitemap_cut_by_our_byte_bound_contributes_what_was_read() -> None:
    locs = [f"http://127.0.0.1:1/p{i:02d}" for i in range(20)]
    report, _ = discover(
        lambda b: {"/": home(), "/sitemap.xml": urlset(*locs)},
        fetch_limits=FetchLimits(max_response_bytes=400),
    )
    assert outcomes(report)["SITEMAP"] == "BUDGET_EXHAUSTED"
    assert 1 <= len(forms(report, "SITEMAP")) < len(locs)


def test_the_entry_budget_stops_the_sitemap_read() -> None:
    report, _ = discover(
        lambda b: {"/": home(), "/sitemap.xml": urlset(*(f"{b}/p{i}" for i in range(5)))},
        limits=DiscoveryLimits(max_sitemap_entries=2),
    )
    assert outcomes(report)["SITEMAP"] == "BUDGET_EXHAUSTED"
    assert len(forms(report, "SITEMAP")) == 2


def test_the_document_budget_stops_the_sitemap_queue() -> None:
    def routes(b: str) -> dict[str, Route]:
        found = {"/": home(), "/robots.txt": robots(*(f"Sitemap: {b}/s{i}.xml" for i in range(3)))}
        found |= {f"/s{i}.xml": urlset(f"{b}/from-{i}") for i in range(3)}
        return found

    report, base = discover(routes, limits=DiscoveryLimits(max_sitemap_documents=2))
    assert outcomes(report)["SITEMAP"] == "BUDGET_EXHAUSTED"
    assert forms(report, "SITEMAP") == [base + "/from-0", base + "/from-1"]


def test_the_request_budget_stops_discovery_before_the_sitemap() -> None:
    report, _ = discover(
        lambda b: {"/": home(), "/sitemap.xml": urlset(b + "/x")},
        limits=DiscoveryLimits(max_requests=2),
    )
    assert outcomes(report)["SITEMAP"] == "BUDGET_EXHAUSTED"
    assert forms(report, "SITEMAP") == []


def test_the_discovery_deadline_turns_every_remaining_source_into_a_timeout() -> None:
    class Clock:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    clock = Clock()

    def factory(scope: Any) -> SafePageFetcher:
        if scope is not None:
            clock.now = 10_000.0  # the bootstrap is done; the run's own deadline has passed
        return SafePageFetcher(policy=loopback_policy(), clock=clock, scope=scope)

    report, _ = discover(lambda b: {"/": home(("/a", "a"))}, fetcher_factory=factory, clock=clock)
    assert outcomes(report)["ROBOTS_DECLARATION"] == "TIMEOUT"
    assert outcomes(report)["SITEMAP"] == "TIMEOUT"
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "USED"


# --- the bootstrap ------------------------------------------------------------------------


def test_a_bootstrap_redirect_establishes_the_origin_it_arrives_at() -> None:
    target: dict[str, Route] = {}
    with ControlledHttpServer(target) as other:
        target.update({"/": home(), "/robots.txt": robots("User-agent: *")})
        report, _ = discover(
            lambda b: {"/": Route(status=301, headers={"Location": other.url("/")})}
        )
    assert report.target_origin == other.base_url + "/"
    assert outcomes(report)["ROBOTS_DECLARATION"] == "NO_SITEMAP_DECLARATION"


def test_once_established_the_origin_is_never_left_even_for_the_original_host() -> None:
    first: dict[str, Route] = {}
    with ControlledHttpServer(first) as original:
        first.update({"/robots.txt": robots(f"Sitemap: {original.url('/s.xml')}")})
        report, _ = discover(
            lambda b: {
                "/": home(),
                "/robots.txt": Route(status=302, headers={"Location": original.url("/robots.txt")}),
            }
        )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "TARGET_POLICY_REFUSED"


@pytest.mark.parametrize(
    ("url", "resolved"),
    [
        ("http://127.0.0.1/", None),
        ("http://[::1]/", None),
        ("http://[::ffff:127.0.0.1]/", None),
        ("http://169.254.169.254/latest/meta-data/", None),
        ("http://10.0.0.8/", None),
        ("https://intranet.example/", ["10.0.0.5"]),
        ("https://split.example/", ["93.184.216.34", "192.168.1.1"]),
        ("https://metadata.example/", ["169.254.169.254"]),
    ],
)
def test_the_shipped_policy_refuses_every_non_public_bootstrap_target(
    url: str, resolved: list[str] | None
) -> None:
    policy = PublicTargetPolicy(resolve=lambda host, port: resolved or [])
    report = HttpSiteDiscovery(policy=policy).discover(url)
    assert report.target_origin is None
    assert report.bootstrap_failure is BootstrapFailure.TARGET_REFUSED
    assert report.observations == () and report.attempts == ()


def test_a_credential_bearing_target_is_refused_before_any_lookup() -> None:
    recorder = Recorder()
    report = HttpSiteDiscovery(policy=PublicTargetPolicy(resolve=recorder)).discover(
        "https://user:secret@example.com/"
    )
    assert report.bootstrap_failure is BootstrapFailure.TARGET_REFUSED
    assert recorder.hosts == []


def test_a_target_that_does_not_resolve_is_unreachable_not_refused() -> None:
    def failing(host: str, port: int) -> list[str]:
        raise OSError("no such host")

    report = HttpSiteDiscovery(policy=PublicTargetPolicy(resolve=failing)).discover(
        "https://does-not-resolve.example/"
    )
    assert report.bootstrap_failure is BootstrapFailure.UNREACHABLE
    assert report.target_origin is None


def test_once_the_entry_budget_is_spent_no_further_sitemap_is_fetched() -> None:
    """A document read only to be discarded is work the bound exists to prevent. Measured on
    rfc-editor.org: the 500-entry budget was spent inside the first child sitemap, and the
    second (495 KB) was still fetched before this guard existed."""
    fetched: list[str] = []

    class Recording:
        def __init__(self, inner: SafePageFetcher) -> None:
            self.inner = inner

        def fetch(self, url: str) -> Any:
            fetched.append(url)
            return self.inner.fetch(url)

    def routes(b: str) -> dict[str, Route]:
        return {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/a.xml", f"Sitemap: {b}/b.xml"),
            "/a.xml": urlset(*(f"{b}/a{i}" for i in range(3))),
            "/b.xml": urlset(*(f"{b}/b{i}" for i in range(3))),
        }

    report, base = discover(
        routes,
        limits=DiscoveryLimits(max_sitemap_entries=2),
        fetcher_factory=lambda scope: Recording(
            SafePageFetcher(policy=loopback_policy(), scope=scope)
        ),
    )
    assert outcomes(report)["SITEMAP"] == "BUDGET_EXHAUSTED"
    assert forms(report, "SITEMAP") == [base + "/a0", base + "/a1"]
    assert base + "/a.xml" in fetched
    assert base + "/b.xml" not in fetched


def recording(fetched: list[str]) -> Any:
    """A fetcher factory that records every URL a discovery fetch was asked for."""

    class Recording:
        def __init__(self, inner: SafePageFetcher) -> None:
            self.inner = inner

        def fetch(self, url: str) -> Any:
            fetched.append(url)
            return self.inner.fetch(url)

    return lambda scope: Recording(SafePageFetcher(policy=loopback_policy(), scope=scope))


def test_a_backslash_href_a_browser_reads_as_another_host_is_never_admitted() -> None:
    """``/\\user:pw@evil.test/`` resolves same-origin under RFC 3986 and is a credentialed URL on
    another host under WHATWG. A form the two standards disagree about has no single identity."""
    report, base = discover(
        lambda b: {
            "/": home(
                ("/\\user:pw@evil.test/steal", "x"), ("/\\evil.test/x", "y"), ("/kontakt", "K")
            )
        }
    )
    link_forms = forms(report, "SAME_ORIGIN_PAGE_LINKS")
    assert link_forms == [base + "/kontakt"]
    assert not any(
        "evil.test" in o.observed_form or "\\" in o.observed_form for o in report.observations
    )


def test_a_bootstrap_the_target_answered_but_we_could_not_follow_is_a_provider_failure() -> None:
    """A redirect loop means the target was reached and answered; UNREACHABLE would be false."""
    with ControlledHttpServer({"/": Route(status=302, headers={"Location": "/"})}) as server:
        report = HttpSiteDiscovery(policy=loopback_policy()).discover(server.url("/"))
    assert report.target_origin is None
    assert report.bootstrap_failure is BootstrapFailure("PROVIDER_FAILURE")


def test_a_seed_that_declares_no_content_type_is_still_read_for_links() -> None:
    body = b'<html><body><a href="/kontakt">K</a></body></html>'
    report, base = discover(lambda b: {"/": Route(body=body, headers={})})
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "USED"
    assert forms(report, "SAME_ORIGIN_PAGE_LINKS") == [base + "/kontakt"]


def test_a_failed_sitemap_is_not_hidden_behind_an_empty_sibling() -> None:
    """EMPTY says *well formed, declared nothing* about the whole source; one document failed."""
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/leer.xml", f"Sitemap: {b}/kaputt.xml"),
            "/leer.xml": urlset(),
            "/kaputt.xml": Route(status=500, headers=XML),
        }
    )
    assert outcomes(report)["SITEMAP"] == "PROVIDER_FAILURE"


def test_a_page_listed_inside_a_sitemap_index_is_not_fetched_as_a_sitemap() -> None:
    fetched: list[str] = []

    def routes(b: str) -> dict[str, Route]:
        index = (
            f'<?xml version="1.0"?><sitemapindex {NS}>'
            f"<url><loc>{b}/kontakt</loc></url></sitemapindex>"
        )
        return {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/idx.xml"),
            "/idx.xml": Route(body=index.encode(), headers=XML),
            "/kontakt": home(),
        }

    report, base = discover(routes, fetcher_factory=recording(fetched))
    assert base + "/kontakt" not in fetched
    assert outcomes(report)["SITEMAP"] == "EMPTY"


def test_a_repeated_sitemap_entry_costs_nothing_against_the_entry_budget() -> None:
    """Duplication is not a penalty: the same written form five times is one entry."""
    report, base = discover(
        lambda b: {"/": home(), "/sitemap.xml": urlset(*([b + "/a"] * 5), b + "/b")},
        limits=DiscoveryLimits(max_sitemap_entries=2),
    )
    assert set(forms(report, "SITEMAP")) == {base + "/a", base + "/b"}
    assert outcomes(report)["SITEMAP"] == "USED"


def test_a_sitemap_redirected_out_of_the_origin_stays_visible_beside_one_that_was_read() -> None:
    recorder = Recorder()
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/a.xml", f"Sitemap: {b}/b.xml"),
            "/a.xml": urlset(b + "/x"),
            "/b.xml": Route(status=302, headers={"Location": "http://evil.test/s.xml"}),
        },
        policy=LoopbackTargetPolicy(resolve=recorder),
    )
    assert outcomes(report)["SITEMAP"] == "USED"
    assert outcomes(report)["REFUSED_SITEMAP"] == "TARGET_POLICY_REFUSED"
    assert "evil.test" not in recorder.hosts


class Rebinding(LoopbackTargetPolicy):
    """A name that answers loopback for the bootstrap and a private address ever after."""

    def __init__(self) -> None:
        self.calls = 0
        super().__init__(resolve=self._resolve)

    def _resolve(self, host: str, port: int) -> list[str]:
        self.calls += 1
        return ["127.0.0.1"] if self.calls == 1 else ["10.0.0.5"]


def test_every_discovery_fetch_reruns_the_address_policy_so_a_rebound_name_is_refused() -> None:
    """The scope narrows by origin; it never replaces the policy. A name that resolved publicly
    for the bootstrap and privately a moment later is refused on every later fetch."""
    policy = Rebinding()
    routes = {"/": home(), "/robots.txt": robots("Sitemap: /s.xml"), "/s.xml": urlset()}
    with ControlledHttpServer(routes) as server:
        report = HttpSiteDiscovery(policy=policy).discover(f"http://site.test:{server.port}/")
    assert report.target_origin == f"http://site.test:{server.port}/"
    assert outcomes(report)["ROBOTS_DECLARATION"] == "TARGET_POLICY_REFUSED"
    assert outcomes(report)["SITEMAP"] == "TARGET_POLICY_REFUSED"
    assert policy.calls >= 3


def test_a_seed_cut_by_our_byte_bound_is_a_bounded_read_not_a_complete_one() -> None:
    padding = "<p>" + "x" * 400 + "</p>"
    report, _ = discover(
        lambda b: {
            "/": Route(body=f'<html><a href="/a">A</a>{padding}</html>'.encode(), headers=HTML)
        },
        fetch_limits=FetchLimits(max_response_bytes=120),
    )
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "BUDGET_EXHAUSTED"


def test_a_robots_file_cut_by_our_byte_bound_is_a_bounded_read() -> None:
    report, _ = discover(
        lambda b: {
            "/": Route(body=b"<html></html>", headers=HTML),
            "/robots.txt": robots("Sitemap: /s.xml", "#" * 400),
        },
        fetch_limits=FetchLimits(max_response_bytes=120),
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "BUDGET_EXHAUSTED"


def test_a_gzip_sitemap_is_inflated_only_up_to_our_byte_bound() -> None:
    """A few hundred compressed bytes can inflate to hundreds of kilobytes. The inflation stops at
    the same bound as the read, and what could not be read is reported as our bound."""

    def routes(b: str) -> dict[str, Route]:
        xml = urlset(*([b + "/p"] * 20000)).body
        body = gzip.compress(xml)
        assert len(body) < 4000 < len(xml)
        return {
            "/": home(),
            "/sitemap.xml": Route(body=body, headers={"Content-Type": "application/x-gzip"}),
        }

    report, base = discover(routes, fetch_limits=FetchLimits(max_response_bytes=4000))
    assert outcomes(report)["SITEMAP"] == "BUDGET_EXHAUSTED"
    assert set(forms(report, "SITEMAP")) == {base + "/p"}


def test_a_source_the_server_answers_too_slowly_is_a_timeout() -> None:
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": Route(body=b"Sitemap: /s.xml\n", headers=TEXT, delay=0.6),
        },
        fetch_limits=FetchLimits(read_timeout_seconds=0.2, total_deadline_seconds=5.0),
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "TIMEOUT"


def test_a_bootstrap_the_server_answers_too_slowly_is_a_timeout_not_unreachable() -> None:
    with ControlledHttpServer(
        {"/": Route(body=b"<html></html>", headers=HTML, delay=0.6)}
    ) as server:
        report = HttpSiteDiscovery(
            policy=loopback_policy(),
            fetch_limits=FetchLimits(read_timeout_seconds=0.2, total_deadline_seconds=5.0),
        ).discover(server.url("/"))
    assert report.target_origin is None
    assert report.bootstrap_failure is BootstrapFailure.TIMEOUT


# --- C-PXAPI-013: a malformed link is one link, never the whole source -----------------------


def test_one_unresolvable_href_does_not_cost_the_page_its_other_links() -> None:
    """The defect this closes: ``read_links`` resolved its targets *outside* its own failure
    isolation, so a single ``<a href="http://[::1">`` raised out of the reader, past the
    ``HtmlUnreadable`` handler, into ``_guarded`` — and the whole SAME_ORIGIN_PAGE_LINKS source
    became RUNTIME_ERROR with nothing admitted, discarding links the document plainly carried."""
    report, base = discover(
        lambda b: {
            "/": home(("/leistungen", "Leistungen"), ("http://[::1", "kaputt"), ("/kontakt", "K"))
        }
    )
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "USED"
    assert forms(report, "SAME_ORIGIN_PAGE_LINKS") == [base + "/leistungen", base + "/kontakt"]


def test_an_unusable_base_href_does_not_make_the_documents_links_disappear() -> None:
    report, base = discover(
        lambda b: {
            "/": Route(
                body=b'<html><base href="https://[not-an-address]/"><body>'
                b'<a href="/leistungen">L</a><a href="/kontakt">K</a></body></html>',
                headers=HTML,
            )
        }
    )
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "USED"
    assert forms(report, "SAME_ORIGIN_PAGE_LINKS") == [base + "/leistungen", base + "/kontakt"]


def test_an_unresolvable_href_is_never_admitted_merely_to_preserve_its_siblings() -> None:
    """Isolation preserves siblings; it never widens what may be persisted.

    A document whose *only* anchor names no readable target therefore admits nothing, and says
    so with ``EMPTY`` rather than with the ``RUNTIME_ERROR`` it used to report. Both are
    non-admitting outcomes pinned to zero candidates, so the inventory is unchanged; what
    changes is that the run no longer claims our own runtime failed on a page it read fine.
    Which of the two zero-admitting states fits this narrow case is not what C-PXAPI-013 names,
    and is left exactly as the existing ``USED``/``EMPTY`` rule decides it.
    """
    report, _ = discover(lambda b: {"/": home(("http://[::1", "kaputt"))})
    assert forms(report, "SAME_ORIGIN_PAGE_LINKS") == []
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "EMPTY"


def test_a_document_our_decoder_cannot_read_is_still_our_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Document-wide failure is untouched by the per-link isolation: it stays RUNTIME_ERROR."""
    from pxapi.adapters.web import html_links

    def broken(body: bytes, charset: str | None) -> str:
        raise ValueError("decoder broke")

    monkeypatch.setattr(html_links, "decode_body", broken)
    report, _ = discover(lambda b: {"/": home(("/leistungen", "L"))})
    assert outcomes(report)["SAME_ORIGIN_PAGE_LINKS"] == "RUNTIME_ERROR"
    assert forms(report, "SAME_ORIGIN_PAGE_LINKS") == []


# --- NF-5: a malformed Sitemap: declaration is one declaration, never the whole source -------
#
# The same tolerant-input defect C-PXAPI-013 closes for document links, in the sibling reader of
# the same theme. ``_robots`` resolved every declaration with an unguarded
# ``urljoin(response.final_url, value.strip())``, so one value the URL parser will not read —
# ``http://[`` and its kind — raised ``ValueError`` out of ``_robots``, was caught only by the
# module-level ``_guarded``, and turned the whole ROBOTS_DECLARATION source into RUNTIME_ERROR
# with zero declarations: the run claimed *our* runtime failed on a robots.txt it read perfectly,
# and every valid sibling declaration — with the sitemap and the pages behind it — was discarded.

BAD_DECLARATION = "Sitemap: http://[::1"


def test_a_malformed_sitemap_declaration_before_a_valid_one_does_not_discard_it() -> None:
    """Scenario A."""
    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(BAD_DECLARATION, f"Sitemap: {b}/karte.xml"),
            "/karte.xml": urlset(b + "/leistungen"),
        }
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "USED"
    assert outcomes(report)["SITEMAP"] == "USED"
    assert forms(report, "SITEMAP") == [base + "/leistungen"]


def test_a_malformed_sitemap_declaration_between_two_valid_ones_discards_neither() -> None:
    """Scenario B — the ordering the brief names explicitly: both siblings must survive."""
    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(
                f"Sitemap: {b}/one.xml", BAD_DECLARATION, f"Sitemap: {b}/two.xml"
            ),
            "/one.xml": urlset(b + "/eins"),
            "/two.xml": urlset(b + "/zwei"),
        }
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "USED"
    assert outcomes(report)["SITEMAP"] == "USED"
    assert forms(report, "SITEMAP") == [base + "/eins", base + "/zwei"]


def test_a_malformed_sitemap_declaration_after_a_valid_one_does_not_discard_it() -> None:
    """Scenario C."""
    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(f"Sitemap: {b}/karte.xml", BAD_DECLARATION),
            "/karte.xml": urlset(b + "/kontakt"),
        }
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "USED"
    assert outcomes(report)["SITEMAP"] == "USED"
    assert forms(report, "SITEMAP") == [base + "/kontakt"]


def test_a_malformed_declaration_is_never_fetched_and_never_persisted() -> None:
    """Scenarios A to D share one safety floor: isolation preserves siblings, it never widens
    what may be reached or written. The unreadable value names no target, so nothing is
    requested for it and nothing carrying it reaches the boundary."""
    fetched: list[str] = []
    report, base = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots(BAD_DECLARATION, f"Sitemap: {b}/karte.xml"),
            "/karte.xml": urlset(b + "/leistungen"),
        },
        fetcher_factory=recording(fetched),
    )
    assert fetched == [base + "/", base + "/robots.txt", base + "/karte.xml"]
    assert not any("[" in url for url in fetched)
    assert not any("[" in o.observed_form for o in report.observations)


def test_robots_declaring_only_malformed_sitemaps_is_malformed_not_a_missing_declaration() -> None:
    """Scenario D. A ``Sitemap:`` field *was* present, so NO_SITEMAP_DECLARATION would be a
    false statement about the file; none of them resolved, so USED would be a false statement
    about what was recovered. MALFORMED is the existing neutral technical state for exactly
    that, and it is pinned to zero declarations — no new SourceOutcome is invented."""
    fetched: list[str] = []
    report, base = discover(
        lambda b: {"/": home(), "/robots.txt": robots(BAD_DECLARATION, "Sitemap: http://[")},
        fetcher_factory=recording(fetched),
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "MALFORMED"
    assert not any("[" in url for url in fetched)
    assert not any("[" in o.observed_form for o in report.observations)
    # The conventional /sitemap.xml is still tried, exactly as it is for any robots file that
    # hands the sitemap stage nothing. It is absent here, and that is what SITEMAP reports.
    assert fetched == [base + "/", base + "/robots.txt", base + "/sitemap.xml"]
    assert outcomes(report)["SITEMAP"] == "ABSENT"


def test_a_robots_file_with_no_sitemap_field_is_still_a_missing_declaration() -> None:
    """Scenario E — the negative control that keeps MALFORMED from swallowing the empty case.
    No ``Sitemap:`` field was recognised at all, so nothing was malformed."""
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots("User-agent: *", "Disallow: /privat", "Sitemap:", "Sitemap:  "),
        }
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "NO_SITEMAP_DECLARATION"


def test_a_valid_off_origin_declaration_is_refused_not_called_malformed() -> None:
    """Scenario F. An off-origin sitemap URL is perfectly readable; it is simply not ours.
    It must keep resolving, so the existing same-origin scope decides it downstream and
    REFUSED_SITEMAP still speaks — collapsing it into MALFORMED would lose that fact."""
    recorder = Recorder()
    report, _ = discover(
        lambda b: {
            "/": home(),
            "/robots.txt": robots("Sitemap: http://evil.test/sitemap.xml", BAD_DECLARATION),
        },
        policy=LoopbackTargetPolicy(resolve=recorder),
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "USED"
    assert outcomes(report)["REFUSED_SITEMAP"] == "TARGET_POLICY_REFUSED"
    assert "evil.test" not in recorder.hosts
    assert not any("evil.test" in o.observed_form for o in report.observations)


def test_the_declaration_guard_does_not_turn_our_own_defect_into_malformed_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario G — the lock that keeps this repair from becoming a broad ``except``.

    Only ``ValueError`` means "this website value names no readable target". Any other type
    from that call is a defect of ours, and it must still leave ``_robots`` and be reported as
    RUNTIME_ERROR by ``_guarded`` — never relabelled as something the site did wrong.
    ``urljoin`` is patched for the declaration value alone, so the robots fetch itself still
    resolves and the failure can only come from the resolution this guard wraps.
    """
    from pxapi.adapters.web import site_discovery as module

    real = module.urljoin

    def selective(base: str, url: str) -> str:
        if url == "/unser-defekt.xml":
            raise RuntimeError("a defect of ours, not a malformed value")
        return real(base, url)

    monkeypatch.setattr(module, "urljoin", selective)
    report, _ = discover(
        lambda b: {"/": home(), "/robots.txt": robots("Sitemap: /unser-defekt.xml")}
    )
    assert outcomes(report)["ROBOTS_DECLARATION"] == "RUNTIME_ERROR"
