"""The boundary vocabulary for reading facts out of a retrieved document.

The shapes live here rather than in the adapter because the application depends on them and
must not depend on any particular parser. Swapping the reader is then a change of adapter, not
a change of what an observation *is*.

``HtmlUnreadable`` is the boundary's way of saying our own runtime failed. It exists so that
"we could not read this document" can never be confused with "this document declares nothing":
one is a fact about the analysis process, the other a fact about the website.

Standard library only. Ports import no third-party distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class HtmlUnreadable(Exception):
    """The document could not be processed. A statement about our run, never about the site."""


@dataclass(frozen=True)
class HtmlObservations:
    """What a document declared, verbatim.

    ``None`` means the element was not found. An empty string means it was found and is empty,
    which is a different fact and is deliberately distinguishable from absence.
    """

    title: str | None
    meta_description: str | None
    canonical_href: str | None


class HtmlReader(Protocol):
    def __call__(self, body: bytes, declared_charset: str | None = None) -> HtmlObservations:
        """The declared title, meta description and canonical link of ``body``."""
        ...
