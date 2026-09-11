"""Which methodology bucket a discovered page is counted under, and by which rules.

Sampling is Pixelkiez methodology and not provider policy (D-PXAPI-007), so the decision of
*what a page is* has to be made here, in the Domain, where no crawler can reach it. This module
is that decision and nothing else: it reads an identity and an optional bounded label, and it
returns a stable token or nothing at all.

Three properties make it safe to build a selection on.

**It is a pure function.** No clock, no network, no state. The same identity and the same label
always yield the same token, which is what lets one frozen discovery input produce one
manifest digest on every run.

**It never judges.** A bucket is the name of a counting bucket. ``LEGAL`` does not rank below
``OFFER``, an unplaced page is not a worse page, and nothing downstream may read one of these
tokens as a quality, a priority or a finding. The contract says as much at ``stratum``; this
module is the producer side of that sentence.

**It declines rather than guesses.** A page this version cannot place returns ``None``. The
inventory then carries no ``page_type`` for it — the contract's way of saying the classifier
assigned none — and the manifest counts it under the neutral ``UNCLASSIFIED`` stratum. Neither
is a statement about the page, and inventing a bucket to avoid an empty one would be.

The vocabulary is open by contract: ``site-inventory.v1`` fixes the token's lexical shape and
deliberately not the taxonomy, because a taxonomy is versioned methodology work. The set below
is therefore *this classifier's* set at *this version*, and a consumer meeting a token it does
not know treats it as an unknown type rather than as an error.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import urlsplit

#: Who assigned the page types, and by which method version. Both travel with every inventory:
#: a page type read without the version of the method that assigned it is not reproducible.
CLASSIFIER: Final = "PAGE_TYPE_BASELINE"
CLASSIFIER_VERSION: Final = "1.0.0"

#: The neutral stratum a selection carries when the classifier placed nothing. The contract
#: names this token and does not close the taxonomy around it: it means the classification did
#: not place this page, and nothing else. It is not a quality, not an exclusion, not a lower
#: rank and not a reason to weight the page differently.
UNCLASSIFIED: Final = "UNCLASSIFIED"

#: The page this analysis was pointed at. Always the canonical target seed, never inferred.
HOMEPAGE: Final = "HOMEPAGE"

#: The bounded initial semantic classes of the accepted methodology, in the fixed order they
#: are tested in. Order is part of the method and therefore part of its version: a page whose
#: path names both a legal and a knowledge token is counted once, under the first rule that
#: matched, rather than under whichever happened to be visited first.
#:
#: ``LEGAL`` is tested before everything else because its vocabulary is the most specific one a
#: site uses — an imprint is never incidentally an offer page — and a legal notice counted as
#: content would misdescribe the population. ``CONTACT`` precedes ``OFFER`` for the mirror
#: reason: a page at ``/angebot-anfordern`` is a conversion step, not a service description.
PAGE_TYPES: Final[tuple[str, ...]] = (
    "LEGAL",
    "CONTACT",
    "OFFER",
    "PROOF",
    "ABOUT",
    "KNOWLEDGE",
)

#: ``page type -> the whole words that place a page in it``. German and English alike, because
#: the sites this analysis is pointed at are German SME sites that routinely mix the two. Every
#: entry is matched as a **whole hyphen-separated word** inside a path segment or a label, never
#: as a substring: a substring rule would place ``/teamsport`` under ``ABOUT`` because it
#: contains "team", and a population mis-bucketed that way is worse than one left unplaced.
_VOCABULARY: Final[dict[str, frozenset[str]]] = {
    "LEGAL": frozenset(
        {
            "agb",
            "cookie",
            "cookies",
            "cookie-richtlinie",
            "datenschutz",
            "datenschutzerklaerung",
            "disclaimer",
            "dsgvo",
            "gdpr",
            "gtc",
            "haftungsausschluss",
            "impressum",
            "imprint",
            "legal",
            "legal-notice",
            "nutzungsbedingungen",
            "privacy",
            "privacy-policy",
            "terms",
            "terms-and-conditions",
            "terms-of-service",
            "widerruf",
            "widerrufsbelehrung",
        }
    ),
    "CONTACT": frozenset(
        {
            "anfahrt",
            "anfrage",
            "anfrage-senden",
            "angebot-anfordern",
            "appointment",
            "beratungstermin",
            "booking",
            "buchen",
            "contact",
            "contact-us",
            "enquiry",
            "get-in-touch",
            "kontakt",
            "kontaktformular",
            "kontaktieren",
            "rueckruf",
            "termin",
            "terminvereinbarung",
        }
    ),
    "OFFER": frozenset(
        {
            "angebot",
            "angebote",
            "dienstleistung",
            "dienstleistungen",
            "leistung",
            "leistungen",
            "loesungen",
            "offer",
            "offers",
            "pakete",
            "preise",
            "preisliste",
            "pricing",
            "produkt",
            "produkte",
            "product",
            "products",
            "service",
            "services",
            "solutions",
            "sortiment",
            "tarife",
        }
    ),
    "PROOF": frozenset(
        {
            "arbeiten",
            "bewertungen",
            "case-studies",
            "case-study",
            "cases",
            "erfolge",
            "erfahrungen",
            "kundenstimmen",
            "portfolio",
            "projekt",
            "projekte",
            "projects",
            "referenz",
            "referenzen",
            "references",
            "success-stories",
            "testimonials",
            "testimonial",
        }
    ),
    "ABOUT": frozenset(
        {
            "about",
            "about-us",
            "career",
            "careers",
            "company",
            "geschichte",
            "history",
            "jobs",
            "karriere",
            "leitbild",
            "philosophie",
            "stellenangebote",
            "team",
            "ueber-mich",
            "ueber-uns",
            "ueberuns",
            "unternehmen",
            "unsere-werte",
            "values",
            "wer-wir-sind",
            "who-we-are",
        }
    ),
    "KNOWLEDGE": frozenset(
        {
            "aktuelles",
            "artikel",
            "articles",
            "beitraege",
            "blog",
            "dokumentation",
            "docs",
            "faq",
            "faqs",
            "glossar",
            "glossary",
            "guide",
            "guides",
            "haeufige-fragen",
            "help",
            "hilfe",
            "knowledge",
            "knowledge-base",
            "magazin",
            "news",
            "ratgeber",
            "support",
            "tipps",
            "wiki",
            "wissen",
        }
    ),
}

#: The bound a label must already be inside when it reaches this module. It is asserted rather
#: than applied: bounding the raw text of a website is the reading adapter's job, and a
#: classifier that silently truncated would make its own input unreproducible.
MAX_LABEL_LENGTH: Final = 120

#: Everything that is not a letter, a digit or a hyphen separates words. Applied after the
#: value is lower-cased, so one spelling of a segment is one spelling here.
_SEPARATORS: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9-]+")

#: A percent escape, after lower-casing. It is replaced by a separator before words are read:
#: an escape followed by letters is not a word, and an escape is not two letters that happen to
#: be hexadecimal digits.
_ESCAPE: Final[re.Pattern[str]] = re.compile(r"%[0-9a-f]{2}")

#: A trailing file extension on a path segment. ``/leistungen.html`` is the offer page, and the
#: suffix a template chose says nothing about the page, so it is removed before matching.
_EXTENSION: Final[re.Pattern[str]] = re.compile(r"\.[a-z0-9]{1,8}$")


def _words(value: str) -> frozenset[str]:
    """Every whole word in ``value``, including the hyphenated compound as written.

    ``ueber-uns`` yields ``{"ueber-uns", "ueber", "uns"}``: the compound is what a vocabulary
    entry such as ``ueber-uns`` matches, and the parts are what makes ``/ueber_uns`` and
    ``/ueber-uns`` the same page to this classifier. Matching stays whole-word throughout —
    no entry can be found inside a longer word.
    """
    # An underscore joins words exactly as a hyphen does in a path, so it is folded to one
    # before splitting: without this, `/ueber_uns` would never meet the entry `ueber-uns`.
    lowered = _ESCAPE.sub(" ", _EXTENSION.sub("", value.lower())).replace("_", "-")
    found: set[str] = set()
    for chunk in _SEPARATORS.split(lowered):
        if not chunk:
            continue
        found.add(chunk)
        found.update(part for part in chunk.split("-") if part)
    return frozenset(found)


def _first_match(words: frozenset[str]) -> str | None:
    """The first page type whose vocabulary ``words`` meets, in the declared order."""
    for page_type in PAGE_TYPES:
        if words & _VOCABULARY[page_type]:
            return page_type
    return None


def classify(url_key: str, target_origin: str, labels: tuple[str, ...] = ()) -> str | None:
    """The page type of one candidate, or ``None`` when this version places none.

    The path is the primary signal, the query is read only when the path places nothing, and
    the labels only when neither does. That order is deliberate and part of the method: a path
    is chosen by whoever built the site and is stable across runs, whereas the text of a link
    is editorial, can differ between the two menus that point at one page, and would
    otherwise let a wording change move a page from one bucket to another between two runs
    of the same analysis.

    Labels are read in the canonical order the caller already sorted them into, and the first
    one that places the page wins, so the sequence in which links were encountered cannot
    change the result either.
    """
    if url_key == target_origin:
        # The seed is the homepage by construction, not by inference: it is the page this run
        # was pointed at, and nothing about its path is consulted.
        return HOMEPAGE

    parts = urlsplit(url_key)
    for component in (parts.path, parts.query):
        # The path first, then the query, each on its own: a referral parameter such as
        # `?ref=impressum` must not move an offer page into another class.
        placed = _first_match(_words(component))
        if placed is not None:
            return placed

    for label in labels:
        if len(label) > MAX_LABEL_LENGTH:
            # The reading adapter is responsible for bounding a label. One that arrives over
            # the bound is dropped rather than truncated here: truncating would make the
            # classifier's own input depend on a rule nobody can see from the outside.
            continue
        placed = _first_match(_words(label))
        if placed is not None:
            return placed
    return None
