"""Canonical identity as properties over a generated corpus, not over hand-picked examples.

Twenty-odd hand-written forms proved each rule; they could not prove the rules compose. An
adversarial review fuzzed the first version and found 213 non-idempotent keys and 141 crashes in
991 generated forms — a non-idempotent key is not a cosmetic defect, because the origin check
re-canonicalises, so such a key reads as *outside its own origin* and a same-origin page was
emitted as ``OFF_ORIGIN``. The corpus is generated from a fixed seed, so it is identical on every
run, and it deliberately mixes every component that interacts: case, ports in several scripts,
userinfo, escapes, dot segments, backslashes, Unicode spaces, tracking parameters and fragments.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

from pxapi.domain import site_identity as si
from tests.contracts.support import CONTRACTS

PUBLIC_URL = CONTRACTS.validator_for_definition("public_url", shared="acquisition")

#: Every component has a clean pool and a hostile pool. Each is drawn from the hostile pool with
#: probability ``HOSTILE``, so about half of all forms are fully clean and yield a key: a corpus
#: that was nearly all refusals would prove the key properties on almost nothing, and the canary
#: below keeps that balance honest in both directions.
HOSTILE = 0.08
SCHEMES = (["http", "https", "HTTP", "HtTpS"], ["ftp", ""])
HOSTS = (
    ["example.com", "EXAMPLE.com", "sub.example.com", "[2001:db8::1]", "127.0.0.1", "example.com."],
    ["[::1", "ex%41mple.com", "exa\u00a0mple.com", "b\u00fccher.de", "a" * 260, ""],
)
PORTS = (
    ["", ":", ":80", ":443", ":8080"],
    [":0", ":65536", ":\u00b2", ":\u0668\u0660", ":80:443", ":x"],
)
USERINFO = ([""], ["user@", "user:pw@", "@"])
SEGMENTS = (
    [
        "a",
        "b",
        "..",
        ".",
        "%2e%2E",
        "%7e",
        "%c3%a4",
        "\u00e4",
        "a%2Fb",
        "a|b",
        "leistungen",
        "",
        "~",
        "%5C",
    ],
    ["%zz", "%", "a\\b", "x y", "\u3000", "z" * 900],
)
QUERY = (
    [
        "a=1",
        "b=2",
        "utm_source=x",
        "UTM_MEDIUM=y",
        "%75tm_source=z",
        "gclid=g",
        "a=1;b=2",
        "utm_source=x;id=7",
        "q=%c3%a4",
        "",
        "ref=1",
    ],
    ["q=a\\b", "q=%"],
)
FRAGMENTS = (["", "", "#", "#top", "#%zz"], ["#a b"])


def generated(count: int, seed: int) -> Iterator[str]:
    rng = random.Random(seed)

    def pick(pools: tuple[list[str], list[str]]) -> str:
        clean, hostile = pools
        return rng.choice(hostile if rng.random() < HOSTILE else clean)

    for _ in range(count):
        path = "/".join(pick(SEGMENTS) for _ in range(rng.randint(0, 4)))
        query = "&".join(pick(QUERY) for _ in range(rng.randint(0, 3)))
        yield (
            pick(SCHEMES)
            + "://"
            + pick(USERINFO)
            + pick(HOSTS)
            + pick(PORTS)
            + "/"
            + path
            + ("?" + query if query or rng.random() < 0.1 else "")
            + pick(FRAGMENTS)
        )


CORPUS = list(generated(3000, 19))


def test_the_corpus_reaches_both_verdicts() -> None:
    """Canary: a corpus that only produced keys, or only refusals, would prove nothing."""
    keys = [si.canonical_url_key(form) for form in CORPUS]
    assert sum(key is None for key in keys) > 300
    assert sum(key is not None for key in keys) > 300


def test_no_generated_form_makes_canonicalisation_raise() -> None:
    """A raise inside the scope or admission takes a whole discovery source down with it."""
    crashes = []
    for form in CORPUS:
        try:
            si.refuse(form)
            si.canonical_url_key(form)
            si.canonical_origin(form)
        except Exception as error:
            crashes.append((form, type(error).__name__))
    assert crashes == [], f"{len(crashes)} crashes, first: {crashes[:3]}"


def test_every_key_is_idempotent_contract_valid_and_inside_its_own_origin() -> None:
    broken = []
    for form in CORPUS:
        key = si.canonical_url_key(form)
        if key is None:
            continue
        problems = []
        if si.canonical_url_key(key) != key:
            problems.append("not idempotent")
        if list(PUBLIC_URL.iter_errors(key)):
            problems.append("fails public_url")
        if not si.is_same_origin(key, si.canonical_origin(key) or ""):
            problems.append("outside its own origin")
        if si.refuse(key) is not None:
            problems.append("its own key is refused")
        if problems:
            broken.append((form, key, problems))
    assert broken == [], f"{len(broken)} broken keys, first: {broken[:3]}"


def test_a_form_is_refused_exactly_when_it_has_no_key() -> None:
    """``refuse`` and ``canonical_url_key`` are two views of one decision and must agree."""
    disagreements = [
        form
        for form in CORPUS
        if (si.refuse(form) is None) != (si.canonical_url_key(form) is not None)
    ]
    assert disagreements == [], f"{len(disagreements)} disagree, first: {disagreements[:3]}"
