"""The bounds a public page fetch runs under.

Small, explicit and in one place, so that "how long may this take" and "how much may we read"
are reviewable facts rather than numbers scattered through an adapter. They are deliberately
conservative: this slice fetches exactly one homepage and is not a general egress platform.

Config is a leaf layer: this module imports no other ``pxapi`` layer and no third party.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FetchLimits:
    """Every bound one homepage fetch is allowed to consume."""

    #: How many redirect hops may be followed. Each hop is fully re-validated and re-resolved,
    #: so this bounds the work an unfriendly site can make us do, not the safety of a hop.
    max_redirects: int = 3

    #: Seconds to wait for a TCP connection to one address.
    connect_timeout_seconds: float = 5.0

    #: Seconds to wait for response data on an established connection.
    read_timeout_seconds: float = 10.0

    #: Seconds for the whole operation, redirects included. Without a deadline spanning hops,
    #: a chain of individually-fast redirects could still run unbounded.
    total_deadline_seconds: float = 20.0

    #: The most response body we will read, in bytes. Reading stops here; the body is never
    #: buffered without a bound, and a declared Content-Length above it is refused up front.
    max_response_bytes: int = 2 * 1024 * 1024


#: The bounds the service runs with.
DEFAULT_FETCH_LIMITS = FetchLimits()
