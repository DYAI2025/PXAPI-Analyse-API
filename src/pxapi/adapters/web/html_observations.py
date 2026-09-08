"""Reads the deterministic facts this slice needs out of an HTML document.

Four facts, each of which a visitor could see for themselves: the document's title, its meta
description, its canonical link, and what its generic robots declarations say. Nothing here
judges any of them — a robots declaration comes back as the text it carried, and what that text
*means* is the domain's decision.

The reader is deliberately tolerant. Real homepages are full of unclosed tags, stray markup and
duplicated elements, and none of that is a defect in the *website* worth reporting — it is
simply the input. What the reader must never do is turn its own difficulty into a finding, so a
document it genuinely cannot process raises ``HtmlUnreadable`` and the caller records that our
runtime failed, not that the site lacks a title.

Values come back exactly as they appeared. Normalising, bounding and deciding whether a value
is representable at all belong to the domain, which owns that policy.
"""

from __future__ import annotations

import codecs
from html.parser import HTMLParser

from pxapi.ports.html_observation import HtmlObservations, HtmlUnreadable

__all__ = ["HtmlObservations", "HtmlUnreadable", "decode_body", "read_html"]


class _Reader(HTMLParser):
    """Collects the first of each element of interest, ignoring everything else."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.meta_description: str | None = None
        self.canonical_href: str | None = None
        self.robots_meta_contents: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title" and self.title is None:
            self._in_title = True
            self._title_parts = []
            return

        attributes = {name.lower(): (value or "") for name, value in attrs}

        if tag == "meta":
            # `name` is compared case-insensitively; `http-equiv` descriptions are not the
            # same declaration and are deliberately not collected.
            name = attributes.get("name", "").strip().lower()
            if name == "description" and self.meta_description is None:
                self.meta_description = attributes.get("content", "")
            elif name == "robots":
                # Every generic declaration, not only the first: a document may carry several
                # and any one of them can be the one that says noindex. A crawler-specific
                # name such as `googlebot` is a different declaration, and this reader
                # deliberately does not collect it.
                self.robots_meta_contents.append(attributes.get("content", ""))
            return

        if tag == "link" and self.canonical_href is None:
            # `rel` is a space-separated token list, so `rel="canonical alternate"` counts.
            tokens = attributes.get("rel", "").lower().split()
            if "canonical" in tokens:
                self.canonical_href = attributes.get("href", "")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            self.title = "".join(self._title_parts)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    @property
    def unclosed_title_text(self) -> str:
        """Title text collected from a <title> the document never closed."""
        return "".join(self._title_parts)


def decode_body(body: bytes, declared_charset: str | None) -> str:
    """Decode a response body, preferring the charset it declared.

    Undecodable bytes are replaced rather than raised on: a single bad byte in a footer is not
    a reason to report that we could not read the page, and replacement is deterministic.
    """
    for candidate in (declared_charset, "utf-8"):
        if not candidate:
            continue
        try:
            codecs.lookup(candidate)
        except LookupError:
            continue
        return body.decode(candidate, errors="replace")
    return body.decode("utf-8", errors="replace")


def read_html(body: bytes, declared_charset: str | None = None) -> HtmlObservations:
    """The declared title, meta description and canonical link of ``body``.

    Raises ``HtmlUnreadable`` if the document could not be processed at all.
    """
    try:
        reader = _Reader()
        reader.feed(decode_body(body, declared_charset))
        reader.close()
    except Exception as error:  # any parser failure is one category to us
        raise HtmlUnreadable("the document could not be processed") from error

    # An unclosed <title> leaves text collected but never committed; it was still observed.
    title = reader.title
    if title is None and reader.unclosed_title_text:
        title = reader.unclosed_title_text

    return HtmlObservations(
        title=title,
        meta_description=reader.meta_description,
        canonical_href=reader.canonical_href,
        robots_meta_contents=tuple(reader.robots_meta_contents),
    )
