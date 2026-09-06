"""The Problem producer is safe by construction, not by filtering.

``to_problem`` turns validator output into a client-readable document. The rules it must obey
are the ones an adapter will inherit, so they are proven here against hostile input rather
than assumed: no validator free text, no exception text, no unresolved contract name, no
unbounded error collection, and output that validates against the Problem contract itself.
"""

from __future__ import annotations

import pytest

from tests.contracts.support import (
    CONTRACTS,
    PROBLEM_CONTRACT,
    Violation,
    load_json,
    to_problem,
    validate,
)

#: Text that must never reach a Problem document, whatever the validator or caller supplies.
HOSTILE = (
    "Traceback (most recent call last):\n"
    '  File "/Users/someone/pxapi/app.py", line 12, in validate\n'
    "  File \u2028/srv/pxapi/secrets.py\u2029, line 3\n"
    "KeyError: 'password=hunter2' token=sk-live-4f9a"
)

INTERNAL_FRAGMENTS = (
    "Traceback (most recent call last)",
    "/Users/",
    "/srv/",
    "password=",
    "sk-live-",
    "KeyError",
    "\n",
    "\r",
    "\u2028",
    "\u2029",
)


def _rendered(document: object) -> str:
    """Everything the document would carry to a client, flattened for a substring search."""
    return repr(document)


def test_problem_built_from_hostile_validator_output_is_sanitised() -> None:
    found = (
        Violation("/detail", "pattern", HOSTILE),
        Violation("", "required", HOSTILE),
    )
    problem = to_problem(PROBLEM_CONTRACT, found)

    assert validate(PROBLEM_CONTRACT, problem) == ()
    assert problem["code"] == "CONTRACT_VALIDATION_FAILED"
    rendered = _rendered(problem)
    for fragment in INTERNAL_FRAGMENTS:
        assert fragment not in rendered, f"internal fragment leaked: {fragment!r}"
    assert {(e["pointer"], e["keyword"]) for e in problem["errors"]} == {
        ("/detail", "pattern"),
        ("", "required"),
    }


def test_problem_errors_carry_structure_only_and_no_message_member() -> None:
    problem = to_problem(PROBLEM_CONTRACT, (Violation("/code", "pattern", HOSTILE),))
    for error in problem["errors"]:
        assert sorted(error) == ["keyword", "pointer"], (
            "a Problem error is (pointer, keyword); a free-text member would reintroduce leakage"
        )


def test_problem_rendering_ignores_the_validator_free_text_entirely() -> None:
    first = to_problem(
        PROBLEM_CONTRACT, (Violation("/a", "type", "one"), Violation("", "required", "two"))
    )
    second = to_problem(
        PROBLEM_CONTRACT, (Violation("/a", "type", HOSTILE), Violation("", "required", ""))
    )
    assert first == second


def test_problem_rendering_is_order_independent() -> None:
    a = Violation("/a", "type", "x")
    b = Violation("/b", "const", "y")
    assert to_problem(PROBLEM_CONTRACT, (a, b)) == to_problem(PROBLEM_CONTRACT, (b, a))


def test_violation_ordering_is_deterministic_and_free_text_independent() -> None:
    unordered = (
        Violation("/z", "type", "zzz"),
        Violation("/a", "pattern", "aaa"),
        Violation("/a", "const", "bbb"),
    )
    keys = [
        e["pointer"] + "|" + e["keyword"] for e in to_problem(PROBLEM_CONTRACT, unordered)["errors"]
    ]
    assert keys == sorted(keys)


# --- untrusted contract names ---------------------------------------------------------------

#: The last entry is a *probe value*, not an inventory claim: it must name a contract-shaped
#: string that is plausible enough to be echoed by accident and that no slice registers. It
#: previously held "measurement-record", which PXK-61 then registered — the self-guard below is
#: what caught that, and it is the reason the guard stays.
UNTRUSTED_NAMES = [
    "no-such-contract",
    "../../etc/passwd",
    "problem\nX-Injected: 1",
    "<script>alert(1)</script>",
    "untrusted-name-probe",
]


@pytest.mark.parametrize("name", UNTRUSTED_NAMES, ids=repr)
def test_an_unregistered_contract_name_is_never_reflected_into_the_document(name: str) -> None:
    assert not CONTRACTS.has_contract(name), f"{name!r} is registered; pick an unregistered name"
    problem = to_problem(name, (Violation("/x", "type", HOSTILE),))

    assert validate(PROBLEM_CONTRACT, problem) == ()
    assert problem["code"] == "CONTRACT_NOT_FOUND"
    rendered = _rendered(problem)
    for fragment in (name, "etc/passwd", "<script>", "X-Injected"):
        if fragment.strip():
            assert fragment not in rendered, f"untrusted input reflected: {fragment!r}"


def test_a_registered_contract_name_is_echoed_from_the_registry() -> None:
    """The one name that may appear is the manifest's own value, not the caller's string."""
    name = CONTRACTS.names()[0]
    problem = to_problem(name, (Violation("/x", "type", "irrelevant"),))
    assert CONTRACTS.entry(name)["name"] in problem["detail"]
    assert validate(PROBLEM_CONTRACT, problem) == ()


# --- the bounded error collection -------------------------------------------------------------


def test_the_problem_contract_bounds_its_error_collection() -> None:
    schema = load_json(CONTRACTS.schema_path(PROBLEM_CONTRACT))
    bound = schema["properties"]["errors"]["maxItems"]
    assert isinstance(bound, int) and bound > 0, "errors must carry a finite, positive bound"
    assert bound == CONTRACTS.max_problem_errors()


def test_the_producer_truncates_to_the_bound_and_still_reports_the_true_count() -> None:
    bound = CONTRACTS.max_problem_errors()
    found = tuple(Violation(f"/f{index:04d}", "type", HOSTILE) for index in range(bound * 3))
    problem = to_problem(PROBLEM_CONTRACT, found)

    assert validate(PROBLEM_CONTRACT, problem) == (), "an over-long document must not be produced"
    assert len(problem["errors"]) == bound
    assert f"{len(found)} violation(s)" in problem["detail"], "the true count must survive"
    assert f"{bound} reported" in problem["detail"]


def test_an_unbounded_error_list_is_rejected_by_the_contract() -> None:
    bound = CONTRACTS.max_problem_errors()
    document = {
        "schema_version": CONTRACTS.entry(PROBLEM_CONTRACT)["version"],
        "code": "CONTRACT_VALIDATION_FAILED",
        "title": "Contract validation failed",
        "detail": "Too many errors were reported.",
        "errors": [{"pointer": f"/f{i}", "keyword": "type"} for i in range(bound + 1)],
    }
    assert ("/errors", "maxItems") in {v.key for v in validate(PROBLEM_CONTRACT, document)}


# --- registered codes and transport neutrality -------------------------------------------------


def test_every_registered_problem_code_produces_a_valid_document() -> None:
    version = CONTRACTS.entry(PROBLEM_CONTRACT)["version"]
    for item in CONTRACTS.problem_codes():
        document = {
            "schema_version": version,
            "code": item["code"],
            "title": "Registered problem",
            "detail": "A registered code produces a valid document.",
            "errors": [],
        }
        assert validate(PROBLEM_CONTRACT, document) == (), item["code"]


def test_a_code_registered_later_remains_consumable_today() -> None:
    """The code is an open token, so adding one is additive and breaks no existing consumer."""
    future = "RATE_LIMIT_EXCEEDED"
    assert future not in {item["code"] for item in CONTRACTS.problem_codes()}
    document = {
        "schema_version": CONTRACTS.entry(PROBLEM_CONTRACT)["version"],
        "code": future,
        "title": "Rate limit exceeded",
        "detail": "The requester exceeded its quota; retry later.",
        "errors": [],
    }
    assert validate(PROBLEM_CONTRACT, document) == ()


def test_the_problem_contract_carries_no_transport_binding() -> None:
    schema = load_json(CONTRACTS.schema_path(PROBLEM_CONTRACT))
    bound = {"status", "http_status", "type", "instance", "headers"} & set(schema["properties"])
    assert bound == set(), f"Problem is transport-neutral; adapter concerns leaked: {bound}"


# --- single-line discipline ---------------------------------------------------------------------

#: Characters that break a single-line field. C0 and C1 controls, DEL, and the two Unicode
#: separators that a naive `[^\r\n]` guard lets through while a renderer still breaks on them.
LINE_BREAKING = [
    "\n",
    "\r",
    "\t",
    "\x0b",
    "\x0c",
    "\x00",
    "\x1b",
    "\x7f",
    "\x85",
    "\x9b",
    "\u2028",
    "\u2029",
]


@pytest.mark.parametrize("member", ["title", "detail"])
@pytest.mark.parametrize("char", LINE_BREAKING, ids=[repr(c) for c in LINE_BREAKING])
def test_single_line_fields_reject_control_and_separator_characters(member: str, char: str) -> None:
    document = load_json(CONTRACTS.example_paths(PROBLEM_CONTRACT)[0])
    document[member] = f"before{char}after"
    assert (f"/{member}", "pattern") in {v.key for v in validate(PROBLEM_CONTRACT, document)}, (
        f"{member} accepted {char!r}"
    )


@pytest.mark.parametrize("member", ["title", "detail"])
def test_single_line_fields_reject_blank_and_padded_values(member: str) -> None:
    document = load_json(CONTRACTS.example_paths(PROBLEM_CONTRACT)[0])
    for value in ("", " ", "   ", " padded "):
        candidate = dict(document, **{member: value})
        assert validate(PROBLEM_CONTRACT, candidate), f"{member} accepted {value!r}"
