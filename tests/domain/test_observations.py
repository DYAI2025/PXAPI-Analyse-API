"""Normalising an observed text, and deciding whether the contract can carry it.

These are the two decisions that stand between a raw page and a published value, and both are
places where a convenient answer would be a false one: a text folded to nothing is not a value,
and a text too long for the contract must not be shortened into something the site never said.
"""

from __future__ import annotations

import pytest

from pxapi.domain.observations import (
    COLLECTOR,
    COLLECTOR_VERSION,
    Metric,
    Stage,
    normalise_single_line,
    representable_text,
)

#: The bound the contracts actually declare for a single-line text.
BOUND = 500


# --- normalisation ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("plain", "plain"),
        ("  leading and trailing  ", "leading and trailing"),
        ("one\ntwo", "one two"),
        ("one\r\ntwo", "one two"),
        ("one\ttwo", "one two"),
        ("one \n\t two", "one two"),
        ("collapse    many     spaces", "collapse many spaces"),
        ("line\u2028separator", "line separator"),
        ("paragraph\u2029separator", "paragraph separator"),
        ("control\x00null", "control null"),
        ("c1\x85next-line", "c1 next-line"),
        ("delete\x7fchar", "delete char"),
        ("", ""),
        ("   ", ""),
        ("\n\t\r", ""),
        ("ümlaut and émoji 🎯", "ümlaut and émoji 🎯"),
    ],
)
def test_normalisation_folds_every_separator_to_a_single_space(raw: str, expected: str) -> None:
    assert normalise_single_line(raw) == expected


def test_normalisation_never_joins_two_words_into_one() -> None:
    """Deleting a newline instead of folding it would invent a word that was never written."""
    assert normalise_single_line("Company\nName") == "Company Name"


def test_normalisation_is_idempotent() -> None:
    once = normalise_single_line("  a \n b  ")
    assert normalise_single_line(once) == once


def test_normalisation_is_deterministic() -> None:
    raw = "  mixed \t whitespace \n here "
    assert normalise_single_line(raw) == normalise_single_line(raw)


# --- representability ------------------------------------------------------------------


def test_a_short_text_is_representable() -> None:
    assert representable_text("A title", BOUND) == "A title"


def test_a_text_exactly_on_the_bound_is_representable() -> None:
    assert representable_text("x" * BOUND, BOUND) == "x" * BOUND


def test_a_text_one_character_over_the_bound_is_not() -> None:
    assert representable_text("x" * (BOUND + 1), BOUND) is None


def test_an_overlong_text_is_refused_rather_than_shortened() -> None:
    """The whole point: a shortened value would read like the original and would be false."""
    raw = "y" * 900
    assert representable_text(raw, BOUND) is None


def test_a_text_that_normalises_to_nothing_is_not_representable() -> None:
    for raw in ("", "   ", "\n\t"):
        assert representable_text(raw, BOUND) is None


def test_the_bound_is_applied_after_normalisation() -> None:
    """Whitespace that collapses away must not count against the bound."""
    raw = "a" + (" " * 400) + "b"
    assert representable_text(raw, 10) == "a b"


# --- the vocabulary is stable and lexically valid --------------------------------------

CODE_METRICS = [*Metric, *Stage]


@pytest.mark.parametrize("token", CODE_METRICS, ids=[t.value for t in CODE_METRICS])
def test_every_identifier_is_a_valid_contract_code(token) -> None:
    """`code` is an open vocabulary but not a free-text member: the shape still holds."""
    import re

    assert re.fullmatch(r"[A-Z][A-Z0-9_]+", token.value), token.value
    assert 2 <= len(token.value) <= 64


def test_the_collector_identity_is_a_valid_code_and_label() -> None:
    import re

    assert re.fullmatch(r"[A-Z][A-Z0-9_]+", COLLECTOR)
    assert COLLECTOR_VERSION and len(COLLECTOR_VERSION) <= 120
