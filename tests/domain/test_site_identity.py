"""Canonical identity: every rule of ``URL_CANONICAL_BASELINE 1.0.0``, and every refusal.

The rules are tested as input/output pairs rather than as descriptions, and each key is also
handed to the *real* contract validator for ``acquisition#/$defs/public_url`` — so a key this
module produces is proved to be a key the contract accepts, not merely one that looks right.
"""

from __future__ import annotations

import pytest

from pxapi.domain import site_identity as si
from pxapi.domain.site_identity import UrlRefusal
from tests.contracts.support import CONTRACTS, load_json

ACQUISITION = load_json(CONTRACTS.schema_path("acquisition"))["$defs"]
PUBLIC_URL = CONTRACTS.validator_for_definition("public_url", shared="acquisition")
PUBLIC_ORIGIN = CONTRACTS.validator_for_definition("public_origin", shared="acquisition")

#: ``written form -> canonical key``, one entry per rule and per edge that rule has.
CANONICAL: list[tuple[str, str]] = [
    ("https://example.com", "https://example.com/"),
    ("HTTPS://EXAMPLE.COM/Path", "https://example.com/Path"),
    ("https://example.com:443/x", "https://example.com/x"),
    ("http://example.com:80/x", "http://example.com/x"),
    ("https://example.com:8443/x", "https://example.com:8443/x"),
    ("https://example.com/x#frag", "https://example.com/x"),
    ("https://example.com/a/b/../c/./d", "https://example.com/a/c/d"),
    ("https://example.com/../../x", "https://example.com/x"),
    ("https://example.com/%7euser", "https://example.com/~user"),
    ("https://example.com/%c3%a4", "https://example.com/%C3%A4"),
    ("https://example.com/ä", "https://example.com/%C3%A4"),
    ("https://example.com/a/%2E%2E/b", "https://example.com/b"),
    ("https://example.com/a\\b", "https://example.com/a/b"),
    ("https://example.com/a%5Cb", "https://example.com/a%5Cb"),
    ("https://example.com/a|b", "https://example.com/a%7Cb"),
    ("https://example.com/%2F", "https://example.com/%2F"),
    ("https://example.com/x?utm_source=a&utm_medium=b", "https://example.com/x"),
    ("https://example.com/x?UTM_SOURCE=a", "https://example.com/x"),
    ("https://example.com/x?b=2&gclid=z&a=1", "https://example.com/x?b=2&a=1"),
    ("https://example.com/x?ref=1", "https://example.com/x?ref=1"),
    ("https://example.com/x?q=a\\b", "https://example.com/x?q=a\\b"),
    ("https://example.com/x/", "https://example.com/x/"),
    ("https://[2001:db8::1]:8443/x", "https://[2001:db8::1]:8443/x"),
]

#: ``written form -> the named reason it has no identity``.
REFUSED: list[tuple[str, UrlRefusal]] = [
    ("https://user:secret@example.com/", UrlRefusal.CREDENTIALS_PRESENT),
    ("https://user@example.com/", UrlRefusal.CREDENTIALS_PRESENT),
    ("https://@example.com/", UrlRefusal.CREDENTIALS_PRESENT),
    ("https://example.com\\leistungen", UrlRefusal.UNUSABLE_AUTHORITY),
    ("https://example.com:notaport/", UrlRefusal.UNUSABLE_AUTHORITY),
    ("https://example.com:99999/", UrlRefusal.UNUSABLE_AUTHORITY),
    ("https:///path", UrlRefusal.UNUSABLE_AUTHORITY),
    ("ftp://example.com/", UrlRefusal.NOT_ABSOLUTE_HTTP),
    ("javascript:alert(1)", UrlRefusal.NOT_ABSOLUTE_HTTP),
    ("mailto:someone@example.com", UrlRefusal.NOT_ABSOLUTE_HTTP),
    ("/relative/path", UrlRefusal.NOT_ABSOLUTE_HTTP),
    ("https://example.com/a b", UrlRefusal.FORBIDDEN_CHARACTER),
    ("https://example.com/\nx", UrlRefusal.FORBIDDEN_CHARACTER),
    ("https://example.com/\u2028", UrlRefusal.FORBIDDEN_CHARACTER),
    ("https://example.com/\x85", UrlRefusal.FORBIDDEN_CHARACTER),
    ("https://example.com/%zz", UrlRefusal.MALFORMED),
    ("https://[::1/", UrlRefusal.MALFORMED),
]


def _ids(pairs: list[tuple[str, object]]) -> list[str]:
    return [repr(form)[:60] for form, _ in pairs]


# --- the contract binding -------------------------------------------------------------------


def test_the_lexical_shapes_are_the_contract_shapes_verbatim() -> None:
    """Restated in the Domain, pinned here: the two cannot drift apart without a red test."""
    assert ACQUISITION["public_url"]["pattern"] == si.PUBLIC_URL_PATTERN
    assert ACQUISITION["public_origin"]["pattern"] == si.PUBLIC_ORIGIN_PATTERN
    assert ACQUISITION["public_url"]["maxLength"] == si.MAX_URL_LENGTH
    assert ACQUISITION["public_origin"]["maxLength"] == si.MAX_ORIGIN_LENGTH


# --- the rules --------------------------------------------------------------------------------


@pytest.mark.parametrize(("form", "key"), CANONICAL, ids=_ids(CANONICAL))
def test_a_written_form_reduces_to_its_canonical_key(form: str, key: str) -> None:
    assert si.canonical_url_key(form) == key
    assert si.refuse(form) is None


@pytest.mark.parametrize(("form", "key"), CANONICAL, ids=_ids(CANONICAL))
def test_a_canonical_key_is_its_own_key(form: str, key: str) -> None:
    """Idempotence: canonicalising a key again changes nothing, or keys would drift per run."""
    assert si.canonical_url_key(key) == key


@pytest.mark.parametrize(("form", "key"), CANONICAL, ids=_ids(CANONICAL))
def test_every_canonical_key_satisfies_the_contract_validator(form: str, key: str) -> None:
    assert list(PUBLIC_URL.iter_errors(key)) == []


def test_an_encoded_dot_segment_cannot_survive_as_a_traversal() -> None:
    """RFC 3986 6.2.2 order: escapes are decoded before dot segments are removed."""
    assert si.canonical_url_key("https://example.com/a/%2e%2e/%2e/secret") == (
        "https://example.com/secret"
    )


def test_an_existing_escape_is_never_encoded_a_second_time() -> None:
    assert "%25" not in (si.canonical_url_key("https://example.com/%c3%a4?q=%c3%a4") or "")


def test_query_parameters_that_remain_keep_the_order_they_were_written_in() -> None:
    """Declining to merge only adds a candidate; merging wrongly would lose a page."""
    assert si.canonical_url_key("https://example.com/x?b=2&a=1") != si.canonical_url_key(
        "https://example.com/x?a=1&b=2"
    )


# --- the refusals -----------------------------------------------------------------------------


@pytest.mark.parametrize(("form", "reason"), REFUSED, ids=_ids(REFUSED))
def test_a_form_without_an_identity_is_refused_with_its_reason(
    form: str, reason: UrlRefusal
) -> None:
    assert si.refuse(form) is reason
    assert si.canonical_url_key(form) is None
    assert si.canonical_origin(form) is None


def test_a_credential_bearing_form_is_never_persistable() -> None:
    """D-PXAPI19-PO-007: refused before persistence, never stripped into something that passes."""
    for form in ("https://user:secret@example.com/", "https://@example.com/"):
        assert si.is_persistable_form(form) is False
        assert si.canonical_url_key(form) is None


def test_a_form_the_contract_refuses_is_not_persistable_even_when_it_has_a_key() -> None:
    """``observed_forms`` is recorded verbatim, so the verbatim form must pass the contract."""
    assert si.canonical_url_key("HTTPS://example.com/") == "https://example.com/"
    assert si.is_persistable_form("HTTPS://example.com/") is False
    assert list(PUBLIC_URL.iter_errors("HTTPS://example.com/")) != []


def test_a_key_longer_than_the_contract_allows_is_refused_rather_than_truncated() -> None:
    assert si.canonical_url_key("https://example.com/" + "a" * 2100) is None
    assert si.canonical_url_key("https://" + "a" * 254 + "/") is None


# --- origins ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("form", "origin"),
    [
        ("https://Example.com/leistungen?x=1#y", "https://example.com/"),
        ("https://example.com:8443/x", "https://example.com:8443/"),
        ("http://example.com:80/", "http://example.com/"),
        ("https://[2001:db8::1]/x", "https://[2001:db8::1]/"),
    ],
)
def test_an_origin_is_a_scheme_an_authority_and_the_root_and_nothing_else(
    form: str, origin: str
) -> None:
    assert si.canonical_origin(form) == origin
    assert list(PUBLIC_ORIGIN.iter_errors(origin)) == []


@pytest.mark.parametrize(
    ("key", "same"),
    [
        ("https://example.com/x", True),
        ("https://example.com/", True),
        ("https://www.example.com/x", False),
        ("http://example.com/x", False),
        ("https://example.com:8443/x", False),
        ("https://example.com.evil.test/x", False),
        ("https://evil.test/https://example.com/", False),
        ("not a url", False),
    ],
)
def test_same_origin_is_exact_origin_equality(key: str, same: bool) -> None:
    assert si.is_same_origin(key, "https://example.com/") is same


def test_a_key_that_is_not_canonical_belongs_to_no_origin() -> None:
    assert si.origin_of_key("https://EXAMPLE.com/x") is None
    assert si.is_same_origin("https://EXAMPLE.com/x", "https://example.com/") is False


# --- page resources ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "page"),
    [
        ("https://example.com/", True),
        ("https://example.com/leistungen", True),
        ("https://example.com/leistungen.html", True),
        ("https://example.com/x.unknownsuffix", True),
        ("https://example.com/.well-known", True),
        ("https://example.com/broschuere.pdf", False),
        ("https://example.com/BROSCHUERE.PDF", False),
        ("https://example.com/img/logo.svg", False),
        ("https://example.com/feed.xml", False),
    ],
)
def test_a_non_page_resource_is_named_by_its_suffix_and_an_unknown_suffix_is_a_page(
    key: str, page: bool
) -> None:
    """Conservative by design: an unrecognised suffix must never silently drop a page."""
    assert si.is_page_resource(key) is page
