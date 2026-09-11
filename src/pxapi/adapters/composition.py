"""How the running service is wired together.

One place builds the real objects, so the HTTP transport and the command line drive exactly the
same use case with exactly the same safety policy. A second wiring site is how a CLI quietly
ends up with a laxer fetcher than the endpoint.

Every default here is the strict one. Nothing in this module accepts a parameter that could
relax the target policy; a test that needs a different one constructs its own use case.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from pxapi.adapters.contracts.registry import ContractRegistry
from pxapi.adapters.web.html_observations import read_html
from pxapi.adapters.web.page_fetcher import SafePageFetcher
from pxapi.adapters.web.site_discovery import HttpSiteDiscovery
from pxapi.application.analyze_homepage import AnalyzeHomepage
from pxapi.application.discover_site import DiscoverSite
from pxapi.config.contract_root import contract_root
from pxapi.config.discovery_limits import DEFAULT_DISCOVERY_LIMITS
from pxapi.config.fetch_limits import DEFAULT_FETCH_LIMITS
from pxapi.domain.sampling_policy import SelectionBudgets

#: The scan mode this slice implements. The contract's vocabulary is wider on purpose; a mode
#: we have not built is refused rather than silently treated as this one.
SUPPORTED_SCAN_MODE = "PUBLIC_NON_INVASIVE"


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_identifier() -> str:
    return f"px-{uuid.uuid4().hex}"


def default_registry() -> ContractRegistry:
    return ContractRegistry(contract_root())


def build_analyzer(
    registry: ContractRegistry | None = None,
    clock: Callable[[], datetime] = utc_now,
    new_id: Callable[[], str] = new_identifier,
) -> AnalyzeHomepage:
    """The real use case: strict target policy, real sockets, real parser."""
    registry = registry or default_registry()
    return AnalyzeHomepage(
        fetcher=SafePageFetcher(limits=DEFAULT_FETCH_LIMITS),
        read_html=read_html,
        clock=clock,
        new_id=new_id,
        # The bound comes out of the contract, so a collector cannot hold a stale copy of it.
        max_text_length=registry.max_single_line_text(),
    )


def build_site_discovery(
    clock: Callable[[], datetime] = utc_now,
    new_id: Callable[[], str] = new_identifier,
) -> DiscoverSite:
    """The real discovery use case: strict target policy, origin-scoped fetches, full census.

    It takes no argument that could relax the target policy or widen a bound, for the same
    reason ``build_analyzer`` takes none: a test that needs a loopback server constructs its
    own use case around a test-only policy, and nothing configurable in production can.
    """
    limits = DEFAULT_DISCOVERY_LIMITS
    return DiscoverSite(
        discovery=HttpSiteDiscovery(fetch_limits=DEFAULT_FETCH_LIMITS, limits=limits),
        clock=clock,
        new_id=new_id,
        # No selection budget is declared, so the census covers every eligible candidate of the
        # inventory that the discovery bounds above already bounded. The ceiling that used to
        # stand here was the value of a registered 19.A *example*, which illustrates a document
        # and decides no policy; how much of a site one analysis covers is a product decision
        # nobody has taken, so none is invented here. A caller that needs a bounded census
        # constructs its own use case with a declared ``SelectionBudgets``, and that declared
        # budget then travels in the manifest planned under it, where a reader can see it.
        budgets=SelectionBudgets(),
    )
