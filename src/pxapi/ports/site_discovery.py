"""The boundary the application talks through to discover one public site's page population.

The port is provider-neutral by construction. What crosses it is a ``DiscoveryReport``: the
origin the bootstrap established (or why none was), every URL a source wrote, and the neutral
technical state each attempted source ended in. No response body, header, status code, parser
object or provider identity crosses it, so nothing behind this boundary — the static HTTP
provider this slice ships, or a rendered-browser provider a later slice may add — can reach
the decisions made on this side of it: which forms are admitted, how they canonicalise, what
type each page is, and which pages the run sets out to analyse.

That is the D-PXAPI-007 rule expressed as a type. A provider reports; Pixelkiez methodology
decides.

The port describes *outcomes*, not exceptions, exactly as ``page_fetch`` does. A discovery that
could not establish an origin is a value the application must handle, because "we could not
start" is a real analysis result rather than an error to be swallowed or re-raised.

Standard library only. Ports import no third-party distribution.
"""

from __future__ import annotations

from typing import Protocol

from pxapi.domain.site_discovery import (
    BootstrapFailure,
    DiscoveryObservation,
    DiscoveryReport,
    SourceAttempt,
    SourceId,
    SourceOutcome,
)

#: Re-exported so an adapter implementing the port names the boundary vocabulary from the
#: port rather than reaching into the Domain for it.
__all__ = [
    "BootstrapFailure",
    "DiscoveryObservation",
    "DiscoveryReport",
    "SiteDiscoveryPort",
    "SourceAttempt",
    "SourceId",
    "SourceOutcome",
]


class SiteDiscoveryPort(Protocol):
    """Discovers one public site's page population, or reports why it could not start."""

    def discover(self, target_url: str) -> DiscoveryReport:
        """Establish the canonical public origin of ``target_url`` and read its sources.

        An implementation must establish the origin under the product's public target policy,
        must never open a connection outside that origin once it is established, and must
        report every source it attempted — including the seed — rather than only the ones that
        produced something.
        """
        ...
