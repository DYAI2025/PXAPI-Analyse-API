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

**A colon is placed by the name in front of it, and what is left over is answered honestly.**
``X-Robots-Tag`` uses ``:`` both to address a crawler and to give a rule its own value, and the
rule names that carry a value are known — this version knows the four in
:data:`VALUE_BEARING_RULES`. So ``max-snippet: 20, noindex`` is a generic rule list whose
``noindex`` applies, and ``googlebot: follow, noindex`` is a rule list scoped to one crawler
that declares nothing generic. Both are settled. ``INDETERMINATE`` is kept for syntax that
genuinely is not: a colon with no name before it, and a rule we model as taking no value being
handed one. It is never ``ABSENT``, because hiding a directive we could not place is the error
that turns our own uncertainty into a claim about the site.

That vocabulary is a bounded parsing aid for this rule version, not a robots registry and not a
scoring model — it says only which names are followed by their own value. Its boundary is a
real limit rather than a hidden one: a colon-valued rule this version does not know is read as
a crawler name, and teaching the parser a new one is version work.

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

#: The robots rule names whose own valid syntax carries a value after a colon, as of rule
#: version ``1.0.0``. This is the *whole* syntax knowledge needed to tell a rule's value from a
#: crawler's name, and deliberately nothing more: it is not a scoring registry, and it models no
#: rule's meaning — only that these names are followed by their own value rather than by a rule
#: list addressed to them. Compared case-insensitively.
VALUE_BEARING_RULES: Final[frozenset[str]] = frozenset(
    {"unavailable_after", "max-snippet", "max-image-preview", "max-video-preview"}
)


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

    Only the first rule may carry a crawler name, and it does so as ``name:``. The same syntax
    is how a rule carries its own value, so the name in front of the colon is what places it,
    and it is read against what rule version ``1.0.0`` knows:

    * **no leading colon** — no crawler can be named here, so every rule is generic;
    * **a name in** :data:`VALUE_BEARING_RULES` — the first rule carries its own value and
      addresses nobody, so the rules after it are generic too;
    * **a name in** :data:`NOINDEX_DIRECTIVES` — a rule we model as taking no value was handed
      one. It is malformed whichever way it is read, and it must not quietly become either a
      crawler of that name or a directive we honour, so it establishes nothing;
    * **any other name** — it addresses a crawler, and the whole rule list on this physical
      value is scoped to it. Nothing generic is declared here, which is a decided ``ABSENT``
      and never an inference about how that crawler behaves.

    The vocabulary is bounded on purpose, and the boundary is a real limit: a colon-valued rule
    this version does not know would be read as a crawler name. Teaching the parser a new rule
    is version work, not something it may guess at run time.
    """
    directives = _directives(field_value)
    if not directives:
        # A field value with no directive in it declares nothing. That is an absence of a
        # directive, and deliberately not a failure to read one.
        return GenericNoindex.ABSENT

    name, colon, _ = directives[0].partition(":")
    if not colon:
        # No crawler name is possible here, so every rule on this value is generic.
        return GenericNoindex.PRESENT if _states_noindex(directives) else GenericNoindex.ABSENT

    scope = name.strip().lower()
    if not scope:
        # A colon with nothing before it names no crawler and is no rule either.
        return GenericNoindex.INDETERMINATE
    if scope in NOINDEX_DIRECTIVES:
        # `noindex: yes`. Malformed under both readings, so neither may be reported.
        return GenericNoindex.INDETERMINATE
    if scope in VALUE_BEARING_RULES:
        # `max-snippet: 20, noindex`. The first rule consumed the colon for its own value, so
        # it is itself generic and so is everything after it — but its *value* is not a rule,
        # which is why only the rules after it are examined.
        return GenericNoindex.PRESENT if _states_noindex(directives[1:]) else GenericNoindex.ABSENT
    # `googlebot: follow, noindex`. Addressed to one named crawler, and therefore outside the
    # generic verdict rather than establishing or withholding it.
    return GenericNoindex.ABSENT


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
