"""Reading a *generically applicable* noindex directive out of what a response declared.

Three properties are asserted here, and each is a decision this slice had to make explicitly.

**Generic means "not addressed to a named crawler".** ``<meta name="robots">`` is generic and
``<meta name="googlebot">`` is not; an unscoped ``X-Robots-Tag: noindex`` is generic and
``X-Robots-Tag: googlebot: noindex`` is not. A directive addressed to one named crawler is
simply *outside* the generic verdict — it does not make the generic verdict true, and it does
not make it unknown either.

**A colon is placed by the rule name in front of it, not guessed.** ``X-Robots-Tag`` uses a
colon both to address a crawler and to give a rule a value, and the four rule names whose own
syntax carries a value are known, so ``max-snippet: 20, noindex`` is a generic rule list and
``googlebot: follow, noindex`` is scoped to one named crawler. Both are settled answers.
``INDETERMINATE`` is kept for syntax that really is unresolvable — a colon with no name before
it, and a rule we model as taking no value being handed one — and it is never "false".

**Nothing here knows about HTTP, HTML or contracts.** The functions take strings and return a
verdict. Whether a channel could be inspected at all — a truncated read, an unreadable
document, a response that is not a document — is the caller's decision, and arrives here only
as the ``NOT_APPLICABLE`` and ``UNASSESSED`` members it may hand back to the combiner.
"""

from __future__ import annotations

import pytest

from pxapi.domain.indexability import (
    VALUE_BEARING_RULES,
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
        "googlebot: noindex",
        "googlebot: noindex, nofollow",
        "googlebot:noindex",
        "GOOGLEBOT: NOINDEX",
        "bingbot: noindex",
        "otherbot: none",
        "nofollow, googlebot: noindex",
        # A whole rule list scoped to one named crawler, however many rules it carries and
        # wherever the noindex sits in it. The scope is set once, by the first name.
        "googlebot: follow, noindex",
        "otherbot: follow, none",
        "googlebot: nosnippet, noarchive, none",
        "GoogleBot: Follow, NoIndex",
        "googlebot: unavailable_after: 2026-06-30, noindex",
        # A generic rule carrying a value, on a list that then declares no noindex.
        "max-image-preview: large",
        "max-snippet: 20, follow",
        "MAX-SNIPPET: 20, FOLLOW",
        "unavailable_after: 2026-06-30",
        "max-video-preview: -1, index, follow",
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
        "unavailable_after: 2026-06-30, noindex",
        "max-snippet: 20, noindex",
        "max-image-preview: large, none",
        "max-video-preview: -1, noindex",
        "max-snippet: 20, none",
        # The same, spelled in any case, and without the optional space after the colon.
        "MAX-SNIPPET: 20, NOINDEX",
        "Unavailable_After: 2026-06-30, None",
        "max-snippet:20,noindex",
        # More than one rule carries a value, and the noindex is last. Still generic.
        "max-snippet: 20, unavailable_after: 2026-06-30, noindex",
        # And the value-bearing rule need not lead for the list to stay generic.
        "noindex, max-snippet: 20",
    ],
)
def test_a_generic_rule_carrying_a_value_leaves_the_rules_after_it_generic(
    field_value: str,
) -> None:
    """The repair: a rule name whose own syntax uses ``:`` addresses no crawler.

    Withholding these would turn our own parser's gap into ``UNKNOWN`` on a field value whose
    syntax is well formed and whose ``noindex`` is generically applicable.
    """
    assert x_robots_tag_generic_noindex([field_value]) is PRESENT


@pytest.mark.parametrize(
    "field_value",
    [
        # A colon with no name before it: nothing is named and nothing is declared.
        ": noindex",
        ":noindex",
        # `noindex` and `none` take no value, so a value makes this malformed however it is
        # read. It must not silently become a crawler named `noindex` either.
        "noindex: yes",
        "none: 1",
        "NOINDEX: YES",
        "None: 1",
        "noindex: yes, none",
        "noindex: yes, follow",
    ],
)
def test_genuinely_unresolvable_syntax_establishes_nothing(field_value: str) -> None:
    """Never ``false``: hiding a directive we could not place would be the worse error."""
    assert x_robots_tag_generic_noindex([field_value]) is INDETERMINATE


def test_the_value_bearing_rule_vocabulary_is_exactly_these_four_names() -> None:
    """Canary: this bounded set is what places a colon, so widening it silently changes verdicts.

    Pinned as a whole set rather than by sampling a member, so adding a fifth name is a
    deliberate, visible change to rule version ``1.0.0`` rather than a passing test.
    """
    known_in_this_rule_version = frozenset(
        {"unavailable_after", "max-snippet", "max-image-preview", "max-video-preview"}
    )
    assert known_in_this_rule_version == VALUE_BEARING_RULES


def test_an_unrecognised_name_before_a_colon_is_read_as_a_crawler_scope() -> None:
    """The stated boundary of that bounded vocabulary, asserted rather than left implicit.

    A name this rule version does not know as value-bearing is read as a named crawler, so a
    colon-valued rule introduced *after* this rule version would be read as a scope and answer
    ``ABSENT``. That is version work, not something the parser guesses at run time.
    """
    assert x_robots_tag_generic_noindex(["otherbot: follow, none"]) is ABSENT
    assert x_robots_tag_generic_noindex(["max-audio-preview: 5, noindex"]) is ABSENT
    assert x_robots_tag_generic_noindex(["nofollow: yes, noindex"]) is ABSENT


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
    ("lines", "once_folded"),
    [
        # The join lets a crawler name scope a directive that arrived generic, and the result
        # is not merely unknown — it is the opposite of what the server sent.
        (["googlebot: follow", "noindex"], ABSENT),
        # And here it lets a malformed leading rule swallow a directive that arrived clear.
        (["noindex: yes", "noindex"], INDETERMINATE),
    ],
)
def test_joining_repeated_headers_destroys_an_established_directive(
    lines: list[str], once_folded: GenericNoindex
) -> None:
    """Why folding is refused: the separator between lines is the separator inside one.

    ``getheader`` folds repeated field lines into one comma-separated string, and a comma is
    exactly what separates directives *inside* a single value. Both examples establish the
    directive as they arrived and stop establishing it once folded.
    """
    assert x_robots_tag_generic_noindex(lines) is PRESENT
    assert x_robots_tag_generic_noindex([", ".join(lines)]) is once_folded


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
