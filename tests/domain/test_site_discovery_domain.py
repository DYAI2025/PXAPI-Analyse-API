"""Admission, aggregation and admissibility: from observations to one candidate population."""

from __future__ import annotations

import random

import pytest

from pxapi.domain.site_discovery import (
    DiscoveryObservation,
    Eligibility,
    ExclusionReason,
    admitted_observations,
    assemble_candidates,
    is_admissible,
    observation_records,
    source_candidate_counts,
)

ORIGIN = "https://example.com/"


def obs(form: str, source: str = "SITEMAP", label: str | None = None) -> DiscoveryObservation:
    return DiscoveryObservation(form, source, label)


OBSERVATIONS = (
    obs("https://example.com", "CANONICAL_SEED"),
    obs("https://example.com/", "SAME_ORIGIN_PAGE_LINKS"),
    obs("https://example.com/leistungen", "SITEMAP"),
    obs("https://example.com/leistungen?utm_source=newsletter", "SAME_ORIGIN_PAGE_LINKS"),
    obs("https://example.com/seite-x", "SAME_ORIGIN_PAGE_LINKS", "Kontakt"),
    obs("https://example.com/broschuere.pdf", "SITEMAP"),
    obs("https://cdn.example.com/katalog.pdf", "SITEMAP"),
)


def test_a_credential_bearing_observation_is_not_admitted() -> None:
    assert not is_admissible(obs("https://user:secret@example.com/x"))
    assert admitted_observations([obs("https://user:secret@example.com/x")]) == ()


def test_an_observation_whose_verbatim_form_the_contract_refuses_is_not_admitted() -> None:
    """It has a key, but the form would be persisted verbatim and would fail ``public_url``."""
    assert not is_admissible(obs("HTTPS://example.com/x"))


def test_admission_sorts_and_collapses_identical_observations() -> None:
    doubled = admitted_observations([*OBSERVATIONS, *OBSERVATIONS])
    assert doubled == admitted_observations(OBSERVATIONS)
    assert list(doubled) == sorted(
        doubled, key=lambda o: (o.observed_form, o.source_id, o.label or "")
    )


def test_the_input_records_bind_a_label_where_one_was_observed_and_no_rejected_form() -> None:
    """The label is transient in the *document*; it is not transient in the input the document's
    input_digest binds, because it changed a classification. A record carries it only when the
    observation did, so a label-free input keeps exactly the 19.A record shape."""
    records = observation_records(
        admitted_observations([*OBSERVATIONS, obs("https://user:pw@example.com/", "SITEMAP")])
    )
    labelled = [r for r in records if "label" in r]
    assert [r["observed_form"] for r in labelled] == ["https://example.com/seite-x"]
    assert all(set(r) == {"observed_form", "source_id"} for r in records if "label" not in r)
    assert not any("user:pw" in record["observed_form"] for record in records)
    assert records == sorted(records, key=lambda r: (r["observed_form"], r["source_id"]))


def test_two_forms_of_one_page_become_one_candidate_with_aggregated_provenance() -> None:
    candidates = {c.url_key: c for c in assemble_candidates(OBSERVATIONS, ORIGIN)}
    offer = candidates["https://example.com/leistungen"]
    assert offer.observed_forms == (
        "https://example.com/leistungen",
        "https://example.com/leistungen?utm_source=newsletter",
    )
    assert offer.provenance == ("SAME_ORIGIN_PAGE_LINKS", "SITEMAP")
    assert offer.is_eligible


def test_duplication_is_neither_an_exclusion_nor_a_second_candidate() -> None:
    candidates = assemble_candidates(OBSERVATIONS, ORIGIN)
    keys = [c.url_key for c in candidates]
    assert len(keys) == len(set(keys))
    offer = next(c for c in candidates if c.url_key.endswith("/leistungen"))
    assert offer.eligibility is Eligibility.ELIGIBLE and offer.exclusion_reason is None


def test_the_population_does_not_depend_on_the_order_observations_arrived_in() -> None:
    reference = assemble_candidates(OBSERVATIONS, ORIGIN)
    shuffler = random.Random(7)
    for _ in range(25):
        shuffled = list(OBSERVATIONS)
        shuffler.shuffle(shuffled)
        assert assemble_candidates(shuffled, ORIGIN) == reference


def test_outside_the_origin_is_reported_before_the_suffix_is_even_read() -> None:
    candidates = {c.url_key: c for c in assemble_candidates(OBSERVATIONS, ORIGIN)}
    assert candidates["https://cdn.example.com/katalog.pdf"].exclusion_reason is (
        ExclusionReason.OFF_ORIGIN
    )
    assert candidates["https://example.com/broschuere.pdf"].exclusion_reason is (
        ExclusionReason.NON_PAGE_RESOURCE
    )


def test_an_excluded_candidate_carries_no_page_type() -> None:
    for candidate in assemble_candidates(OBSERVATIONS, ORIGIN):
        if not candidate.is_eligible:
            assert candidate.page_type is None


def test_a_transient_label_places_a_page_and_is_carried_by_no_candidate() -> None:
    candidates = {c.url_key: c for c in assemble_candidates(OBSERVATIONS, ORIGIN)}
    assert candidates["https://example.com/seite-x"].page_type == "CONTACT"
    assert not any("Kontakt" in repr(candidate) for candidate in candidates.values())


def test_the_label_order_cannot_change_a_classification() -> None:
    forward = [obs(ORIGIN + "seite-x", label="Impressum"), obs(ORIGIN + "seite-x", label="Kontakt")]
    for ordering in (forward, list(reversed(forward))):
        (page,) = [c for c in assemble_candidates(ordering, ORIGIN) if c.url_key != ORIGIN]
        assert page.page_type == "LEGAL"


def test_a_source_counts_the_candidates_it_contributed_not_the_entries_it_declared() -> None:
    counts = source_candidate_counts(assemble_candidates(OBSERVATIONS, ORIGIN))
    assert counts == {"CANONICAL_SEED": 1, "SAME_ORIGIN_PAGE_LINKS": 3, "SITEMAP": 3}


def test_the_domain_never_invents_a_seed_the_provider_did_not_observe() -> None:
    """The producer refuses a seedless inventory instead; see the application tests."""
    candidates = assemble_candidates([obs(ORIGIN + "kontakt")], ORIGIN)
    assert ORIGIN not in {c.url_key for c in candidates}


def test_assembly_needs_an_established_origin() -> None:
    with pytest.raises(ValueError):
        assemble_candidates(OBSERVATIONS, "https://user@example.com/")
