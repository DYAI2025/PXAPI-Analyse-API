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
