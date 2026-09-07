"""Which destinations PXAPI is allowed to fetch, decided before any socket is opened.

The rule this module protects is narrow and absolute: a public analysis may reach public
destinations only. Loopback, private ranges, link-local (which is where cloud metadata lives),
unspecified, multicast, carrier-grade NAT and unique-local addresses are all refused, and so is
a hostname that resolves to *any* of them.

Every test injects a resolver. The policy is the unit under test, not DNS: a test that depended
on what a real name resolves to today would be measuring the internet instead of the rule.
"""

from __future__ import annotations

import socket

import pytest

from pxapi.adapters.web.target_policy import PublicTargetPolicy, TargetRefused
from pxapi.ports.page_fetch import FetchFailureKind

PUBLIC = "93.184.216.34"


def policy_resolving_to(*addresses: str) -> PublicTargetPolicy:
    """A policy whose resolver always answers with ``addresses``."""

    def resolve(host: str, port: int) -> list[str]:
        return list(addresses)

    return PublicTargetPolicy(resolve=resolve)


def refusing_policy(error: Exception) -> PublicTargetPolicy:
    def resolve(host: str, port: int) -> list[str]:
        raise error

    return PublicTargetPolicy(resolve=resolve)


# --- the canary: the policy must accept something, or every test below is vacuous ---------


def test_a_public_https_target_is_permitted() -> None:
    target = policy_resolving_to(PUBLIC).validate("https://example.com/")
    assert target.scheme == "https"
    assert target.host == "example.com"
    assert target.port == 443
    assert target.addresses == (PUBLIC,)


def test_a_public_http_target_is_permitted_on_its_default_port() -> None:
    target = policy_resolving_to(PUBLIC).validate("http://example.com/path")
    assert target.scheme == "http"
    assert target.port == 80


def test_an_explicit_port_is_kept() -> None:
    assert policy_resolving_to(PUBLIC).validate("https://example.com:8443/").port == 8443


# --- scheme ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "data:text/html,hi",
        "//example.com/",
        "example.com",
        "",
    ],
)
def test_only_http_and_https_are_permitted(url: str) -> None:
    with pytest.raises(TargetRefused) as refused:
        policy_resolving_to(PUBLIC).validate(url)
    assert refused.value.kind is FetchFailureKind.BLOCKED_TARGET


# --- credentials -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@example.com/",
        "https://user@example.com/",
        "https://:secret@example.com/",
    ],
)
def test_credentials_in_the_authority_are_refused(url: str) -> None:
    """Accepting them would put a secret into a URL we then record and echo back."""
    with pytest.raises(TargetRefused) as refused:
        policy_resolving_to(PUBLIC).validate(url)
    assert refused.value.kind is FetchFailureKind.BLOCKED_TARGET


def test_a_refusal_never_carries_the_credential() -> None:
    with pytest.raises(TargetRefused) as refused:
        policy_resolving_to(PUBLIC).validate("https://user:hunter2@example.com/")
    assert "hunter2" not in str(refused.value)
    assert "hunter2" not in repr(refused.value)


# --- forbidden destination classes -------------------------------------------------------

FORBIDDEN = {
    "loopback v4": "127.0.0.1",
    "loopback v4, unusual form": "127.255.255.254",
    "loopback v6": "::1",
    "private 10/8": "10.0.0.1",
    "private 172.16/12": "172.16.5.4",
    "private 192.168/16": "192.168.1.1",
    "link-local": "169.254.1.1",
    "cloud metadata": "169.254.169.254",
    "link-local v6": "fe80::1",
    "unique-local v6": "fd00::1",
    "unspecified v4": "0.0.0.0",
    "unspecified v6": "::",
    "multicast v4": "224.0.0.1",
    "multicast v6": "ff02::1",
    "carrier-grade NAT": "100.64.0.1",
    "reserved": "240.0.0.1",
    "broadcast": "255.255.255.255",
    "IPv4-mapped loopback": "::ffff:127.0.0.1",
    "IPv4-mapped metadata": "::ffff:169.254.169.254",
}


@pytest.mark.parametrize("address", FORBIDDEN.values(), ids=list(FORBIDDEN))
def test_a_hostname_resolving_to_a_forbidden_address_is_refused(address: str) -> None:
    with pytest.raises(TargetRefused) as refused:
        policy_resolving_to(address).validate("https://anything.example/")
    assert refused.value.kind is FetchFailureKind.BLOCKED_TARGET


@pytest.mark.parametrize("address", FORBIDDEN.values(), ids=list(FORBIDDEN))
def test_a_literal_forbidden_address_is_refused(address: str) -> None:
    """An IP literal skips resolution but never skips classification."""
    literal = f"[{address}]" if ":" in address else address
    with pytest.raises(TargetRefused) as refused:
        policy_resolving_to(address).validate(f"https://{literal}/")
    assert refused.value.kind is FetchFailureKind.BLOCKED_TARGET


def test_a_public_literal_address_is_permitted() -> None:
    """Canary for the two tests above: the literal path is not refusing everything."""
    target = policy_resolving_to(PUBLIC).validate(f"https://{PUBLIC}/")
    assert target.addresses == (PUBLIC,)


# --- the partial-resolution rule ----------------------------------------------------------


def test_a_host_resolving_partly_to_a_forbidden_address_is_refused_entirely() -> None:
    """One bad answer condemns the name.

    A split-horizon or attacker-controlled name can answer with a public address alongside a
    private one. Taking "there was at least one good address" would let exactly that through.
    """
    with pytest.raises(TargetRefused) as refused:
        policy_resolving_to(PUBLIC, "127.0.0.1").validate("https://split.example/")
    assert refused.value.kind is FetchFailureKind.BLOCKED_TARGET


def test_the_order_of_the_answers_does_not_change_the_verdict() -> None:
    with pytest.raises(TargetRefused):
        policy_resolving_to("127.0.0.1", PUBLIC).validate("https://split.example/")


def test_a_host_resolving_to_several_public_addresses_keeps_them_all() -> None:
    target = policy_resolving_to(PUBLIC, "8.8.8.8").validate("https://many.example/")
    assert target.addresses == (PUBLIC, "8.8.8.8")


def test_a_host_that_resolves_to_nothing_is_a_dns_failure() -> None:
    with pytest.raises(TargetRefused) as refused:
        policy_resolving_to().validate("https://empty.example/")
    assert refused.value.kind is FetchFailureKind.DNS_FAILURE


def test_a_resolver_error_is_a_dns_failure_not_a_blocked_target() -> None:
    """The two are different facts: one is our policy, the other is the name not existing."""
    with pytest.raises(TargetRefused) as refused:
        refusing_policy(socket.gaierror("nope")).validate("https://nx.example/")
    assert refused.value.kind is FetchFailureKind.DNS_FAILURE


def test_a_resolver_error_never_leaks_its_message() -> None:
    with pytest.raises(TargetRefused) as refused:
        refusing_policy(socket.gaierror("Name or service not known: secret.internal")).validate(
            "https://nx.example/"
        )
    assert "secret.internal" not in str(refused.value)


# --- structure ----------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["https:///path", "https://", "http://:80/"])
def test_a_url_without_a_host_is_refused(url: str) -> None:
    with pytest.raises(TargetRefused) as refused:
        policy_resolving_to(PUBLIC).validate(url)
    assert refused.value.kind is FetchFailureKind.BLOCKED_TARGET


def test_the_resolver_is_asked_for_the_port_that_will_be_connected_to() -> None:
    seen: list[tuple[str, int]] = []

    def resolve(host: str, port: int) -> list[str]:
        seen.append((host, port))
        return [PUBLIC]

    PublicTargetPolicy(resolve=resolve).validate("https://example.com:8443/x")
    assert seen == [("example.com", 8443)]


def test_the_default_policy_resolves_through_the_standard_library() -> None:
    """The shipped policy must not carry a test seam as its default."""
    assert PublicTargetPolicy().resolve is not None
    assert PublicTargetPolicy._resolve_with_stdlib.__module__.startswith("pxapi.")


def test_the_shipped_policy_permits_no_loopback_address() -> None:
    """The extension point exists for tests; the shipped policy must not itself be widened."""
    strict = PublicTargetPolicy()
    for address in ("127.0.0.1", "::1", "169.254.169.254", "10.0.0.1"):
        assert strict._permits(address) is False, address
    assert strict._permits(PUBLIC) is True


def test_the_policy_takes_no_argument_that_could_widen_it() -> None:
    """A constructor switch could be set in production; a subclass in tests cannot be."""
    import inspect

    parameters = set(inspect.signature(PublicTargetPolicy.__init__).parameters) - {"self"}
    assert parameters == {"resolve"}, (
        f"PublicTargetPolicy gained the parameter(s) {parameters - {'resolve'}}; "
        "the address rule must not be configurable"
    )
