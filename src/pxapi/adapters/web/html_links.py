"""Reads the link targets, and the text each link carries, out of one static HTML document.

It is the link half of site discovery and nothing more: it resolves every ``<a href>`` and
``<area href>`` against the document's base, and it returns each target with the bounded text
a visitor would read on it. Deciding which targets are same-origin, which may be persisted and
what a page *is* belongs to the Domain; this module never filters on meaning.

Two rules keep it honest.

**A label is bounded before it leaves this module, and never truncated.** The text inside a
link is website content. It is normalised to one line with the Domain's own rule and handed on
only if it fits the classifier's bound; a longer one is dropped. A truncated label would be text
the site never wrote, and a classification resting on it would not be reproducible.

**Our difficulty is never the site's.** A document the parser genuinely cannot process raises
``HtmlUnreadable``, and the caller records that *our* runtime failed. Unclosed tags, stray markup
and links nested in ways the standard forbids are ordinary input and are read tolerantly.

Standard library only for parsing; this adapter imports no third-party distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from pxapi.adapters.web.html_observations import decode_body
from pxapi.domain.observations import representable_text
from pxapi.ports.html_observation import HtmlUnreadable

__all__ = ["DocumentLink", "HtmlUnreadable", "read_links"]

#: How many characters of raw link text are collected before a label is known to be too long.
#: Normalisation can only shorten text, so four times the bound is enough to decide that the
#: normalised label would exceed it, while keeping the collection itself bounded no matter how
#: much text one link wraps.
_COLLECTION_FACTOR = 4


@dataclass(frozen=True)
class DocumentLink:
    """One resolved link target, in document order, with its bounded label if it has one."""

    href: str
    label: str | None


class _LinkReader(HTMLParser):
    """Collects every link target and its text, and the document's first ``<base href>``."""

    def __init__(self, collect_limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.base_href: str | None = None
        self.raw_links: list[tuple[str, str, bool]] = []
        self._collect_limit = collect_limit
        self._open_href: str | None = None
        self._open_text: list[str] = []
        self._open_length = 0
        self._open_overflow = False
        self._open_fallback = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        if tag == "base" and self.base_href is None and "href" in attributes:
            self.base_href = attributes["href"]
        elif tag == "a":
            # An <a> opened inside another closes the first: nesting anchors is not valid HTML,
            # and every browser ends the outer link at that point.
            self._close_open()
            if "href" in attributes:
                self._open_href = attributes["href"]
                self._open_fallback = attributes.get("aria-label") or attributes.get("title", "")
        elif tag == "area" and "href" in attributes:
            self.raw_links.append((attributes["href"], attributes.get("alt", ""), False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag == "a":
            self._close_open()

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._close_open()

    def handle_data(self, data: str) -> None:
        if self._open_href is None or self._open_overflow:
            return
        self._open_length += len(data)
        if self._open_length > self._collect_limit:
            self._open_overflow = True
            self._open_text = []
            return
        self._open_text.append(data)

    def close(self) -> None:
        super().close()
        self._close_open()

    def _close_open(self) -> None:
        if self._open_href is None:
            return
        text = "".join(self._open_text)
        if not text.strip() and not self._open_overflow:
            text = self._open_fallback
        self.raw_links.append((self._open_href, text, self._open_overflow))
        self._open_href = None
        self._open_text = []
        self._open_length = 0
        self._open_overflow = False
        self._open_fallback = ""


def _base_for(document_url: str, base_href: str | None) -> str:
    """The URL every relative link resolves against.

    A ``<base href>`` wins when it resolves to an absolute http(s) URL, as it does in every
    browser; any other value is ignored and the document's own URL is used. Where the base
    points is not decided here: a base outside the origin simply yields targets outside it,
    which the Domain then records as ``OFF_ORIGIN`` rather than following.
    """
    if base_href is not None:
        resolved = urljoin(document_url, base_href.strip())
        if urlsplit(resolved).scheme in ("http", "https") and urlsplit(resolved).netloc:
            return resolved
    return document_url


def read_links(
    body: bytes, document_url: str, declared_charset: str | None, max_label_length: int
) -> tuple[DocumentLink, ...]:
    """Every link target of ``body``, resolved, in document order.

    Raises ``HtmlUnreadable`` if the document could not be processed at all.
    """
    try:
        reader = _LinkReader(collect_limit=max_label_length * _COLLECTION_FACTOR)
        reader.feed(decode_body(body, declared_charset))
        reader.close()
    except Exception as error:  # any parser failure is one category to us
        raise HtmlUnreadable("the document could not be processed") from error

    base = _base_for(document_url, reader.base_href)
    links: list[DocumentLink] = []
    for href, text, overflowed in reader.raw_links:
        target = href.strip()
        if not target:
            continue
        label = None if overflowed else representable_text(text, max_label_length)
        links.append(DocumentLink(href=urljoin(base, target), label=label))
    return tuple(links)
