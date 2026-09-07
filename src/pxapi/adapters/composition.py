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
from pxapi.application.analyze_homepage import AnalyzeHomepage
from pxapi.config.contract_root import contract_root
from pxapi.config.fetch_limits import DEFAULT_FETCH_LIMITS

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
