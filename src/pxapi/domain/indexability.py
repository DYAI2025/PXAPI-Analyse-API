"""Whether a response declared a *generically applicable* noindex directive.

The whole module answers one question, on two channels a single homepage response can carry it:
an HTML ``<meta name="robots">`` declaration, and an ``X-Robots-Tag`` response header. It reads
strings and returns a verdict. It knows nothing about HTTP, HTML parsing or contracts.

Three decisions are made here, and each is a business decision rather than a parsing detail.

**Generic means "not addressed to a named crawler".** ``<meta name="robots">`` is generic;
``<meta name="googlebot">`` is a different declaration and is not collected at all. An unscoped
``X-Robots-Tag: noindex`` is generic; ``X-Robots-Tag: googlebot: noindex`` is addressed to one
crawler and is therefore *outside* the generic verdict — it does not establish it, and it does
not withhold it either. This slice deliberately infers nothing about how any named crawler
behaves.

**A colon is ambiguous, and ambiguity is answered honestly.** ``X-Robots-Tag`` uses ``:`` both
to address a crawler and to give a directive a value, so ``unavailable_after: <date>, noindex``
has two readings: one where a crawler named ``unavailable_after`` scopes everything after it,
and one where that ``noindex`` is generic. Settling it would need a registry of every serving
directive, which this slice does not build. Where the two readings disagree the answer is
``INDETERMINATE`` — never ``ABSENT``, because hiding a directive we could not place is the
error that turns our own uncertainty into a claim about the site.

**A channel that could not be inspected never becomes an absence.** ``NOT_APPLICABLE`` and
``UNASSESSED`` are produced by the caller, not here — only the caller knows whether the
response was a document, whether the read was truncated, or whether our own parser failed — but
the combiner has to know what to do with them, so they are members of this vocabulary.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Final


class GenericNoindex(StrEnum):
    """What one observation channel established about a generically applicable noindex.

    The first three are what a channel can establish from what it read. The last two are what
    a caller hands the combiner about a channel it could not read, and they are deliberately
    different from each other: a channel that does not apply leaves the combination free to
    conclude, and a channel we failed to assess does not.
    """

    #: A generic noindex directive was observed on this channel.
    PRESENT = "PRESENT"
    #: This channel was assessed in full and declared no generic noindex directive.
    ABSENT = "ABSENT"
    #: The channel was assessed and established nothing — the syntax does not say whether a
    #: directive is generic, or the read could not have seen every declaration.
    INDETERMINATE = "INDETERMINATE"
    #: This channel does not exist for this response at all, such as an HTML declaration in a
    #: response that is not a document. A fact about the measurement, not about the site.
    NOT_APPLICABLE = "NOT_APPLICABLE"
    #: Our process could not assess this channel. A fact about our run, not about the site.
    UNASSESSED = "UNASSESSED"


#: The directive tokens that establish the condition this slice observes. ``none`` is included
#: because it is the conventional equivalent of ``noindex, nofollow``; the set is deliberately
#: this short, because modelling every robots serving directive is not what B1 is for.
NOINDEX_DIRECTIVES: Final[frozenset[str]] = frozenset({"noindex", "none"})


def _directives(declaration: str) -> list[str]:
    """The comma-separated directives of one declaration, blanks dropped.

    An entry that is nothing but whitespace is not a directive, so it is dropped rather than
    carried through as an empty token that no comparison could match anyway.
    """
    return [token.strip() for token in declaration.split(",") if token.strip()]


def _states_noindex(directives: Iterable[str]) -> bool:
    """Whether any of these directives is a bare noindex token. Case-insensitive."""
    return any(directive.lower() in NOINDEX_DIRECTIVES for directive in directives)


def meta_robots_generic_noindex(contents: Sequence[str]) -> GenericNoindex:
    """The verdict for the HTML channel, from the ``content`` of each generic robots meta.

    Every entry is already known to be generic: a crawler-specific declaration names the
    crawler in ``name=``, so it is a different declaration and never reaches this function.
    There is therefore no scope to parse and no ambiguity to report — this channel answers
    only ``PRESENT`` or ``ABSENT``.

    An empty sequence means the document declared no generic robots meta, which is an absence
    of the directive. Whether the document was read *completely* is a different question, and
    the caller owns it: only the caller knows the read was truncated.
    """
    for content in contents:
        if _states_noindex(_directives(content)):
            return GenericNoindex.PRESENT
    return GenericNoindex.ABSENT


def _field_value_generic_noindex(field_value: str) -> GenericNoindex:
    """The verdict for one physical ``X-Robots-Tag`` field value.

    Only the first directive may carry a crawler name, and it does so as ``name:``. The same
    syntax is how a directive carries a value, so the field value is read *both* ways and the
    two readings are compared:

    * **scoped** — ``name`` addresses a crawler, so every directive here is addressed to it
      and none of them is generic. This reading always yields ``ABSENT``.
    * **unscoped** — ``name`` is itself a directive carrying a value, so no crawler is named
      and every directive here is generic.

    Agreeing readings are the answer. Disagreeing readings mean the syntax genuinely does not
    say whether the directive is generic, and that is ``INDETERMINATE``.
    """
    directives = _directives(field_value)
    if not directives:
        # A field value with no directive in it declares nothing. That is an absence of a
        # directive, and deliberately not a failure to read one.
        return GenericNoindex.ABSENT

    name, colon, _ = directives[0].partition(":")
    if not colon:
        # No crawler name is possible here, so there is only one reading.
        return GenericNoindex.PRESENT if _states_noindex(directives) else GenericNoindex.ABSENT

    scope = name.strip()
    if not scope:
        # A colon with nothing before it names no crawler and is no directive either.
        return GenericNoindex.INDETERMINATE

    scoped_reading = GenericNoindex.ABSENT
    unscoped_reading = (
        GenericNoindex.PRESENT
        if _states_noindex([scope, *directives[1:]])
        else GenericNoindex.ABSENT
    )
    if scoped_reading is unscoped_reading:
        return scoped_reading
    return GenericNoindex.INDETERMINATE


def x_robots_tag_generic_noindex(field_values: Sequence[str]) -> GenericNoindex:
    """The verdict for the response-header channel, over every physical field value.

    The values are kept apart rather than joined, because the separator between two header
    lines is the same comma that separates directives *inside* one line: joining
    ``googlebot: follow`` and ``noindex`` yields one crawler-scoped value and establishes the
    opposite of what arrived.

    An empty sequence means the response declared no such header, which is an absence of the
    directive on a channel that was fully assessed — the headers of a response we received are
    always readable.
    """
    if not field_values:
        return GenericNoindex.ABSENT
    return combined_generic_noindex(
        *(_field_value_generic_noindex(value) for value in field_values)
    )


def combined_generic_noindex(*channels: GenericNoindex) -> GenericNoindex:
    """The one verdict for the response, from what each channel established.

    The order of the rules is the whole semantics:

    * one channel that established the directive is enough — the other channels cannot
      un-observe it;
    * otherwise one channel that established nothing, or that we could not assess at all,
      forbids concluding an absence, because what we did not see is not what is not there;
    * otherwise every channel that applies was assessed and found nothing, which is a real
      absence;
    * and where no channel applied at all there is nothing to state.

    Commutative and total by construction, so two runs over the same channels agree and no
    combination of members falls through unanswered.
    """
    if GenericNoindex.PRESENT in channels:
        return GenericNoindex.PRESENT
    if any(
        channel in {GenericNoindex.INDETERMINATE, GenericNoindex.UNASSESSED} for channel in channels
    ):
        return GenericNoindex.INDETERMINATE
    if GenericNoindex.ABSENT in channels:
        return GenericNoindex.ABSENT
    return GenericNoindex.NOT_APPLICABLE
