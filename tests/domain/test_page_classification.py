"""The page-type classifier: the accepted classes, the neutral ``None``, and determinism."""

from __future__ import annotations

import re
from itertools import combinations, permutations

import pytest

from pxapi.domain import page_classification as pc
from pxapi.domain.page_classification import HOMEPAGE, UNCLASSIFIED, classify
from tests.contracts.support import CONTRACTS, load_json

ORIGIN = "https://example.com/"
CODE = re.compile(load_json(CONTRACTS.schema_path("common"))["$defs"]["code"]["pattern"])

#: The bounded initial semantic classes PXAPI-19 names, by the token this classifier uses.
REQUIRED_CLASSES = {"HOMEPAGE", "OFFER", "PROOF", "ABOUT", "CONTACT", "LEGAL", "KNOWLEDGE"}


@pytest.mark.parametrize(
    ("path", "page_type"),
    [
        ("leistungen", "OFFER"),
        ("unsere-leistungen", "OFFER"),
        ("services/webdesign", "OFFER"),
        ("preise", "OFFER"),
        ("referenzen", "PROOF"),
        ("case-studies/kunde-a", "PROOF"),
        ("ueber-uns", "ABOUT"),
        ("ueber_uns", "ABOUT"),
        ("team", "ABOUT"),
        ("kontakt", "CONTACT"),
        ("kontakt.html", "CONTACT"),
        ("angebot-anfordern", "CONTACT"),
        ("index.php?id=kontakt", "CONTACT"),
        ("impressum", "LEGAL"),
        ("datenschutz", "LEGAL"),
        ("impressum-faq", "LEGAL"),
        ("faq", "KNOWLEDGE"),
        ("blog/ein-artikel", "KNOWLEDGE"),
    ],
)
def test_a_path_places_a_page_in_its_class(path: str, page_type: str) -> None:
    assert classify(ORIGIN + path, ORIGIN) == page_type


def test_the_seed_is_the_homepage_by_construction() -> None:
    assert classify(ORIGIN, ORIGIN) == HOMEPAGE
    assert classify(ORIGIN, ORIGIN, ("Impressum",)) == HOMEPAGE


def test_a_page_this_version_cannot_place_is_left_unplaced() -> None:
    """``None`` is the neutral answer: the manifest counts it under ``UNCLASSIFIED``."""
    assert classify(ORIGIN + "xyz123", ORIGIN) is None


def test_matching_is_whole_word_so_a_longer_word_never_matches_by_accident() -> None:
    assert classify(ORIGIN + "teamsport", ORIGIN) is None
    assert classify(ORIGIN + "servicestelle", ORIGIN) is None


def test_a_label_places_a_page_only_when_its_path_says_nothing() -> None:
    assert classify(ORIGIN + "seite-7", ORIGIN, ("Kontakt aufnehmen",)) == "CONTACT"
    assert classify(ORIGIN + "leistungen", ORIGIN, ("Kontakt",)) == "OFFER"


def test_the_first_label_that_places_a_page_wins_in_the_order_given() -> None:
    """Callers sort labels first, so the order links were met in cannot change the result."""
    assert classify(ORIGIN + "seite-7", ORIGIN, ("Impressum", "Kontakt")) == "LEGAL"
    assert classify(ORIGIN + "seite-7", ORIGIN, ("Kontakt", "Impressum")) == "CONTACT"


def test_a_label_over_the_bound_is_dropped_rather_than_truncated() -> None:
    overlong = ("Kontakt " * 30).strip()
    assert len(overlong) > pc.MAX_LABEL_LENGTH
    assert classify(ORIGIN + "seite-7", ORIGIN, (overlong,)) is None


def test_the_same_input_always_yields_the_same_class() -> None:
    for labels in permutations(("Blog", "Team", "Preise")):
        sorted_labels = tuple(sorted(labels))
        assert classify(ORIGIN + "seite-7", ORIGIN, sorted_labels) == classify(
            ORIGIN + "seite-7", ORIGIN, tuple(sorted(("Preise", "Blog", "Team")))
        )


# --- the vocabulary ---------------------------------------------------------------------------


def test_the_classes_cover_every_accepted_methodology_class() -> None:
    assert {*pc.PAGE_TYPES, HOMEPAGE} == REQUIRED_CLASSES


def test_every_token_is_a_contract_code() -> None:
    """``page_type`` and ``stratum`` are ``common#/$defs/code``: an open token of that shape."""
    for token in (*pc.PAGE_TYPES, HOMEPAGE, UNCLASSIFIED, pc.CLASSIFIER):
        assert CODE.search(token), token


def test_no_word_places_a_page_in_two_classes() -> None:
    """A shared word would make the class depend on the declared order alone, silently."""
    for left, right in combinations(pc.PAGE_TYPES, 2):
        shared = pc._VOCABULARY[left] & pc._VOCABULARY[right]
        assert shared == set(), f"{left} and {right} share {sorted(shared)}"


def test_every_declared_class_has_a_vocabulary_and_nothing_else_does() -> None:
    assert set(pc._VOCABULARY) == set(pc.PAGE_TYPES)


def test_unclassified_is_not_a_class_a_page_can_be_placed_in() -> None:
    """The neutral bucket is the manifest's, never a verdict the classifier returns."""
    assert UNCLASSIFIED not in pc.PAGE_TYPES
    assert UNCLASSIFIED != HOMEPAGE
