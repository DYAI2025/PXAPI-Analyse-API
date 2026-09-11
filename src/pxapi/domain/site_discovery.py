"""What a discovery run observed, and how observations become one candidate population.

This module holds the step between "a provider handed us some URLs" and "the inventory has a
candidate list": admission, canonicalisation, aggregation of everything that collapses onto one
identity, technical admissibility, and the per-source admitted counts. It is Domain code
because every one of those is a Pixelkiez methodology decision rather than a transport detail —
D-PXAPI-007 says providers must not decide which pages become diagnosis-relevant, and the way to
honour that is for no provider to be able to reach this logic at all.

Three rules carry the weight.

**Admission before anything else.** An observation enters the population only when its written
form is one the contract may persist *and* it has a canonical identity. A credential-bearing
URL fails both, and is dropped here — never recorded as a rejected string so a digest could be
recomputed over it, which D-PXAPI19-PO-007 forbids outright. The inventory's ``input_digest``
is computed over exactly the admitted observations, which is what the contract means by "the
admitted discovery-observation input".

**Aggregation, never multiplication.** Admitted observations that canonicalise to the same
identity become one candidate naming every source that contributed it and every accepted form
that was seen. Seeing a page twice is not a defect of the website, not an exclusion and not a
penalty: it is the ordinary consequence of a page being both in a sitemap and in a menu.

**Order cannot matter.** Observations are read in a canonical order and every collection a
candidate carries is emitted sorted, so a run that enumerated a sitemap before a menu produces
exactly the population of a run that did it the other way round.

A raw anchor label reaches this module as a transient classification signal and leaves it
again: no candidate carries one, because ``site-inventory.v1`` does not represent anchor text
and D-PXAPI19-PO-007 keeps it out of the canonical inventory.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from pxapi.domain.page_classification import classify
from pxapi.domain.site_identity import (
    CANONICALISATION_VERSION,
    canonical_origin,
    canonical_url_key,
    is_page_resource,
    is_persistable_form,
    is_same_origin,
)

#: The discovery method this slice is, and its version. Both travel with every inventory: two
#: inventories of one site are comparable only when the method and the version agree. The
#: version is bound to the canonicalisation version rather than restated, because the keys the
#: method produces *are* its output and a change to those rules is a change to this method.
DISCOVERY_METHOD: Final = "SAME_ORIGIN_PUBLIC_DISCOVERY"
DISCOVERY_METHOD_VERSION: Final = CANONICALISATION_VERSION


class SourceId(StrEnum):
    """The discovery sources this method attempts.

    ``site-inventory.v1`` holds the source vocabulary **open** — a later slice adds a source
    without a schema change — so this enum names the sources *this* method attempts and is
    deliberately not a closed contract vocabulary.
    """

    #: The canonical target seed: the origin the bootstrap established.
    CANONICAL_SEED = "CANONICAL_SEED"
    #: ``/robots.txt``, read for ``Sitemap:`` declarations and for nothing else.
    ROBOTS_DECLARATION = "ROBOTS_DECLARATION"
    #: Every same-origin sitemap document read, index documents included.
    SITEMAP = "SITEMAP"
    #: Sitemap references that point outside the established origin. They are never fetched,
    #: and they are reported as a source of their own so that refusing them stays visible
    #: rather than being folded into the outcome of the sitemaps that were read.
    OFF_ORIGIN_SITEMAP = "OFF_ORIGIN_SITEMAP"
    #: Same-origin links read out of the static HTML of the seed document.
    SAME_ORIGIN_PAGE_LINKS = "SAME_ORIGIN_PAGE_LINKS"


class SourceOutcome(StrEnum):
    """What became of one attempted source: the contract's closed vocabulary, verbatim.

    Every value names the analysis process. None is a website-quality polarity and none may be
    rendered as one: an absent sitemap, a malformed source, an exhausted budget, a refusal, a
    failure and a timeout are all facts about *this analysis*.
    """

    USED = "USED"
    EMPTY = "EMPTY"
    ABSENT = "ABSENT"
    MALFORMED = "MALFORMED"
    NO_SITEMAP_DECLARATION = "NO_SITEMAP_DECLARATION"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TARGET_POLICY_REFUSED = "TARGET_POLICY_REFUSED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIMEOUT = "TIMEOUT"


#: The outcomes under which a candidate could have been admitted from the source at all.
ADMITTING_OUTCOMES: Final[frozenset[SourceOutcome]] = frozenset(
    {SourceOutcome.USED, SourceOutcome.BUDGET_EXHAUSTED, SourceOutcome.TIMEOUT}
)


class BootstrapFailure(StrEnum):
    """Why no canonical public origin could be established. Every value names our side.

    A bootstrap failure produces **no** inventory and **no** manifest (D-PXAPI19-PO-006): a
    document that existed anyway would have to carry zero candidates, and would then read as
    "this site has no pages" when what happened is that discovery never started.
    """

    #: Our own target policy refused the target, before any connection was opened.
    TARGET_REFUSED = "TARGET_REFUSED"
    #: The target could not be reached: it did not resolve, or no connection held.
    UNREACHABLE = "UNREACHABLE"
    #: A time budget elapsed before the origin could be established.
    TIMEOUT = "TIMEOUT"
    #: Our own runtime failed in a way it did not anticipate before an origin was established.
    RUNTIME_ERROR = "RUNTIME_ERROR"


class DiscoveryStage(StrEnum):
    """The stages one discovery run executes. ``stage_id`` is an open token on its contract."""

    #: Establishing the origin and reading every discovery source.
    SITE_DISCOVERY = "SITE_DISCOVERY"
    #: Choosing, deterministically, which candidates the run sets out to analyse.
    SAMPLING_PLAN = "SAMPLING_PLAN"


class Eligibility(StrEnum):
    """Whether a candidate is a technically admissible acquisition target."""

    ELIGIBLE = "ELIGIBLE"
    EXCLUDED = "EXCLUDED"


class ExclusionReason(StrEnum):
    """Why a candidate is not admissible. Every value names this analysis or its boundary."""

    OFF_ORIGIN = "OFF_ORIGIN"
    NON_PAGE_RESOURCE = "NON_PAGE_RESOURCE"
    TARGET_POLICY_REFUSED = "TARGET_POLICY_REFUSED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class DiscoveryObservation:
    """One URL as one source actually wrote it, with the transient signal that came with it.

    ``label`` is the normalised anchor text a link carried, already bounded by the adapter
    that read it. It lets the classifier use a menu entry reading "Kontakt" to place a page
    whose path says nothing, and it is deliberately **not** part of any candidate.
    """

    observed_form: str
    source_id: str
    label: str | None = None


@dataclass(frozen=True)
class SourceAttempt:
    """One attempted source and the neutral technical state the attempt ended in."""

    source_id: str
    outcome: SourceOutcome


@dataclass(frozen=True)
class DiscoveryReport:
    """Everything a discovery provider established, in provider-neutral terms.

    It is the whole of what crosses the ``SiteDiscoveryPort`` boundary: no response body, no
    header, no status code and no provider identity. A provider reports what it observed and
    what became of each source it tried; every decision about what that means is made on this
    side of the boundary.

    ``target_origin`` is ``None`` exactly when the bootstrap established no canonical public
    origin, and ``bootstrap_failure`` then says why in our own terms. The provider reports the
    seed itself, as a ``CANONICAL_SEED`` observation: the producer refuses to emit an inventory
    whose seed is missing rather than inventing one the provider never observed.
    """

    target_origin: str | None
    observations: tuple[DiscoveryObservation, ...] = ()
    attempts: tuple[SourceAttempt, ...] = ()
    bootstrap_failure: BootstrapFailure | None = None


@dataclass(frozen=True)
class Candidate:
    """One discovered target under its canonical identity, ready to be written out.

    Every collection is already in canonical order: the order a producer visited its sources
    in must not survive into a document whose digest is meant to be a digest of a set.
    """

    url_key: str
    observed_forms: tuple[str, ...]
    provenance: tuple[str, ...]
    eligibility: Eligibility
    exclusion_reason: ExclusionReason | None = None
    page_type: str | None = None

    @property
    def is_eligible(self) -> bool:
        return self.eligibility is Eligibility.ELIGIBLE


@dataclass
class _Accumulator:
    """The forms, sources and labels seen for one identity while observations are folded in."""

    observed_forms: set[str] = field(default_factory=set)
    provenance: set[str] = field(default_factory=set)
    labels: set[str] = field(default_factory=set)


def is_admissible(observation: DiscoveryObservation) -> bool:
    """Whether one observation may enter the population at all.

    Both halves are required. A form the contract cannot persist is not recorded verbatim, and
    rewriting it would record something nobody served; a form with no canonical identity has
    nothing to aggregate onto. A credential-bearing URL fails both, which is the point.
    """
    return (
        is_persistable_form(observation.observed_form)
        and canonical_url_key(observation.observed_form) is not None
    )


def admitted_observations(
    observations: Iterable[DiscoveryObservation],
) -> tuple[DiscoveryObservation, ...]:
    """The observations that may enter the population, in canonical order.

    Sorted rather than kept in the sequence they were handed, because that is the rule the
    inventory's ``input_digest`` declares: enumeration order must not be able to change it.
    Duplicates collapse here too — two identical observations are one admitted input.
    """
    admitted = {o for o in observations if is_admissible(o)}
    return tuple(sorted(admitted, key=lambda o: (o.observed_form, o.source_id, o.label or "")))


def observation_records(admitted: Iterable[DiscoveryObservation]) -> list[dict[str, str]]:
    """The admitted observations in the shape the inventory's ``input_digest`` covers.

    The label is deliberately absent: it is never admitted into the document, so it is not
    part of the input the document binds itself to. A label that changes a classification
    changes the ``output_digest``, which is where that consequence becomes visible.
    """
    unique = {(o.observed_form, o.source_id) for o in admitted}
    return [{"observed_form": form, "source_id": source} for form, source in sorted(unique)]


def assemble_candidates(
    admitted: Iterable[DiscoveryObservation], target_origin: str
) -> tuple[Candidate, ...]:
    """The candidate population one set of admitted observations reduces to, sorted by key."""
    origin = canonical_origin(target_origin)
    if origin is None:
        raise ValueError("assemble_candidates needs an established canonical origin")

    folded: dict[str, _Accumulator] = {}
    for observation in admitted_observations(admitted):
        key = canonical_url_key(observation.observed_form)
        if key is None:  # pragma: no cover - admitted_observations already refused it
            continue
        entry = folded.setdefault(key, _Accumulator())
        entry.observed_forms.add(observation.observed_form)
        entry.provenance.add(observation.source_id)
        if observation.label:
            entry.labels.add(observation.label)

    return tuple(_candidate_for(key, folded[key], origin) for key in sorted(folded))


def _candidate_for(url_key: str, entry: _Accumulator, origin: str) -> Candidate:
    """One identity's candidate: its admissibility first, then its type if it has one.

    The two exclusions are tested in this order on purpose. A resource outside the authorised
    origin is outside it whatever its file extension says, and naming the extension instead
    would report a boundary this run never even reached. Neither is a defect of the page.

    An excluded candidate is left unclassified: this analysis will not fetch it, so placing it
    in a methodology bucket would assert a page type nobody observed.
    """
    if not is_same_origin(url_key, origin):
        reason: ExclusionReason | None = ExclusionReason.OFF_ORIGIN
    elif not is_page_resource(url_key):
        reason = ExclusionReason.NON_PAGE_RESOURCE
    else:
        reason = None

    return Candidate(
        url_key=url_key,
        observed_forms=tuple(sorted(entry.observed_forms)),
        provenance=tuple(sorted(entry.provenance)),
        eligibility=Eligibility.ELIGIBLE if reason is None else Eligibility.EXCLUDED,
        exclusion_reason=reason,
        page_type=None
        if reason is not None
        else classify(url_key, origin, tuple(sorted(entry.labels))),
    )


def source_candidate_counts(candidates: Iterable[Candidate]) -> dict[str, int]:
    """How many candidates each source contributed, keyed by ``source_id``.

    It counts what *this inventory admitted*, which is deliberately not what the source
    declared: a sitemap listing a thousand URLs of which two survived admission contributed
    two. Zero therefore means nothing was admitted from that source here — never that the
    source declared nothing, and never that the site has no such pages.
    """
    counts: dict[str, int] = {}
    for candidate in candidates:
        for source_id in candidate.provenance:
            counts[source_id] = counts.get(source_id, 0) + 1
    return counts
