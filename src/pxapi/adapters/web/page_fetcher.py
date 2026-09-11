"""Fetches one public page over real HTTP, under an explicit safety and resource boundary.

Three properties are the reason this module exists rather than a two-line call to a library.

**Every hop is validated before it is taken.** Redirects are followed by hand. A library that
follows them for us would perform the second request itself, and our check would then have run
only against the first URL. Each ``Location`` is resolved, re-validated and **re-resolved**
through the policy before any connection is made to it.

**We connect to an address, not to a name.** The policy hands back the addresses it actually
classified, and the connection is opened to one of those. Connecting by hostname would resolve
a second time, and a name that answered publicly during the check may answer with a loopback
address a moment later — the very gap a DNS-rebinding attack lives in. TLS still verifies the
certificate against the *hostname*, which is why the socket is wrapped explicitly.

**Nothing is unbounded.** Connect, read and a deadline spanning the whole redirect chain all
have limits, and the body is read to a byte bound rather than into memory in full. A per-receive
timeout alone bounds nothing against a peer that trickles one byte just inside it, so a watchdog
enforces the deadline itself: at the deadline it shuts the socket, the blocked read returns, and
whatever had arrived by then is discarded rather than mistaken for a response.

**A scope can narrow where a fetch may go, and nothing can widen it.** A caller that has been
authorised for one origin — site discovery, which may never leave the origin its bootstrap
established — passes a ``scope``. It is consulted on every hop *before* the policy and before
any socket, so a redirect out of the authorised origin is refused without the foreign host ever
being resolved, let alone connected to. The scope is an authorisation boundary and deliberately
not a second safety model: it can only refuse, every URL it admits is still classified by
``PublicTargetPolicy`` exactly as before, and a fetcher built without one behaves exactly as it
always has.

A failure returns a value, never an exception, and that value carries a category and nothing
else: no message, no address, no exception text. A provider's free text cannot reach a
normalised record through this module.
"""

from __future__ import annotations

import contextlib
import http.client
import socket
import ssl
import threading
import time
import zlib
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

from pxapi.adapters.web.target_policy import (
    PublicTargetPolicy,
    TargetRefused,
    ValidatedTarget,
)
from pxapi.config.fetch_limits import DEFAULT_FETCH_LIMITS, FetchLimits
from pxapi.ports.page_fetch import (
    FetchFailureKind,
    PageFetchFailure,
    PageFetchOutcome,
    PageFetchResult,
)

#: Statuses this fetcher treats as a redirect. 300 is excluded: it offers choices rather than
#: naming one, so there is nothing deterministic to follow.
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _expire(connection: http.client.HTTPConnection, expired: threading.Event) -> None:
    """The watchdog's action at the deadline: mark the hop expired and unblock its socket."""
    expired.set()
    sock = connection.sock
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)


class PinnedHTTPConnection(http.client.HTTPConnection):
    """Sends ``Host: <hostname>`` but connects to the address the policy validated."""

    def __init__(self, host: str, address: str, port: int, connect_timeout: float) -> None:
        super().__init__(host, port=port, timeout=connect_timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """The same pinning for TLS, with the certificate still checked against the hostname."""

    def __init__(
        self,
        host: str,
        address: str,
        port: int,
        connect_timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host, port=port, timeout=connect_timeout, context=context)
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, self.port), self.timeout)
        # `server_hostname` is the name, not the pinned address: certificate verification and
        # SNI must still be about who we believe we are talking to.
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class SafePageFetcher:
    """Fetches one page, following only redirects that are themselves permitted targets."""

    def __init__(
        self,
        policy: PublicTargetPolicy | None = None,
        limits: FetchLimits = DEFAULT_FETCH_LIMITS,
        clock: Callable[[], float] = time.monotonic,
        scope: Callable[[str], bool] | None = None,
        deadline_cap: Callable[[], float] | None = None,
    ) -> None:
        self.policy = policy or PublicTargetPolicy()
        self.limits = limits
        self.clock = clock
        #: Which URLs this fetcher is authorised to reach at all, or ``None`` for no narrowing.
        self.scope = scope
        #: The latest instant any fetch may run to, or ``None`` for no cap. A caller running under a
        #: deadline of its own passes it, so a fetch that begins just before that deadline cannot
        #: run a whole fetch deadline past it.
        self.deadline_cap = deadline_cap

    def fetch(self, url: str) -> PageFetchResult:
        deadline = self.clock() + self.limits.total_deadline_seconds
        if self.deadline_cap is not None:
            deadline = min(deadline, self.deadline_cap())
        current = url
        redirects = 0

        while True:
            # The scope first: it is decidable from the URL alone, so a hop out of the
            # authorised origin is refused before its host is resolved or connected to.
            if self.scope is not None and not self.scope(current):
                return PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)

            # Re-entering the loop re-validates AND re-resolves: a redirect target gets the
            # same scrutiny as the original URL, never a weaker one.
            try:
                target = self.policy.validate(current)
            except TargetRefused as refused:
                return PageFetchFailure(refused.kind)
            except ValueError:
                # A URL the standard library cannot even split — an unterminated IPv6 literal,
                # an authority invalid under NFKC — is not a permitted target, and must never
                # escape as an exception that takes the whole analysis down with it.
                return PageFetchFailure(FetchFailureKind.BLOCKED_TARGET)

            if self.clock() >= deadline:
                return PageFetchFailure(FetchFailureKind.TIMEOUT)

            outcome = self._request(target, deadline, redirects)
            if isinstance(outcome, PageFetchFailure):
                return outcome

            location = outcome.redirect_location
            if location is None:
                return outcome.response

            if redirects >= self.limits.max_redirects:
                return PageFetchFailure(FetchFailureKind.TOO_MANY_REDIRECTS)

            try:
                nxt = urljoin(target.url, location)
                scheme = urlsplit(nxt).scheme
            except ValueError:
                # A Location the standard library cannot split is not a redirect we can follow.
                return PageFetchFailure(FetchFailureKind.INVALID_REDIRECT)
            if not scheme:
                return PageFetchFailure(FetchFailureKind.INVALID_REDIRECT)
            current = nxt
            redirects += 1

    # --- one hop ---------------------------------------------------------------------

    def _request(self, target: ValidatedTarget, deadline: float, redirects: int) -> _HopResult:
        remaining = deadline - self.clock()
        if remaining <= 0:
            return PageFetchFailure(FetchFailureKind.TIMEOUT)

        connect_timeout = min(self.limits.connect_timeout_seconds, remaining)
        read_timeout = min(self.limits.read_timeout_seconds, remaining)
        connection = self._connection(target, connect_timeout)

        # The watchdog is what makes the deadline a deadline: a per-receive timeout resets on
        # every byte, so without it a trickling peer could hold this hop for as long as it liked.
        expired = threading.Event()
        watchdog = threading.Timer(remaining, _expire, args=(connection, expired))
        watchdog.daemon = True
        watchdog.start()
        try:
            result = self._exchange(connection, target, redirects, read_timeout, expired)
        except TimeoutError:
            result = PageFetchFailure(FetchFailureKind.TIMEOUT)
        except ssl.SSLError:
            result = PageFetchFailure(FetchFailureKind.PROTOCOL_ERROR)
        except http.client.HTTPException:
            result = PageFetchFailure(FetchFailureKind.PROTOCOL_ERROR)
        except ValueError:
            # A request line http.client refuses to encode (a raw non-ASCII path a server
            # redirected to without escaping it, which RFC 3986 does not allow in a Location)
            # is a request we could not make, reported in our terms rather than raised.
            result = PageFetchFailure(FetchFailureKind.PROTOCOL_ERROR)
        except OSError:
            # Every remaining socket-level problem: refused, reset, unreachable. The text is
            # deliberately dropped rather than carried into a record.
            result = PageFetchFailure(FetchFailureKind.CONNECTION_FAILURE)
        finally:
            watchdog.cancel()
            connection.close()
        # The deadline ended the exchange, not the peer: a shut socket can let a partial body
        # through without an error, and a partial body is not a response.
        if expired.is_set():
            return PageFetchFailure(FetchFailureKind.TIMEOUT)
        return result

    def _exchange(
        self,
        connection: http.client.HTTPConnection,
        target: ValidatedTarget,
        redirects: int,
        read_timeout: float,
        expired: threading.Event,
    ) -> _HopResult:
        """One request and its response over ``connection``. It may raise; the caller maps."""
        connection.connect()
        if expired.is_set():
            raise TimeoutError
        # Connect and read are bounded separately: a peer that accepts instantly and then
        # says nothing is a read timeout, not a connection that succeeded forever.
        if connection.sock is not None:
            connection.sock.settimeout(read_timeout)
        connection.putrequest("GET", self._request_path(target.url), skip_accept_encoding=True)
        connection.putheader("Accept", "text/html,application/xhtml+xml,*/*;q=0.1")
        connection.putheader("Accept-Encoding", "identity")
        connection.putheader("Connection", "close")
        connection.endheaders()
        response = connection.getresponse()

        status = response.status
        content_type = response.getheader("Content-Type")

        if status in REDIRECT_STATUSES:
            location = response.getheader("Location")
            if location is None or not location.strip():
                return PageFetchFailure(FetchFailureKind.INVALID_REDIRECT)
            return _Hop(response=None, redirect_location=location.strip())

        bound = self.limits.max_response_bytes
        # One byte past the bound: enough to know the body was longer, never enough to
        # matter. Reading without a bound is what this line exists to prevent.
        raw = response.read(bound + 1)
        truncated = len(raw) > bound
        body, undecodable, inflated_past_bound = _decoded_content(
            raw[:bound], response.getheader("Content-Encoding"), bound
        )

        return _Hop(
            response=PageFetchOutcome(
                final_url=target.url,
                status_code=status,
                content_type=content_type,
                # `get_all` keeps every physical field line; `getheader` would fold them
                # into one comma-separated string, and a comma is exactly what separates
                # directives inside a single value. Two lines that fold into one are then
                # indistinguishable from one line that always said that, which is how a
                # generic directive comes to look crawler-scoped.
                x_robots_tag=tuple(response.headers.get_all("X-Robots-Tag") or ()),
                is_https=target.is_https,
                redirect_count=redirects,
                body=body,
                truncated=truncated or inflated_past_bound,
                declared_charset=_charset_of(content_type),
                undecodable=undecodable,
            ),
            redirect_location=None,
        )

    def _connection(
        self, target: ValidatedTarget, connect_timeout: float
    ) -> http.client.HTTPConnection:
        address = target.addresses[0]
        if target.is_https:
            return PinnedHTTPSConnection(
                target.host, address, target.port, connect_timeout, ssl.create_default_context()
            )
        return PinnedHTTPConnection(target.host, address, target.port, connect_timeout)

    @staticmethod
    def _request_path(url: str) -> str:
        parts = urlsplit(url)
        path = parts.path or "/"
        return f"{path}?{parts.query}" if parts.query else path


class _Hop:
    """One hop's result: either a response, or the Location to validate and follow."""

    __slots__ = ("redirect_location", "response")

    def __init__(self, response: PageFetchOutcome | None, redirect_location: str | None) -> None:
        self.response = response
        self.redirect_location = redirect_location


_HopResult = _Hop | PageFetchFailure


#: Content encodings we can decode. Anything else is reported as undecodable rather than
#: parsed as though the compressed bytes were the document.
_DECODERS: dict[str, int] = {
    # gzip framing, and raw/zlib-wrapped deflate.
    "gzip": 16 + zlib.MAX_WBITS,
    "x-gzip": 16 + zlib.MAX_WBITS,
    "deflate": zlib.MAX_WBITS,
}


def _decoded_content(raw: bytes, encoding: str | None, bound: int) -> tuple[bytes, bool, bool]:
    """Decode a response body, returning ``(body, undecodable, inflated_past_bound)``.

    Servers compress even when asked not to, so a fetcher that skipped this would hand the
    parser gzip bytes, find no title in them, and report that the *site* has no title. That
    is the exact failure this slice exists to prevent, which is why an encoding we cannot
    decode is reported as such instead of being parsed anyway.

    Decompression is bounded as well as the read. A small compressed body can inflate to an
    arbitrarily large one, so the output is capped exactly like the input.
    """
    token = (encoding or "").strip().lower()
    if not token or token == "identity":
        return raw, False, False

    window = _DECODERS.get(token)
    if window is None:
        # Brotli, zstd, or several encodings applied at once. We do not have the document.
        return b"", True, False

    for wbits in (window, -zlib.MAX_WBITS):
        try:
            # `max_length` caps the output: a decompression bomb cannot make us allocate
            # more than one bounded body.
            decoded = zlib.decompressobj(wbits).decompress(raw, bound + 1)
        except zlib.error:
            continue
        if not decoded:
            continue
        return decoded[:bound], False, len(decoded) > bound
    # The stream was cut at the read bound, or it is not what it claimed to be.
    return b"", True, False


def _charset_of(content_type: str | None) -> str | None:
    """The charset declared in a Content-Type header, if it declares one."""
    if not content_type:
        return None
    for parameter in content_type.split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "charset":
            return value.strip().strip('"').strip("'") or None
    return None
