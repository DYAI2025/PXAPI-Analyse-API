"""The bounds one site discovery and one selection run under.

Small, explicit and in one place, for the same reason ``fetch_limits`` exists: "how many
requests may discovery make", "how much of a sitemap may it read" and "how many pages may a
selection name" are reviewable facts rather than numbers scattered through an adapter.

None of these is a census-to-sampling threshold, and none may be read as one. C-PXAPI-005 keeps
that threshold ``MISSING`` until representative benchmarks support a versioned decision, and
nothing here decides *which method* is used: every value below is a ceiling on how much work
one run may do. Reaching one is recorded as a neutral technical state — a source outcome of
``BUDGET_EXHAUSTED`` or ``TIMEOUT``, a selection that is ``CENSUS`` with ``selection_complete``
false — and never as a property of the site and never as a switch to ``STRATIFIED_SAMPLE``.

Config is a leaf layer: this module imports no other ``pxapi`` layer and no third party.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryLimits:
    """Every bound one discovery run and its selection are allowed to consume."""

    #: Fetches one discovery may issue in total: the bootstrap, ``/robots.txt`` and every
    #: sitemap document together. Each fetch still runs under ``FetchLimits`` — its own
    #: redirect, byte and time bounds — so this bounds how many of those one site can cause.
    max_requests: int = 8

    #: Sitemap documents one discovery may read, index documents included. A sitemap index can
    #: name thousands of children; this is what keeps one site from turning discovery into a
    #: crawl of its own sitemap tree.
    max_sitemap_documents: int = 5

    #: Sitemap URL entries admitted across every sitemap document together.
    max_sitemap_entries: int = 500

    #: Distinct same-origin link targets admitted from the seed document.
    max_page_links: int = 200

    #: The longest normalised anchor label carried to the classifier. A longer one is dropped,
    #: never truncated: a truncated label is text the site did not write.
    max_label_length: int = 120

    #: Seconds for the whole discovery, every fetch included. Without a deadline spanning the
    #: run, a site answering each of several requests just inside its own timeout could still
    #: hold one discovery for minutes.
    total_deadline_seconds: float = 60.0

    #: The declared ceiling on how many pages one selection may name. It is a budget and not a
    #: threshold: reaching it leaves the mode ``CENSUS`` and records the selection as bounded.
    max_selected_pages: int = 25


#: The bounds the service runs with.
DEFAULT_DISCOVERY_LIMITS = DiscoveryLimits()
