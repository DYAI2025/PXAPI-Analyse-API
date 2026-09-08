"""Reading title, meta description, canonical and generic robots declarations out of HTML.

Absence and presence are both facts here, and the tests keep them apart from the third case
that matters: a document the reader could not process at all, which is a statement about our
runtime and never about the site.
"""

from __future__ import annotations

import pytest

from pxapi.adapters.web.html_observations import (
    HtmlObservations,
    decode_body,
    read_html,
)


def test_a_complete_document_yields_all_three_facts() -> None:
    html = b"""<!doctype html><html><head>
      <title>Example Domain</title>
      <meta name="description" content="An example page.">
      <link rel="canonical" href="https://example.com/">
    </head><body>hi</body></html>"""
    assert read_html(html) == HtmlObservations(
        title="Example Domain",
        meta_description="An example page.",
        canonical_href="https://example.com/",
        robots_meta_contents=(),
    )


def test_an_empty_document_yields_only_absences() -> None:
    observed = read_html(b"")
    assert observed == HtmlObservations(None, None, None, ())


# --- title ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (b"<title>Plain</title>", "Plain"),
        (b"<TITLE>Upper</TITLE>", "Upper"),
        (b"<title>  spaced  </title>", "  spaced  "),
        (b"<title>Line\nbreak</title>", "Line\nbreak"),
        (b"<title>&amp; entity</title>", "& entity"),
        (b"<title></title>", ""),
        (b"<title>First</title><title>Second</title>", "First"),
        (b"<html><head><title>Unclosed", "Unclosed"),
    ],
)
def test_the_title_is_returned_verbatim(html: bytes, expected: str) -> None:
    """Verbatim: normalisation is the domain's decision, not the reader's."""
    assert read_html(html).title == expected


def test_a_document_without_a_title_reports_none() -> None:
    assert read_html(b"<html><head></head><body>no title</body></html>").title is None


# --- meta description ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (b'<meta name="description" content="A">', "A"),
        (b'<meta NAME="Description" CONTENT="B">', "B"),
        (b"<meta name='description' content='C'>", "C"),
        (b'<meta name=" description " content="D">', "D"),
        (b'<meta name="description" content="">', ""),
        (b'<meta name="description" content="one"><meta name="description" content="two">', "one"),
    ],
)
def test_the_meta_description_is_read_case_insensitively(html: bytes, expected: str) -> None:
    assert read_html(html).meta_description == expected


@pytest.mark.parametrize(
    "html",
    [
        b"<html><head></head></html>",
        b'<meta name="keywords" content="not a description">',
        b'<meta http-equiv="description" content="not the same declaration">',
        b'<meta property="og:description" content="a different vocabulary">',
    ],
)
def test_a_document_without_a_meta_description_reports_none(html: bytes) -> None:
    assert read_html(html).meta_description is None


# --- generic robots meta ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (b'<meta name="robots" content="noindex">', ("noindex",)),
        (b'<meta NAME="Robots" CONTENT="NOINDEX">', ("NOINDEX",)),
        (b"<meta name='robots' content='none'>", ("none",)),
        (b'<meta name=" robots " content="noindex, nofollow">', ("noindex, nofollow",)),
        (b'<meta name="robots" content="">', ("",)),
        (b"<meta name=robots content=noindex>", ("noindex",)),
        # Every declaration, not only the first: any one of them can be the one that counts.
        (
            b'<meta name="robots" content="index"><meta name="robots" content="noindex">',
            ("index", "noindex"),
        ),
    ],
)
def test_every_generic_robots_declaration_is_collected_verbatim(
    html: bytes, expected: tuple[str, ...]
) -> None:
    """Verbatim, and in document order: what the tokens *mean* is the domain's decision."""
    assert read_html(html).robots_meta_contents == expected


@pytest.mark.parametrize(
    "html",
    [
        b"<html><head></head></html>",
        b'<meta name="description" content="not a robots declaration">',
        # Crawler-specific declarations are a different vocabulary. This slice states nothing
        # about how a named crawler behaves, so it does not collect them at all.
        b'<meta name="googlebot" content="noindex">',
        b'<meta name="bingbot" content="noindex">',
        b'<meta name="robotsx" content="noindex">',
        b'<meta http-equiv="robots" content="noindex">',
        b'<meta property="robots" content="noindex">',
    ],
)
def test_a_document_with_no_generic_robots_declaration_collects_nothing(html: bytes) -> None:
    assert read_html(html).robots_meta_contents == ()


def test_a_robots_declaration_does_not_displace_the_meta_description() -> None:
    """The two declarations are independent; collecting one must not consume the other."""
    html = b'<meta name="robots" content="noindex"><meta name="description" content="Still read.">'
    observed = read_html(html)
    assert observed.robots_meta_contents == ("noindex",)
    assert observed.meta_description == "Still read."


def test_a_meta_description_does_not_displace_a_later_robots_declaration() -> None:
    html = b'<meta name="description" content="First."><meta name="robots" content="noindex">'
    observed = read_html(html)
    assert observed.meta_description == "First."
    assert observed.robots_meta_contents == ("noindex",)


# --- canonical --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (b'<link rel="canonical" href="https://a.example/">', "https://a.example/"),
        (b'<link REL="Canonical" HREF="https://b.example/">', "https://b.example/"),
        (b'<link rel="canonical alternate" href="https://c.example/">', "https://c.example/"),
        (b'<link rel="alternate canonical" href="https://d.example/">', "https://d.example/"),
        (b'<link rel="canonical" href="/relative">', "/relative"),
        (b'<link rel="canonical" href="">', ""),
    ],
)
def test_the_canonical_href_is_read_from_the_rel_token_list(html: bytes, expected: str) -> None:
    assert read_html(html).canonical_href == expected


@pytest.mark.parametrize(
    "html",
    [
        b"<html><head></head></html>",
        b'<link rel="stylesheet" href="/style.css">',
        b'<link rel="canonicalish" href="/no">',
        b'<a rel="canonical" href="/not-a-link-element">x</a>',
    ],
)
def test_a_document_without_a_canonical_link_reports_none(html: bytes) -> None:
    assert read_html(html).canonical_href is None


# --- malformed input is input, not a defect ------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        b"<html><head><title>Ok</title><body><p>unclosed<div><span>",
        b"<<>><title>Ok</title>>>",
        b"<title>Ok</title><meta name=description content=unquoted>",
        b"<!-- <title>commented</title> --><title>Ok</title>",
        b"<html\x00><title>Ok</title>",
        b"\xff\xfe<title>Ok</title>",
    ],
)
def test_malformed_markup_is_read_without_raising(html: bytes) -> None:
    """A messy page is still a page; the reader must not turn its own difficulty into news."""
    assert read_html(html).title is not None


def test_reading_is_deterministic_for_identical_input() -> None:
    html = b'<title>T</title><meta name="description" content="D">'
    assert read_html(html) == read_html(html)


# --- decoding -------------------------------------------------------------------------------------


def test_a_declared_charset_is_honoured() -> None:
    body = "<title>Grüße</title>".encode("iso-8859-1")
    assert read_html(body, "iso-8859-1").title == "Grüße"


def test_an_unknown_declared_charset_falls_back_rather_than_failing() -> None:
    body = b"<title>Fine</title>"
    assert read_html(body, "not-a-real-charset").title == "Fine"


def test_undecodable_bytes_are_replaced_not_raised() -> None:
    assert decode_body(b"\xff\xfe\xfd", "utf-8") is not None


def test_decoding_prefers_the_declared_charset_over_the_default() -> None:
    body = "ä".encode("iso-8859-1")
    assert decode_body(body, "iso-8859-1") == "ä"
    assert decode_body(body, "utf-8") != "ä"
