"""The boundary the application talks through to retrieve one public page.

The port deliberately describes *outcomes*, not exceptions. A fetch that did not happen is a
value the application must handle, in the same shape as a fetch that did, because "we could not
measure" is a real analysis result rather than an error to be swallowed or re-raised.

A failure carries a ``kind`` and nothing else — no message, no address, no exception text, no
path. That is what keeps a provider's or our runtime's free text structurally unable to reach a
normalised record, a log line or a customer-facing document.

Standard library only. Ports import no third-party distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class FetchFailureKind(StrEnum):
    """Why a page fetch produced no response. Every value names *our* side of the attempt.

    None of these says anything about the website. That is the point: they are the reasons an
    analysis process failed to observe, and a later mapping turns them into the contract's
    ``not_assessed_reason`` — never into a finding about the site.
    """

    #: The target is not a permitted public destination. Refused before any socket was opened.
    BLOCKED_TARGET = "BLOCKED_TARGET"
    #: The hostname did not resolve.
    DNS_FAILURE = "DNS_FAILURE"
    #: The connection could not be established, or was lost.
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    #: A connect, read, or the overall deadline elapsed.
    TIMEOUT = "TIMEOUT"
    #: The redirect chain exceeded the configured bound.
    TOO_MANY_REDIRECTS = "TOO_MANY_REDIRECTS"
    #: A redirect response carried no usable Location, or one that is not a permitted target.
    INVALID_REDIRECT = "INVALID_REDIRECT"
    #: The peer spoke something we could not parse as HTTP, or the TLS handshake failed.
    PROTOCOL_ERROR = "PROTOCOL_ERROR"


@dataclass(frozen=True)
class PageFetchFailure:
    """A fetch that produced no response, and the reason in our own terms."""

    kind: FetchFailureKind


@dataclass(frozen=True)
class PageFetchOutcome:
    """A response that was actually received.

    ``truncated`` is load-bearing. When the body hit the configured byte bound, what we did not
    see is genuinely unknown: an element missing from a truncated document may well be present
    in the part we never read. A caller must not report such an absence as a fact about the
    site, and this flag is how it can tell the difference.
    """

    #: The URL the fetch ended at, after every followed redirect.
    final_url: str
    status_code: int
    #: The raw ``Content-Type`` header, or ``None`` when the response declared none.
    content_type: str | None
    #: Whether the final response arrived over TLS.
    is_https: bool
    redirect_count: int
    #: The response body, never longer than the configured bound.
    body: bytes
    #: Whether reading stopped at the bound rather than at the end of the body.
    truncated: bool
    #: The charset declared in ``Content-Type``, or ``None`` when none was declared.
    declared_charset: str | None
    #: True when the response arrived in a content encoding we could not decode, so ``body``
    #: is not the document. Load-bearing for the same reason ``truncated`` is: a document we
    #: could not decode tells us nothing about what it contains, and reporting its elements
    #: as absent would turn our own gap into a finding about the site.
    undecodable: bool = False


#: What a fetch returns: either a response, or the reason there is none.
PageFetchResult = PageFetchOutcome | PageFetchFailure


class PageFetcher(Protocol):
    """Retrieves one public page, or reports why it could not."""

    def fetch(self, url: str) -> PageFetchResult:
        """Fetch ``url``, following only redirects that are themselves permitted targets."""
        ...
