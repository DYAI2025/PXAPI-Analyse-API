"""Which destinations a public, non-invasive analysis may fetch.

This is the whole of the slice's egress rule, and it is deliberately small: it decides one
question — *may we open a connection to this URL?* — and answers it **before** any socket
exists. It is not a general egress platform, a proxy, or a firewall.

The rule is that a public analysis reaches public destinations only. Everything else is
refused: loopback, private ranges, link-local (where cloud metadata endpoints live),
unspecified, multicast, reserved, carrier-grade NAT and unique-local addresses.

Two properties matter more than the list itself.

**Partial resolution is fatal.** A hostname is refused when *any* address it resolves to is
forbidden. Accepting a name because at least one answer looked public is exactly the hole a
split-horizon or attacker-controlled name walks through.

**The verdict names addresses, not a hostname.** ``ValidatedTarget.addresses`` is what the
fetcher must connect to. Connecting by hostname would re-resolve, and a name that answered
publicly during validation may answer with a loopback address a moment later — the check would
have been performed against one destination and the connection made to another.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from pxapi.ports.page_fetch import FetchFailureKind

#: The only schemes this slice speaks, and the port each defaults to.
DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


class TargetRefused(Exception):
    """The URL may not be fetched, and why in our own terms.

    The message names the rule and never the value that broke it: a rejected URL may carry a
    credential, and an exception is copied into logs long before anyone reviews it.
    """

    def __init__(self, kind: FetchFailureKind, rule: str) -> None:
        super().__init__(f"target refused: {rule}")
        self.kind = kind
        self.rule = rule


class Resolver(Protocol):
    def __call__(self, host: str, port: int) -> list[str]:
        """Every address ``host`` resolves to, as strings."""
        ...


@dataclass(frozen=True)
class ValidatedTarget:
    """A destination that passed the policy, and the addresses it may be reached at."""

    url: str
    scheme: str
    host: str
    port: int
    #: Validated addresses, in resolution order. The fetcher connects to one of *these*.
    addresses: tuple[str, ...]

    @property
    def is_https(self) -> bool:
        return self.scheme == "https"


def _unwrapped(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """The address, with an IPv4-mapped IPv6 address reduced to the IPv4 address it carries.

    ``::ffff:127.0.0.1`` is loopback wearing a v6 costume. Classifying it as a v6 address would
    read it as globally routable and let it through.
    """
    parsed = ipaddress.ip_address(address)
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        return parsed.ipv4_mapped
    return parsed


def is_public_address(address: str) -> bool:
    """Whether ``address`` is a destination a public analysis may connect to.

    ``is_global`` carries the private, loopback, link-local, unspecified, carrier-grade NAT and
    unique-local exclusions; multicast and reserved are named separately because a globally
    *scoped* multicast address is still not a website.
    """
    try:
        parsed = _unwrapped(address)
    except ValueError:
        return False
    return parsed.is_global and not parsed.is_multicast and not parsed.is_reserved


class PublicTargetPolicy:
    """Decides whether a URL is a permitted public destination, before any connection."""

    def __init__(self, resolve: Resolver | None = None) -> None:
        self.resolve: Resolver = resolve or self._resolve_with_stdlib

    def _permits(self, address: str) -> bool:
        """Whether this policy allows connecting to ``address``.

        The shipped policy permits public addresses and nothing else, and takes no argument
        that could widen that. The single extension point is this method, so an integration
        test that needs to reach a server on loopback subclasses the policy **in test code**
        rather than the product gaining a configuration switch that could be set in
        production. Test infrastructure and product policy stay separate that way.
        """
        return is_public_address(address)

    @staticmethod
    def _resolve_with_stdlib(host: str, port: int) -> list[str]:
        """Every address the system resolver returns for ``host``, v4 and v6 alike."""
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        seen: list[str] = []
        for info in infos:
            address = str(info[4][0])
            if address not in seen:
                seen.append(address)
        return seen

    def validate(self, url: str) -> ValidatedTarget:
        """Return the validated target, or raise ``TargetRefused``.

        The order is deliberate: everything decidable from the URL alone is decided before the
        resolver is consulted, so a malformed or credentialed URL never causes a DNS lookup.
        """
        parts = urlsplit(url)

        if parts.scheme not in DEFAULT_PORTS:
            raise TargetRefused(FetchFailureKind.BLOCKED_TARGET, "scheme must be http or https")

        # `parts.username`/`password` only see a well-formed userinfo; the raw check also
        # catches an authority that merely contains one.
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            raise TargetRefused(
                FetchFailureKind.BLOCKED_TARGET, "credentials in the URL authority are not accepted"
            )

        try:
            port = parts.port or DEFAULT_PORTS[parts.scheme]
        except ValueError as error:
            raise TargetRefused(FetchFailureKind.BLOCKED_TARGET, "port is not a number") from error

        host = (parts.hostname or "").strip()
        if not host:
            raise TargetRefused(FetchFailureKind.BLOCKED_TARGET, "the URL names no host")

        addresses = self._addresses_for(host, port)

        forbidden = [address for address in addresses if not self._permits(address)]
        if forbidden:
            # The offending address is not named: it is attacker-influenced input, and the
            # rule is what a reader needs, not the value that tripped it.
            raise TargetRefused(
                FetchFailureKind.BLOCKED_TARGET,
                "the host resolves to a non-public address",
            )

        return ValidatedTarget(
            url=url, scheme=parts.scheme, host=host, port=port, addresses=tuple(addresses)
        )

    def _addresses_for(self, host: str, port: int) -> list[str]:
        """The addresses to classify: the literal itself, or everything the name resolves to."""
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            return [host]

        try:
            addresses = self.resolve(host, port)
        except Exception as error:
            # A resolver's text can name internal infrastructure; only the category survives.
            raise TargetRefused(
                FetchFailureKind.DNS_FAILURE, "the host could not be resolved"
            ) from error

        if not addresses:
            raise TargetRefused(
                FetchFailureKind.DNS_FAILURE, "the host resolved to no address at all"
            )
        return addresses
