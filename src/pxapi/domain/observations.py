"""What this slice observes about a homepage, and when an observed value is representable.

Two decisions live here, and both are business decisions rather than transport details.

**Which metrics exist.** The identifiers below are the analysis vocabulary. The contracts hold
``metric_id`` open on purpose — they fix the token's lexical shape and never the set — so this
module names the set for this slice without any contract changing.

**When a value may be stated.** An observed text is only representable if it survives
normalisation to a single line *and* fits the contract's bound. When it does not, the honest
result is that the measurement ran and established nothing — never a silently truncated value
presented as though it were the whole thing. This module makes that a decision with a name,
so a collector cannot make it accidentally.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Metric(StrEnum):
    """The metrics this slice measures. Values are ``code`` tokens: upper snake case."""

    #: The HTTP status of the final response. An integer, never a verdict about the site.
    HTTP_STATUS = "HTTP_STATUS"
    #: The URL the fetch ended at, after every followed redirect.
    FINAL_URL = "FINAL_URL"
    #: The declared media type of the final response.
    CONTENT_TYPE = "CONTENT_TYPE"
    #: Whether the final response was delivered over TLS.
    TRANSPORT_IS_HTTPS = "TRANSPORT_IS_HTTPS"
    #: How many redirects were followed to reach the final response.
    REDIRECT_COUNT = "REDIRECT_COUNT"
    #: Whether the document carries a non-empty title, and what it says.
    PAGE_TITLE_PRESENT = "PAGE_TITLE_PRESENT"
    PAGE_TITLE = "PAGE_TITLE"
    #: Whether the document declares a non-empty meta description, and what it says.
    META_DESCRIPTION_PRESENT = "META_DESCRIPTION_PRESENT"
    META_DESCRIPTION = "META_DESCRIPTION"
    #: Whether the document declares a canonical link, and where it points.
    CANONICAL_PRESENT = "CANONICAL_PRESENT"
    CANONICAL_URL = "CANONICAL_URL"


class Stage(StrEnum):
    """The stages one homepage analysis executes. ``stage_id`` is an open token too."""

    #: Retrieving the page over the network, redirects included.
    PAGE_FETCH = "PAGE_FETCH"
    #: Reading deterministic facts out of the retrieved document.
    HTML_OBSERVATION = "HTML_OBSERVATION"


#: The context every observation in this slice is made in.
SCENARIO_HOMEPAGE_FETCH: Final = "HOMEPAGE_FETCH"

#: Who made the observation, and by which method. Two records are comparable only when both
#: agree, so the version travels with every record rather than being assumed.
COLLECTOR: Final = "HOMEPAGE_BASELINE_COLLECTOR"
COLLECTOR_VERSION: Final = "1.0.0"

#: Code points that may not appear in a contract ``single_line_text`` at all: every C0 control
#: (tab, CR and LF included) and the space, DEL, every C1 control, and the Unicode LINE and
#: PARAGRAPH separators. They are folded to a space rather than deleted, so two words separated
#: only by a newline do not silently become one word.
_FOLD_TO_SPACE: Final[frozenset[int]] = frozenset(
    set(range(0x00, 0x21)) | {0x7F} | set(range(0x80, 0xA0)) | {0x2028, 0x2029}
)


def normalise_single_line(raw: str) -> str:
    """Fold an observed text to the single-line shape the contracts accept.

    Deterministic and total: the same input always yields the same output, and the output has
    no leading or trailing blank and no interior run of blanks. An input that carries nothing
    but separators normalises to the empty string, which callers read as "no text observed".
    """
    folded = "".join(" " if ord(char) in _FOLD_TO_SPACE else char for char in raw)
    # `split()` with no argument collapses runs; `split(" ")` would keep the empty strings
    # between consecutive spaces and rebuild the run verbatim.
    return " ".join(folded.split())


def representable_text(raw: str, max_length: int) -> str | None:
    """The normalised text if the contract can carry it, otherwise ``None``.

    ``None`` is the whole point of this function. A text that normalises to nothing was not
    observed, and a text longer than the contract's bound cannot be stated in this version of
    the contract. Neither may be rendered as a shortened value that reads like the original:
    a caller that gets ``None`` records an assessment that established nothing, which is true,
    instead of a value that is false.
    """
    normalised = normalise_single_line(raw)
    if not normalised or len(normalised) > max_length:
        return None
    return normalised
