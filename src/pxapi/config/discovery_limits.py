"""The bounds one site discovery runs under.

Small, explicit and in one place, for the same reason ``fetch_limits`` exists: "how many
requests may discovery make" and "how much of a sitemap may it read" are reviewable facts
rather than numbers scattered through an adapter.

**Nothing here bounds a selection.** Every value below caps the *discovery* that produces the
site inventory, and none of them may be read as a ceiling on how many of that inventory's
candidates a census may name. The two are different questions, and a discovery bound quietly
doing double duty as a selection bound is exactly how a run stops short of its own population
without saying so: discovery incompleteness belongs in the inventory's source outcomes, and
selection incompleteness in the manifest. How much of the bound inventory one selection may
take is the Domain's ``SelectionBudgets``, declared by whoever runs the selection, and the
shipped default declares none — a census over the whole bound inventory. A ceiling on that
would be a product decision about how much of a site an analysis covers, and no PXAPI authority
has taken one.

None of these is a census-to-sampling threshold, and none may be read as one. C-PXAPI-005 keeps
that threshold ``MISSING`` until representative benchmarks support a versioned decision, and
nothing here decides *which method* is used: every value below is a ceiling on how much work
one run may do. Reaching one is recorded as a neutral technical state — a source outcome of
``BUDGET_EXHAUSTED`` or ``TIMEOUT`` — and never as a property of the site and never as a switch
to ``STRATIFIED_SAMPLE``.

Config is a leaf layer: this module imports no other ``pxapi`` layer and no third party.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryLimits:
    """Every bound one discovery run is allowed to consume.

    Discovery only. A member that bounded a *selection* would belong to ``SelectionBudgets``,
    where it travels into the manifest that was planned under it and can be read there.
    """

    #: Fetches one discovery may issue in total: the bootstrap, ``/robots.txt`` and every
    #: sitemap document together. Each fetch still runs under ``FetchLimits`` — its own
    #: redirect, byte and time bounds — so this bounds how many of those one site can cause.
    max_requests: int = 8

    #: Sitemap documents one discovery may read, index documents included. A sitemap index can
    #: name thousands of children; this is what keeps one site from turning discovery into a
    #: crawl of its own sitemap tree.
    max_sitemap_documents: int = 5

    #: Distinct written sitemap entries admitted across every sitemap document together. A form
    #: repeated in a sitemap counts once: duplication is never allowed to cost a page.
    max_sitemap_entries: int = 500

    #: Distinct written same-origin link targets admitted from the seed document. A target a
    #: menu and a footer both link to counts once.
    max_page_links: int = 200

    #: Distinct link targets examined in the seed document, same-origin or not. The page-link
    #: budget above counts what is admitted; this counts the work of deciding, so a document of
    #: thousands of distinct foreign links cannot make discovery canonicalise every one of them.
    max_links_examined: int = 2000

    #: The longest normalised anchor label carried to the classifier. A longer one is dropped,
    #: never truncated: a truncated label is text the site did not write.
    max_label_length: int = 120

    #: Seconds for the whole discovery, every fetch included. Every fetch is capped by what
    #: remains of it, and a watchdog enforces each fetch's own deadline, so a site answering each
    #: of several requests just inside a timeout, or trickling a body, cannot hold a discovery
    #: past it.
    total_deadline_seconds: float = 60.0


#: The bounds the service runs with.
DEFAULT_DISCOVERY_LIMITS = DiscoveryLimits()
