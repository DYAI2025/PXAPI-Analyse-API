"""The link reader: resolution, the bounded label, and our failure never becoming the site's."""

from __future__ import annotations

import pytest

from pxapi.adapters.web import html_links
from pxapi.adapters.web.html_links import DocumentLink, read_links
from pxapi.ports.html_observation import HtmlUnreadable

PAGE = "https://example.com/a/seite"


def links(markup: str, max_label: int = 120) -> tuple[DocumentLink, ...]:
    return read_links(markup.encode(), PAGE, "utf-8", max_label)


def test_a_relative_link_resolves_against_the_document() -> None:
    assert links('<a href="kontakt">K</a><a href="/impressum">I</a>') == (
        DocumentLink("https://example.com/a/kontakt", "K"),
        DocumentLink("https://example.com/impressum", "I"),
    )


def test_a_base_href_wins_and_a_non_web_base_is_ignored() -> None:
    assert links('<base href="https://example.com/x/"><a href="y">Y</a>')[0].href == (
        "https://example.com/x/y"
    )
    assert links('<base href="javascript:alert(1)"><a href="y">Y</a>')[0].href == (
        "https://example.com/a/y"
    )


def test_a_label_is_folded_to_one_line_with_the_domain_rule() -> None:
    assert (
        links('<a href="/k">  Kontakt\n\t <b>aufnehmen</b>  </a>')[0].label == "Kontakt aufnehmen"
    )


def test_a_label_over_the_bound_is_dropped_never_truncated() -> None:
    (link,) = links(f'<a href="/k">{"Kontakt " * 40}</a>', max_label=120)
    assert link.label is None and link.href == "https://example.com/k"


def test_a_link_without_text_falls_back_to_its_accessible_name() -> None:
    assert links('<a href="/k" aria-label="Kontakt"><img src="x.png"></a>')[0].label == "Kontakt"


def test_an_image_map_area_is_a_link_labelled_by_its_alternative_text() -> None:
    assert links('<map><area href="/impressum" alt="Impressum"></map>')[0] == (
        DocumentLink("https://example.com/impressum", "Impressum")
    )


def test_a_nested_anchor_closes_the_outer_one_as_a_browser_would() -> None:
    assert [link.href for link in links('<a href="/a">A<a href="/b">B</a>')] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_an_anchor_the_document_never_closed_is_still_read() -> None:
    assert links('<a href="/offen">Offen')[0].label == "Offen"


def test_an_empty_or_missing_href_is_not_a_link() -> None:
    assert links('<a href="">x</a><a name="top">y</a><a href="   ">z</a>') == ()


def test_links_come_back_in_document_order() -> None:
    order = [link.href.rsplit("/", 1)[1] for link in links('<a href="/c">c</a><a href="/a">a</a>')]
    assert order == ["c", "a"]


def test_a_document_we_cannot_process_is_our_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(body: bytes, charset: str | None) -> str:
        raise RuntimeError("decoder broke")

    monkeypatch.setattr(html_links, "decode_body", broken)
    with pytest.raises(HtmlUnreadable):
        links('<a href="/k">K</a>')


# --- C-PXAPI-013: one malformed value never discards its valid siblings ----------------------

#: Values that make ``urlsplit``/``urljoin`` raise rather than return a URL. Fuzzing the two
#: functions over ~900k inputs produced ``ValueError`` and nothing else, which is why the
#: isolation below catches that type and not a bare ``Exception``: a wider guard would swallow
#: a defect of ours that has nothing to do with a link.
UNRESOLVABLE = (
    "http://[::1",
    "https://[not-an-address]/x",
    "https://exa[mple.com/x",
    "http://[",
)


@pytest.mark.parametrize("bad", UNRESOLVABLE)
def test_a_malformed_href_never_discards_its_valid_siblings(bad: str) -> None:
    """One link the URL parser cannot resolve is one link, not the whole document.

    Before the repair the ``urljoin`` that resolves each target sat outside ``read_links``'
    failure isolation, so a single such value propagated a ``ValueError`` out of the reader and
    the caller lost every other link on the page with it.
    """
    resolved = [
        link.href for link in links(f'<a href="/a">A</a><a href="{bad}">B</a><a href="/c">C</a>')
    ]
    assert resolved == ["https://example.com/a", "https://example.com/c"]


@pytest.mark.parametrize("bad", UNRESOLVABLE)
def test_an_unusable_base_href_falls_back_to_the_document_it_cannot_replace(bad: str) -> None:
    """A base the parser cannot read is ignored exactly like a non-web base already was."""
    resolved = [
        link.href for link in links(f'<base href="{bad}"><a href="/a">A</a><a href="/c">C</a>')
    ]
    assert resolved == ["https://example.com/a", "https://example.com/c"]


@pytest.mark.parametrize("bad", UNRESOLVABLE)
def test_an_unusable_document_url_loses_its_links_and_not_our_runtime(bad: str) -> None:
    """Defence in depth: the product establishes its origin from this URL before reading links,
    so an unresolvable one cannot reach here — and if it did, it would be an empty read rather
    than an exception escaping the reader."""
    assert read_links(b'<a href="/a">A</a>', bad, "utf-8", 120) == ()


def test_a_malformed_href_is_dropped_rather_than_admitted_unresolved() -> None:
    """No unsafe target is admitted merely to preserve its siblings: it is simply not a link."""
    assert [link.href for link in links('<a href="http://[::1">B</a>')] == []


def test_isolating_a_malformed_link_leaves_its_label_bounding_untouched() -> None:
    (a, c) = links(
        f'<a href="/a">  Kontakt\n aufnehmen </a><a href="http://[">x</a>'
        f'<a href="/c">{"Kontakt " * 40}</a>'
    )
    assert a.label == "Kontakt aufnehmen"
    assert c.label is None


def test_a_document_wide_decode_failure_is_still_our_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The isolation above narrows nothing: a document that cannot be processed at all is
    still ``HtmlUnreadable``, which the caller records as our RUNTIME_ERROR."""

    def broken(body: bytes, charset: str | None) -> str:
        raise ValueError("decoder broke")

    monkeypatch.setattr(html_links, "decode_body", broken)
    with pytest.raises(HtmlUnreadable):
        links('<a href="/k">K</a>')


def test_the_link_guard_is_narrow_and_does_not_swallow_a_defect_of_ours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The per-link guard catches ``ValueError`` and deliberately nothing wider.

    ``urljoin`` and ``urlsplit`` raise ``ValueError`` and nothing else — fuzzed over ~900k
    inputs — so that type is the whole of "this href is not a URL". Any other exception from
    this line is a defect of *ours*, and must keep travelling until ``_guarded`` records it as
    RUNTIME_ERROR. Swallowed as a dropped link instead, it would read as a website that simply
    linked nowhere. Widening the guard to ``except Exception`` turns this test red.
    """

    def exploding(base: str, target: str) -> str:
        raise RuntimeError("a defect that is not a URL problem")

    monkeypatch.setattr(html_links, "urljoin", exploding)
    with pytest.raises(RuntimeError):
        links('<a href="/k">K</a>')
