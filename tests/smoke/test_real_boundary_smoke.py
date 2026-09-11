"""The PXAPI-19 Real-Boundary-Smoke, as an opt-in test against one controlled public site.

It is skipped unless ``PXAPI_REAL_BOUNDARY_SMOKE_URL`` names a target, so the suite and CI stay
network-free and deterministic: a public site changes between two runs, and a test whose verdict
depends on that would be a test of the site rather than of this code. Run deliberately it drives
the *real* composition — the shipped ``PublicTargetPolicy``, real DNS, real sockets, the real
bounds — and asserts the properties that must hold for any public site, never a site's content.

What it proves is the tested boundary only: that one public origin was established safely,
discovered within its bounds, reduced to a valid inventory and planned as a valid census. It does
not prove arbitrary internet crawling, production scale, complete site coverage, browser
rendering, PXAPI-20 acquisition, scoring quality or customer uplift.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from pxapi.adapters.composition import build_site_discovery, default_registry
from pxapi.adapters.inbound.cli import build_request
from pxapi.adapters.inbound.discover_cli import invalid_documents
from tests.application.test_discover_site import verdict_keys_in

TARGET = os.environ.get("PXAPI_REAL_BOUNDARY_SMOKE_URL")

pytestmark = pytest.mark.skipif(
    not TARGET, reason="opt-in: set PXAPI_REAL_BOUNDARY_SMOKE_URL to a public target"
)


def test_one_public_site_crosses_the_whole_discovery_boundary() -> None:
    assert TARGET is not None
    envelope: dict[str, Any] = build_site_discovery().run(build_request(TARGET))

    assert invalid_documents(default_registry(), envelope) == []
    assert envelope["analysis_run_state"]["state"] == "SUCCEEDED", envelope["analysis_run_state"]
    inventory, manifest = envelope["site_inventory"], envelope["sampling_manifest"]

    seeds = [c for c in inventory["candidates"] if c["url_key"] == inventory["target_origin"]]
    assert len(seeds) == 1 and "CANONICAL_SEED" in seeds[0]["provenance"]

    # The shipped composition declares no selection budget, so the census is complete over the
    # inventory discovery produced: every eligible candidate is selected, none is left out by a
    # budget, and no budget is declared. A discovery *source* may still report BUDGET_EXHAUSTED
    # on the same run — that is the inventory's statement about how far discovery reached, and
    # it is deliberately not the selection's statement about the population it was handed.
    eligible = [c for c in inventory["candidates"] if c["eligibility"]["state"] == "ELIGIBLE"]
    assert manifest["mode"] == "CENSUS"
    assert len(manifest["selections"]) == len(eligible)
    assert manifest["selection_complete"] is True
    assert "budgets" not in manifest
    assert "incompleteness" not in manifest
    assert all(e["reason"] != "SELECTION_BUDGET_EXHAUSTED" for e in manifest["exclusions"])
    ranks = sorted(s["selection_rank"] for s in manifest["selections"])
    assert ranks == list(range(1, len(ranks) + 1))
    assert manifest["inventory_output_digest"] == inventory["output_digest"]
    assert verdict_keys_in(envelope) == set()
