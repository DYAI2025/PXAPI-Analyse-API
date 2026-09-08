"""Reading a *generically applicable* noindex directive out of what a response declared.

Three properties are asserted here, and each is a decision this slice had to make explicitly.

**Generic means "not addressed to a named crawler".** ``<meta name="robots">`` is generic and
``<meta name="googlebot">`` is not; an unscoped ``X-Robots-Tag: noindex`` is generic and
``X-Robots-Tag: googlebot: noindex`` is not. A directive addressed to one named crawler is
simply *outside* the generic verdict — it does not make the generic verdict true, and it does
not make it unknown either.

**Ambiguity is a real answer, and it is never "false".** ``X-Robots-Tag`` uses a colon both to
address a crawler and to give a directive a value, so ``unavailable_after: <date>, noindex``
has two readings that disagree about whether that ``noindex`` is generic. Where the two
readings disagree the honest answer is ``INDETERMINATE``, because picking either one would
either invent a directive or hide one.

**Nothing here knows about HTTP, HTML or contracts.** The functions take strings and return a
verdict. Whether a channel could be inspected at all — a truncated read, an unreadable
document, a response that is not a document — is the caller's decision, and arrives here only
as the ``NOT_APPLICABLE`` and ``UNASSESSED`` members it may hand back to the combiner.
"""

from __future__ import annotations

import pytest

from pxapi.domain.indexability import (
    GenericNoindex,
    combined_generic_noindex,
    meta_robots_generic_noindex,
    x_robots_tag_generic_noindex,
)

PRESENT = GenericNoindex.PRESENT
ABSENT = GenericNoindex.ABSENT
INDETERMINATE = GenericNoindex.INDETERMINATE
NOT_APPLICABLE = GenericNoindex.NOT_APPLICABLE
UNASSESSED = GenericNoindex.UNASSESSED


# --- the HTML robots meta channel --------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    [
        "noindex",
        "NOINDEX",
        "NoIndex",
        "  noindex  ",
        "noindex, nofollow",
        "nofollow, noindex",
        "index, noindex",
        "none",
        "NONE",
        "none, nofollow",
        "max-snippet:-1, noindex",
    ],
)
def test_a_generic_robots_declaration_that_says_noindex_establishes_it(content: str) -> None:
    """``none`` counts: it is the conventional equivalent of ``noindex, nofollow``."""
    assert meta_robots_generic_noindex([content]) is PRESENT


@pytest.mark.parametrize(
    "content",
    [
        "index",
        "follow",
        "index, follow",
        "nofollow",
        "noarchive, nosnippet",
        "max-snippet:-1",
        "unavailable_after: 2026-06-30",
        "",
        "   ",
        ",,,",
        "noindexing",
        "no-index",
        "nonesuch",
    ],
)
def test_a_generic_robots_declaration_without_noindex_establishes_its_absence(
    content: str,
) -> None:
    assert meta_robots_generic_noindex([content]) is ABSENT


def test_a_document_that_declared_no_generic_robots_meta_establishes_absence() -> None:
    """A document read in full that says nothing about robots says no generic noindex."""
    assert meta_robots_generic_noindex([]) is ABSENT


def test_any_one_of_several_generic_declarations_can_establish_the_directive() -> None:
    assert meta_robots_generic_noindex(["index, follow", "noindex"]) is PRESENT
    assert meta_robots_generic_noindex(["noindex", "index, follow"]) is PRESENT
    assert meta_robots_generic_noindex(["index", "follow"]) is ABSENT


def test_the_meta_channel_never_reports_ambiguity_of_its_own() -> None:
    """A meta declaration carries no crawler scope: the crawler name lives in ``name=``.

    Whether the document was read completely is the caller's question, not this one's, so the
    only two answers this channel produces are the two it can actually establish.
    """
    answers = {
        meta_robots_generic_noindex([content])
        for content in ("noindex", "index", "", "a: b: c", "noindex: yes", ": noindex")
    }
    assert answers <= {PRESENT, ABSENT}


# --- the X-Robots-Tag response header channel --------------------------------------------


@pytest.mark.parametrize(
    "field_value",
    [
        "noindex",
        "NOINDEX",
        "NoIndex",
        "  noindex  ",
        "noindex, nofollow",
        "nofollow, noindex",
        "none",
        "NONE",
        "none, nofollow",
        "noindex, googlebot: follow",
    ],
)
def test_an_unscoped_noindex_field_value_establishes_the_generic_directive(
    field_value: str,
) -> None:
    assert x_robots_tag_generic_noindex([field_value]) is PRESENT


@pytest.mark.parametrize(
    "field_value",
    [
        "nofollow",
        "noarchive",
        "index, follow",
        "max-image-preview: large",
        "googlebot: noindex",
        "googlebot: noindex, nofollow",
        "googlebot:noindex",
        "GOOGLEBOT: NOINDEX",
        "bingbot: noindex",
        "otherbot: none",
        "nofollow, googlebot: noindex",
        "",
        "   ",
        ",,,",
    ],
)
def test_a_field_value_with_no_generic_noindex_establishes_its_absence(field_value: str) -> None:
    """A directive addressed to one named crawler is outside the generic verdict, not unknown."""
    assert x_robots_tag_generic_noindex([field_value]) is ABSENT


def test_a_response_that_declared_no_such_header_establishes_absence() -> None:
    """The channel was assessed — the response simply carries no directive on it."""
    assert x_robots_tag_generic_noindex([]) is ABSENT


@pytest.mark.parametrize(
    "field_value",
    [
        # Two readings that disagree: `unavailable_after` may be a crawler name scoping the
        # `noindex` that follows, or a directive carrying a value, leaving that `noindex`
        # generic. Nothing in the syntax settles it.
        "unavailable_after: 2026-06-30, noindex",
        "max-snippet: 20, none",
        "googlebot: unavailable_after: 2026-06-30, noindex",
        # A colon with no name before it: neither reading is even available.
        ": noindex",
        ":noindex",
        # `noindex` is not a directive that takes a value, so this is malformed either way.
        "noindex: yes",
        "none: 1",
    ],
)
def test_genuinely_ambiguous_scoping_establishes_nothing(field_value: str) -> None:
    """Never ``false``: hiding a directive we could not place would be the worse error."""
    assert x_robots_tag_generic_noindex([field_value]) is INDETERMINATE


def test_repeated_header_lines_are_each_evaluated_and_any_one_can_establish_it() -> None:
    """The reason the port keeps every physical field value rather than one joined string."""
    assert x_robots_tag_generic_noindex(["googlebot: follow", "noindex"]) is PRESENT
    assert x_robots_tag_generic_noindex(["noindex", "googlebot: follow"]) is PRESENT
    assert x_robots_tag_generic_noindex(["googlebot: noindex", "bingbot: noindex"]) is ABSENT
    assert x_robots_tag_generic_noindex(["nofollow", "noarchive"]) is ABSENT


def test_an_ambiguous_line_beside_a_clear_one_does_not_erase_the_clear_one() -> None:
    assert x_robots_tag_generic_noindex(["noindex", "noindex: yes"]) is PRESENT
    assert x_robots_tag_generic_noindex(["nofollow", "noindex: yes"]) is INDETERMINATE


@pytest.mark.parametrize(
    "lines",
    [
        # The join lets a crawler name appear to scope a directive that arrived generic.
        ["googlebot: follow", "noindex"],
        # And here it lets a directive's own value appear to be a crawler name.
        ["unavailable_after: 2026-06-30", "noindex"],
    ],
)
def test_joining_repeated_headers_destroys_an_established_directive(lines: list[str]) -> None:
    """Why folding is refused: the separator between lines is the separator inside one.

    ``getheader`` folds repeated field lines into one comma-separated string, and a comma is
    exactly what separates directives *inside* a single value. Both examples establish the
    directive as they arrived and stop establishing it once folded.
    """
    assert x_robots_tag_generic_noindex(lines) is PRESENT
    assert x_robots_tag_generic_noindex([", ".join(lines)]) is INDETERMINATE


# --- combining the channels ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("meta", "header", "expected"),
    [
        (PRESENT, ABSENT, PRESENT),
        (ABSENT, PRESENT, PRESENT),
        (PRESENT, PRESENT, PRESENT),
        (PRESENT, INDETERMINATE, PRESENT),
        (INDETERMINATE, PRESENT, PRESENT),
        (ABSENT, ABSENT, ABSENT),
        (ABSENT, INDETERMINATE, INDETERMINATE),
        (INDETERMINATE, ABSENT, INDETERMINATE),
        (INDETERMINATE, INDETERMINATE, INDETERMINATE),
    ],
)
def test_the_combined_result_is_the_smallest_honest_combination(
    meta: GenericNoindex, header: GenericNoindex, expected: GenericNoindex
) -> None:
    """One established channel is enough to establish it; one blind channel forbids a ``false``."""
    assert combined_generic_noindex(meta, header) is expected


def test_a_channel_that_does_not_apply_does_not_hold_the_combination_open() -> None:
    """A response that is not a document has no meta channel to be blind about.

    This is the case that keeps a non-HTML response with a readable ``X-Robots-Tag``
    truthfully representable, without inventing an HTML observation that was never made.
    """
    assert combined_generic_noindex(NOT_APPLICABLE, PRESENT) is PRESENT
    assert combined_generic_noindex(NOT_APPLICABLE, ABSENT) is ABSENT
    assert combined_generic_noindex(NOT_APPLICABLE, INDETERMINATE) is INDETERMINATE


def test_a_channel_our_process_could_not_assess_never_becomes_an_absence() -> None:
    """Our own gap is not a fact about the site, so it can only ever withhold a verdict."""
    assert combined_generic_noindex(UNASSESSED, ABSENT) is INDETERMINATE
    assert combined_generic_noindex(UNASSESSED, INDETERMINATE) is INDETERMINATE
    assert combined_generic_noindex(UNASSESSED, PRESENT) is PRESENT
    assert combined_generic_noindex(UNASSESSED, UNASSESSED) is INDETERMINATE


def test_combining_nothing_applicable_stays_not_applicable() -> None:
    assert combined_generic_noindex() is NOT_APPLICABLE
    assert combined_generic_noindex(NOT_APPLICABLE, NOT_APPLICABLE) is NOT_APPLICABLE


def test_the_combination_does_not_depend_on_the_order_of_the_channels() -> None:
    states = list(GenericNoindex)
    for left in states:
        for right in states:
            assert combined_generic_noindex(left, right) is combined_generic_noindex(right, left)


def test_the_channel_vocabulary_is_exactly_these_five_states() -> None:
    """Canary: a sixth state would fall through the combiner's rules unnoticed."""
    assert [state.value for state in GenericNoindex] == [
        "PRESENT",
        "ABSENT",
        "INDETERMINATE",
        "NOT_APPLICABLE",
        "UNASSESSED",
    ]
