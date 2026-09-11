"""The canonical identity of a discovered URL, and the origin one discovery run is bound to.

Discovery sees the same page under many written forms: with and without a trailing slash on
the root, with a campaign parameter a newsletter appended, with a dot segment a template left
behind, with the scheme or host in a different case. ``site-inventory.v1`` requires those to
collapse onto **one** candidate carrying the provenance of every form that was seen, so this
module is where a written form becomes an identity.

Four properties are the reason it is Domain code rather than a helper in the adapter.

**It is total, deterministic and idempotent.** Every function here is a pure function of its
argument that never raises on a string. The same written form always yields the same key, and a
key canonicalises to itself, which matters beyond tidiness: the origin check re-canonicalises,
so a key that did not reproduce itself would read as outside its own origin.

**It refuses rather than repairs.** A form this module cannot bring into the contract's lexical
shape has no identity and is never persisted. That is the producer side of D-PXAPI19-PO-007: a
credential-bearing URL is refused *before* it could become inventory data, and an arbitrary
attacker-controlled string is not kept merely so that a digest could be recomputed over it.

**It merges only on named grounds.** Every normalisation is either one the URL standards
themselves call equivalent (the case of scheme and host, a default port, dot segments, the case
of a percent escape, an escaped unreserved character, the compressed form of an IPv6 literal)
or one of a few merges this method *declares* and versions: a named set of campaign parameters,
empty query pairs and an empty query. Everything else is kept as written: remaining parameters
keep their order and a trailing slash below the root is kept, because a merge that is wrong
loses a page while a merge declined only yields one more candidate, which the contract says is
not a defect of the website.

**A form the two URL standards read differently has no identity.** RFC 3986 treats a backslash
as data and WHATWG treats it as a path separator for http and https, so a backslash after the
root is a path on this origin to one reader and a different host to the other, and a browser
is the second reader. A form carrying a raw backslash, or any Unicode space a policy might
silently strip, is refused outright rather than keyed under one reading and fetched under the
other.

The canonicalisation method is named and versioned here because ``site-inventory.v1`` fixes the
identity's lexical shape and deliberately not how it was derived: a consumer reads
``discovery_method_version`` to know which rules produced the keys it is looking at.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

import ipaddress
import re
from enum import StrEnum
from typing import Final
from urllib.parse import quote, urlsplit, urlunsplit

#: The canonicalisation method these rules are, and its version. It travels with the inventory
#: as part of the discovery method, because two keys are comparable only under the same rules.
CANONICALISATION_METHOD: Final = "URL_CANONICAL_BASELINE"
CANONICALISATION_VERSION: Final = "1.0.0"

#: The only schemes a public analysis speaks, and the port each defaults to. The mapping is
#: stated here as well as in the target policy because they answer different questions — this
#: one is "which port is redundant in a written form", that one is "where do we connect" — and
#: because the Domain may not import an adapter to ask.
DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}

#: The contract's own lexical shapes, verbatim: ``acquisition#/$defs/public_url`` and
#: ``public_origin``, pattern and ``maxLength`` alike. They are restated rather than read out of
#: the registry because the Domain may not import a validator or a file path, and they are
#: pinned character for character against the schema by ``tests/domain/test_site_identity.py``
#: so the two cannot drift. Python's ``re`` reads the ``\uXXXX`` escapes and the ``(?!\n)$``
#: anchor exactly as the reference validator does — it *is* the engine that validator uses — so
#: a value this module accepts is a value the contract accepts, and the producer can never emit
#: an identity or an observed form its own schema would refuse.
#: The excluded set both patterns share, built from escape *text* so this source file holds no
#: raw control character; the result is character-for-character the schema's pattern text.
_ESCAPE_TEXT: Final = "\\u"
_EXCLUDED: Final = (
    f"{_ESCAPE_TEXT}0000-{_ESCAPE_TEXT}0020{_ESCAPE_TEXT}007F-{_ESCAPE_TEXT}009F"
    f"{_ESCAPE_TEXT}2028{_ESCAPE_TEXT}2029"
)
PUBLIC_URL_PATTERN: Final = (
    f"^https?://[^{_EXCLUDED}/?#@]{{1,253}}(?:[/?#][^{_EXCLUDED}]{{0,1790}})?(?!\\n)$"
)
PUBLIC_ORIGIN_PATTERN: Final = f"^https?://[^{_EXCLUDED}{_ESCAPE_TEXT}005C/?#@]{{1,253}}/?(?!\\n)$"
MAX_URL_LENGTH: Final = 2048
MAX_ORIGIN_LENGTH: Final = 262

_PUBLIC_URL: Final[re.Pattern[str]] = re.compile(PUBLIC_URL_PATTERN)
_PUBLIC_ORIGIN: Final[re.Pattern[str]] = re.compile(PUBLIC_ORIGIN_PATTERN)

#: Characters no part of a written form may carry at all: the C0 controls and space, DEL, the C1
#: controls, the Unicode line and paragraph separators, and the backslash; every other Unicode
#: space is refused beside them, by ``str.isspace``. A form holding one is not repaired by
#: escaping it but refused, because a producer that silently rewrote the bytes it observed would
#: record an ``observed_form`` nobody served, and because the target policy strips surrounding
#: whitespace from a host before resolving it: a form it would strip is a form whose identity and
#: whose destination could differ.
_FORBIDDEN_ANYWHERE: Final[frozenset[str]] = frozenset(
    {chr(code) for code in range(0x00, 0x21)}
    | {chr(0x7F)}
    | {chr(code) for code in range(0x80, 0xA0)}
    | {chr(0x2028), chr(0x2029), chr(0x5C)}
)

#: Characters an authority may not carry beyond those: the four authority terminators and the
#: percent sign. A hostname cannot contain an escape, and the one place the URL grammar admits a
#: percent sign in a host, an IPv6 zone identifier, names a link-local interface no public
#: analysis may reach.
_FORBIDDEN_IN_AUTHORITY: Final[frozenset[str]] = _FORBIDDEN_ANYWHERE | set("/?#@%")

#: Query parameters this version drops from an identity, as a closed, named set. Each is a
#: campaign or click-tracking parameter that every major analytics vendor documents as carrying
#: no addressing meaning: the page served at ``/leistungen?utm_source=newsletter`` is the page
#: served at ``/leistungen``. The set is closed and versioned rather than a prefix guess,
#: because dropping a parameter a site actually routes on would lose a page, and a lost page is
#: the one error this module must not make. ``utm_`` is matched as a prefix because the vendor
#: vocabulary under it is open by design; everything else is matched exactly.
_TRACKING_PREFIXES: Final[tuple[str, ...]] = ("utm_",)
_TRACKING_PARAMETERS: Final[frozenset[str]] = frozenset(
    {
        "gclid",
        "gbraid",
        "wbraid",
        "dclid",
        "fbclid",
        "msclkid",
        "twclid",
        "ttclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "vero_id",
        "_hsenc",
        "_hsmi",
        "hsctatracking",
        "yclid",
        "wickedid",
        "oly_anon_id",
        "oly_enc_id",
    }
)

#: Path suffixes this version records as something other than a page. The list is a technical
#: admissibility statement and never a judgement: a PDF brochure is not a defect of a website,
#: it is simply not an HTML page this analysis fetches. It is deliberately conservative — an
#: extension absent from it yields a page candidate, because treating an unknown extension as
#: a non-page would silently drop real pages served under vanity suffixes.
_NON_PAGE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".7z",
        ".apk",
        ".avi",
        ".avif",
        ".bmp",
        ".bz2",
        ".css",
        ".csv",
        ".dmg",
        ".doc",
        ".docx",
        ".eot",
        ".epub",
        ".exe",
        ".flv",
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".json",
        ".mjs",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".odp",
        ".ods",
        ".odt",
        ".ogg",
        ".otf",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".rss",
        ".svg",
        ".tar",
        ".tgz",
        ".tif",
        ".tiff",
        ".ttf",
        ".txt",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".xls",
        ".xlsx",
        ".xml",
        ".zip",
    }
)

#: A percent escape. Matching the two hex digits explicitly is what lets a stray '%' that is
#: not an escape be refused rather than re-encoded into something the server never served.
_PERCENT_ESCAPE: Final[re.Pattern[str]] = re.compile("%([0-9A-Fa-f]{2})")

#: Characters RFC 3986 calls unreserved: percent-encoding one of them changes nothing about
#: what the URL addresses, so an escape covering one is decoded to give one written identity.
_UNRESERVED: Final[frozenset[str]] = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


class UrlRefusal(StrEnum):
    """Why a written form did not become an identity. Every value names *our* rule.

    None of these is a statement about the website. A URL we refuse to canonicalise is a URL
    this analysis will not carry, which is a bound of ours: the page it names may be perfectly
    ordinary, and nothing downstream may render one of these as a defect.
    """

    #: Not an absolute http or https URL.
    NOT_ABSOLUTE_HTTP = "NOT_ABSOLUTE_HTTP"
    #: The authority carries a userinfo component. Refused before persistence, always.
    CREDENTIALS_PRESENT = "CREDENTIALS_PRESENT"
    #: The URL names no host, or a host our own lexical rules exclude.
    UNUSABLE_AUTHORITY = "UNUSABLE_AUTHORITY"
    #: A character no part of a written form may carry.
    FORBIDDEN_CHARACTER = "FORBIDDEN_CHARACTER"
    #: The canonical form would exceed a bound the contract fixes.
    TOO_LONG = "TOO_LONG"
    #: The value could not be split into a URL at all.
    MALFORMED = "MALFORMED"


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 section 5.2.4, verbatim in behaviour.

    ``/a/b/../c`` addresses ``/a/c`` for every server and every browser, so two forms that
    differ only by a dot segment are one identity. The algorithm is written out rather than
    delegated to ``posixpath`` because that module collapses a repeated slash and drops a
    trailing one, neither of which RFC 3986 does and both of which would merge two URLs a
    server may well distinguish.
    """
    output: list[str] = []
    remaining = path
    while remaining:
        if remaining.startswith("../"):
            remaining = remaining[3:]
        elif remaining.startswith("./"):
            remaining = remaining[2:]
        elif remaining.startswith("/./"):
            remaining = "/" + remaining[3:]
        elif remaining == "/.":
            remaining = "/"
        elif remaining.startswith("/../"):
            remaining = "/" + remaining[4:]
            if output:
                output.pop()
        elif remaining == "/..":
            remaining = "/"
            if output:
                output.pop()
        elif remaining in (".", ".."):
            remaining = ""
        else:
            end = remaining.find("/", 1)
            if end == -1:
                output.append(remaining)
                remaining = ""
            else:
                output.append(remaining[:end])
                remaining = remaining[end:]
    return "".join(output)


def _normalised_escapes(value: str) -> str | None:
    """Percent escapes in upper case, with an escaped unreserved character decoded.

    Returns ``None`` when the value carries a '%' that begins no valid escape: such a value is
    not a URL we can state a canonical form of, and guessing — by escaping the '%' itself —
    would record a form the server never served.
    """
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "%":
            result.append(char)
            index += 1
            continue
        match = _PERCENT_ESCAPE.match(value, index)
        if match is None:
            return None
        decoded = chr(int(match.group(1), 16))
        result.append(decoded if decoded in _UNRESERVED else "%" + match.group(1).upper())
        index = match.end()
    return "".join(result)


def _canonical_query(query: str) -> str:
    """The query with every named tracking parameter dropped, the rest in written order.

    It runs on a query whose escapes are already normalised, so an escaped ``utm_source`` is
    recognised as the ``utm_source`` it is: otherwise a first pass would keep it, decode it, and a
    second pass would drop it, and a key that changes on a second pass is not a key. A pair
    carrying ``;`` is kept whole, because some frameworks read ``;`` as a second separator and
    dropping the pair would drop whatever followed it. Empty pairs are dropped, a declared merge.

    Order is preserved rather than sorted on purpose. Sorting would merge ``?a=1&b=2`` with
    ``?b=2&a=1``, and while those address the same resource on nearly every server, "nearly"
    is not a property an identity may rest on.
    """
    kept: list[str] = []
    for pair in query.split("&"):
        if not pair:
            continue
        name = pair.partition("=")[0].lower()
        tracking = name in _TRACKING_PARAMETERS or name.startswith(_TRACKING_PREFIXES)
        if tracking and ";" not in pair:
            continue
        kept.append(pair)
    return "&".join(kept)


def _split_authority(netloc: str) -> tuple[str, str] | None:
    """``(host, port)`` of an authority, lower-cased, or ``None`` when it may not be carried.

    ``None`` for anything this analysis will not carry: a forbidden character, an empty host, a
    bracketed authority that is not exactly one IPv6 literal, or a second colon outside
    brackets. An IPv6 literal is reduced to its compressed form, which is the same address.
    """
    if any(char in _FORBIDDEN_IN_AUTHORITY or char.isspace() for char in netloc):
        return None

    # A colon separates host from port only when it lies *outside* a bracketed IPv6 literal.
    # Comparing the two last positions is what distinguishes `[::1]`, where every colon is
    # part of the address, from `[::1]:8080`, where the final one is not.
    if netloc.rfind(":") > netloc.rfind("]"):
        host, _, port = netloc.rpartition(":")
    else:
        host, port = netloc, ""

    host = host.lower()
    if not host:
        return None
    if host.startswith("[") or host.endswith("]"):
        if not (host.startswith("[") and host.endswith("]")):
            return None
        try:
            return f"[{ipaddress.IPv6Address(host[1:-1])}]", port
        except ValueError:
            return None
    if ":" in host:
        # Outside brackets a colon can only separate the port, and one already did. A second
        # means this is not a host and a port at all, and splitting it again would key an
        # invalid form onto some valid page.
        return None
    return host, port


def _authority_of(scheme: str, netloc: str) -> str | None:
    """The canonical authority for ``scheme``, or ``None`` when it may not be carried."""
    split = _split_authority(netloc)
    if split is None:
        return None
    host, port_text = split
    if not port_text:
        return host
    # ASCII digits only. `str.isdigit` also accepts a superscript two or an Arabic-Indic digit,
    # and `int` would then either raise on the first or quietly read the second as its value,
    # folding a form no server receives onto a port that one does.
    if not (port_text.isascii() and port_text.isdigit()):
        return None
    port = int(port_text)
    if port == DEFAULT_PORTS[scheme]:
        return host
    if not 0 < port <= 65535:
        return None
    return f"{host}:{port}"


def is_persistable_form(value: str) -> bool:
    """Whether ``value`` may be written into a document as a ``public_url`` at all.

    This is the contract's lexical shape and nothing more — no reachability, no safety, no
    canonical form. It is what decides whether an *observed* form may be persisted: an
    ``observed_form`` is recorded verbatim, because rewriting it would record something nobody
    served, so a form the contract would refuse — ``HTTPS://`` with an upper-case scheme is one —
    is not admitted at all rather than being quietly repaired into one that passes.
    """
    return len(value) <= MAX_URL_LENGTH and _PUBLIC_URL.search(value) is not None


def _canonicalise(value: str) -> tuple[str | None, UrlRefusal | None]:
    """The one decision behind :func:`canonical_url_key` and :func:`refuse`.

    Exactly one of the two results is ``None``, so the key function and the refusal function
    cannot disagree about a form: they are two views of this.
    """
    if any(char in _FORBIDDEN_ANYWHERE or char.isspace() for char in value):
        return None, UrlRefusal.FORBIDDEN_CHARACTER
    try:
        parts = urlsplit(value)
    except ValueError:
        return None, UrlRefusal.MALFORMED
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        return None, UrlRefusal.NOT_ABSOLUTE_HTTP
    if "@" in parts.netloc:
        return None, UrlRefusal.CREDENTIALS_PRESENT
    authority = _authority_of(scheme, parts.netloc)
    if authority is None:
        return None, UrlRefusal.UNUSABLE_AUTHORITY

    # RFC 3986 section 6.2.2 fixes the order: percent-encoding is normalised *before* dot
    # segments are removed, or `/a/%2E%2E/b` would keep its escaped dot segment through removal
    # and only then decode into a traversal. The fragment is never examined: it is dropped.
    escaped_path = _normalised_escapes(parts.path)
    escaped_query = _normalised_escapes(parts.query)
    if escaped_path is None or escaped_query is None:
        return None, UrlRefusal.MALFORMED
    path = _remove_dot_segments(escaped_path) or "/"
    if not path.startswith("/"):
        path = "/" + path
    query = _canonical_query(escaped_query)

    # `quote` percent-encodes what may not appear raw, a non-ASCII character above all, and
    # leaves every existing escape alone: '%' is safe because every '%' left in the value was
    # validated above as the start of an escape, so encoding it again would turn `%C3%A4` into
    # `%25C3%25A4`, the identity of a different URL.
    safe_path = quote(path, safe="/-._~!$&'()*+,;=:@%")
    safe_query = quote(query, safe="/-._~!$&'()*+,;=:@?%")
    key = urlunsplit((scheme, authority, safe_path, safe_query, ""))
    if not is_persistable_form(key):
        # Refused rather than truncated: a shortened key would be the identity of another URL.
        return None, UrlRefusal.TOO_LONG
    return key, None


def refuse(value: str) -> UrlRefusal | None:
    """Why ``value`` cannot become an identity, or ``None`` when it can."""
    return _canonicalise(value)[1]


def canonical_url_key(value: str) -> str | None:
    """The canonical identity of one written URL form, or ``None`` when it has none.

    The rules, in the order they apply, are the whole of version
    ``URL_CANONICAL_BASELINE 1.0.0``:

    1. a form carrying a control character, DEL, a C1 control, a Unicode separator or space, or
       a raw backslash, which RFC 3986 and WHATWG read differently, is refused;
    2. the scheme is lower-cased and must be ``http`` or ``https``;
    3. a userinfo component is refused outright, never stripped;
    4. the host is lower-cased; a percent sign, a second unbracketed colon or a bracketed value
       that is not one IPv6 literal is refused, and an IPv6 literal takes its compressed form;
    5. the port must be ASCII digits in 1..65535, and a port equal to the default is dropped;
    6. the fragment is dropped without being examined;
    7. percent escapes are upper-cased and an escaped unreserved character is decoded;
    8. dot segments are removed per RFC 3986, after rule 7, as section 6.2.2 requires;
    9. an empty path becomes the root ``/``; a trailing slash below the root is kept;
    10. declared merges: the named tracking parameters (recognised after rule 7) are dropped
        unless the pair carries ``;``, empty pairs are dropped, and an emptied query disappears;
        every other parameter keeps its written order;
    11. a character that may not appear raw is percent-encoded; an existing escape never is;
    12. a key the contract's own ``public_url`` shape would refuse is refused, never truncated.
    """
    return _canonicalise(value)[0]


def canonical_origin(value: str) -> str | None:
    """The canonical public origin of ``value``, in the shape ``public_origin`` fixes.

    An origin is a scheme and an authority and the normalised root slash, and nothing else: a
    path beyond the root, a query and a fragment are all discarded, because the member a reader
    treats as the authority for a whole site must not be able to hold one page of it. A value
    that cannot become an identity at all has no origin either.
    """
    key = canonical_url_key(value)
    if key is None:
        return None
    parts = urlsplit(key)
    origin = f"{parts.scheme}://{parts.netloc}/"
    if len(origin) > MAX_ORIGIN_LENGTH or _PUBLIC_ORIGIN.search(origin) is None:
        return None
    return origin


def origin_of_key(url_key: str) -> str | None:
    """The origin a canonical key belongs to. ``None`` if the key is not canonical."""
    if canonical_url_key(url_key) != url_key:
        return None
    return canonical_origin(url_key)


def is_same_origin(url_key: str, origin: str) -> bool:
    """Whether ``url_key`` lies inside ``origin``.

    Exact origin equality: scheme, host and port must all agree. A subdomain is a different
    origin and so is the same host on another scheme or port, which is what keeps a discovery
    boundary a boundary rather than a suggestion. Being outside it is a technical statement —
    the inventory records ``OFF_ORIGIN`` — and never a defect of the page.
    """
    return origin_of_key(url_key) == canonical_origin(origin)


def is_page_resource(url_key: str) -> bool:
    """Whether this identity names something this analysis reads as a page.

    Decided from the path suffix alone, conservatively: an extension this version does not
    know yields ``True``, because treating an unrecognised suffix as a non-page would silently
    drop real pages. A ``False`` is a technical admissibility statement and never a judgement
    about the resource or the site that serves it.
    """
    path = urlsplit(url_key).path
    last = path.rpartition("/")[2]
    dot = last.rfind(".")
    if dot <= 0:
        return True
    return last[dot:].lower() not in _NON_PAGE_SUFFIXES
