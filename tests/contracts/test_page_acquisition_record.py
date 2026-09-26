"""What `page-acquisition-record.v1` guarantees beyond what the generic registry harness checks.

The generic harness already proves the things every contract must satisfy: the registry entry's
shape, that each example validates and declares the registered version, the schema meta-rules,
the pattern dialect, the invalid-fixture expectations and the closed-vocabulary pins. Nothing
below repeats any of that.

What is left is this contract's own semantics, and they are checked in four groups: that the
conditional groups are complete in *both* directions, that every URL-shaped and digest-shaped
member references the narrowed acquisition shapes rather than the wider common ones, that the
members this contract must never grow are absent by name, and that the numeric bounds agree with
the Domain constants that derive them. The registration check asks the registry whether the
contract is there and never how many contracts exist, so registering a later one cannot turn
this module red.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from pxapi.domain.page_acquisition import (
    ACQUISITION_METHOD,
    ACQUISITION_METHOD_VERSION,
    HTTP_STATUS_MAX,
    HTTP_STATUS_MIN,
    MEASUREMENTS_WITHHELD_SOURCE_URL,
    OBSERVATION_MODE_STATIC_HTTP,
    PAGE_ACQUISITION_RECORD,
    is_contract_url,
)
from tests.contracts.support import CONTRACTS, iter_refs, load_json

CONTRACT = PAGE_ACQUISITION_RECORD

ACQUISITION_URL_KEY = "urn:pxapi:schema:acquisition:1.0.0#/$defs/url_key"
ACQUISITION_DIGEST = "urn:pxapi:schema:acquisition:1.0.0#/$defs/digest"
COMMON_ID = "urn:pxapi:schema:common:1.0.0#/$defs/id"
COMMON_URL = "urn:pxapi:schema:common:1.0.0#/$defs/url"

#: The members of the response group: present together, or refused together.
RESPONSE_MEMBERS = (
    "http_status",
    "final_url_key",
    "redirect_count",
    "body_truncated",
    "body_decoded",
)

#: Members the response group refuses outright when no response arrived — the five above plus the
#: two that depend on one.
FORBIDDEN_WITHOUT_RESPONSE = (*RESPONSE_MEMBERS, "body_digest", "raw_artifact_ref")

#: Names this record must never carry. Page content is measured and referenced, never inlined,
#: and a judgement about a page is not a thing an acquisition record may express at all.
BANNED_MEMBERS = (
    "body",
    "raw_body",
    "response_body",
    "html",
    "raw_html",
    "content",
    "headers",
    "response_headers",
    "payload",
    "screenshot",
    "score",
    "severity",
    "polarity",
    "confidence",
    "finding",
    "finding_summary",
    "quality",
    "rating",
    "weight",
)

#: The three member names that legitimately begin with a banned prefix. Without the allow-list a
#: substring ban would forbid the members the contract exists to carry.
ALLOWED_BODY_MEMBERS = ("body_digest", "body_truncated", "body_decoded")


def schema() -> dict[str, Any]:
    return load_json(CONTRACTS.schema_path(CONTRACT))


def example(fragment: str) -> dict[str, Any]:
    path = next(p for p in CONTRACTS.example_paths(CONTRACT) if fragment in p.name)
    return load_json(path)


def keys_of(document: Any) -> set[tuple[str, str]]:
    return {violation.key for violation in CONTRACTS.validate(CONTRACT, document)}


def valid(document: Any) -> bool:
    return CONTRACTS.validate(CONTRACT, document) == ()


def without(document: dict[str, Any], member: str) -> dict[str, Any]:
    candidate = copy.deepcopy(document)
    candidate.pop(member)
    return candidate


def with_member(document: dict[str, Any], member: str, value: Any) -> dict[str, Any]:
    candidate = copy.deepcopy(document)
    candidate[member] = value
    return candidate


# --- registration and the examples ----------------------------------------------------------


def test_the_contract_is_registered() -> None:
    """By name only: a count or an inventory equality would go red on a later contract."""
    assert CONTRACTS.has_contract(CONTRACT)
    assert CONTRACTS.entry(CONTRACT)["owner_slice"].strip()


def test_the_three_examples_cover_a_response_a_failure_and_a_withheld_page() -> None:
    names = [path.name for path in CONTRACTS.example_paths(CONTRACT)]
    assert [
        fragment in name
        for fragment, name in zip(
            ("response-received", "timeout", "measurements-withheld"), names, strict=True
        )
    ] == [True, True, True], names


def test_the_response_example_is_the_first_one_registered() -> None:
    """The generic versioning matrix runs on the first example, so it must be the fullest one."""
    first = example("response-received")
    assert CONTRACTS.example_paths(CONTRACT)[0].name.endswith(
        "page-acquisition-record.response-received.example.json"
    )
    assert all(member in first for member in RESPONSE_MEMBERS)
    assert "body_digest" in first


def test_no_registered_example_emits_a_raw_artifact_ref() -> None:
    """This producer retains nothing, so no example may suggest that it points at an artifact."""
    for path in CONTRACTS.example_paths(CONTRACT):
        assert "raw_artifact_ref" not in load_json(path), path.name


def test_the_withheld_example_carries_a_url_the_measurement_contract_cannot_hold() -> None:
    """The example exists to show C-PXAPI-020, so its identity has to be a real instance of it."""
    withheld = example("measurements-withheld")
    assert withheld["measurement_refs"] == []
    assert withheld["measurements_withheld_reason"] == MEASUREMENTS_WITHHELD_SOURCE_URL
    assert CONTRACTS.validator_for_definition("url_key", shared="acquisition").is_valid(
        withheld["url_key"]
    )
    assert not is_contract_url(withheld["url_key"])


def test_every_example_declares_this_producer_s_method_and_mode() -> None:
    """The contract admits a rendered mode; no example of *this* producer may carry one."""
    for path in CONTRACTS.example_paths(CONTRACT):
        document = load_json(path)
        assert document["observation_mode"] == OBSERVATION_MODE_STATIC_HTTP, path.name
        assert document["acquisition_method"] == ACQUISITION_METHOD, path.name
        assert document["acquisition_method_version"] == ACQUISITION_METHOD_VERSION, path.name


# --- the conditional groups, in both directions ----------------------------------------------


@pytest.mark.parametrize("member", RESPONSE_MEMBERS)
def test_a_received_response_requires_every_response_member(member: str) -> None:
    candidate = without(example("response-received"), member)
    if member == "body_decoded":
        # Removing it also removes the branch that requires the digest, so the digest goes too.
        candidate.pop("body_digest")
    assert ("", "required") in keys_of(candidate)


@pytest.mark.parametrize("member", FORBIDDEN_WITHOUT_RESPONSE)
def test_an_attempt_without_a_response_refuses_every_response_member(member: str) -> None:
    values: dict[str, Any] = {
        "http_status": 503,
        "final_url_key": "https://example.com/kontakt",
        "redirect_count": 0,
        "body_truncated": False,
        "body_decoded": False,
        "body_digest": "sha256:" + "0" * 64,
        "raw_artifact_ref": "art-0001",
    }
    candidate = with_member(example("timeout"), member, values[member])
    assert ("", "not") in keys_of(candidate)


def test_a_decoded_body_requires_its_digest_and_an_undecoded_one_refuses_it() -> None:
    response = example("response-received")
    assert ("", "required") in keys_of(without(response, "body_digest"))
    assert ("", "not") in keys_of(with_member(response, "body_decoded", False))
    undecoded = without(with_member(response, "body_decoded", False), "body_digest")
    assert valid(undecoded), CONTRACTS.validate(CONTRACT, undecoded)


def test_empty_refs_require_a_reason_and_a_non_empty_list_refuses_one() -> None:
    response = example("response-received")
    assert ("", "required") in keys_of(with_member(response, "measurement_refs", []))
    assert ("", "not") in keys_of(
        with_member(response, "measurements_withheld_reason", MEASUREMENTS_WITHHELD_SOURCE_URL)
    )
    assert valid(example("measurements-withheld"))


def test_a_raw_artifact_ref_is_permitted_on_a_received_response() -> None:
    """The member exists for a later slice that retains one; this producer simply never emits it.

    Without this the fixture proving it is refused on a failure would be indistinguishable from
    a contract that forbids the member everywhere, and the next slice would have to version it.
    """
    candidate = with_member(example("response-received"), "raw_artifact_ref", "art-0001")
    assert valid(candidate), CONTRACTS.validate(CONTRACT, candidate)


#: The observation-mode vocabulary the architecture authority fixes for this contract.
#: Confluence `54362115` §7 states the minimum semantics of `page-acquisition-record.v1` as
#: `observation_mode = STATIC_HTTP | RENDERED_BROWSER`, and D-PXAPI-ACQ-005 defines the two as
#: separate observation modes of the *same* record: Pipeline C emits
#: `PageAcquisitionRecord(STATIC_HTTP)` and Pipeline D emits `PageAcquisitionRecord(
#: RENDERED_BROWSER)`. PXAPI-20 implements only the first — that is a *producer* decision
#: (`D-20-C`), enforced by the producer invariant, and it is not this contract's vocabulary.
AUTHORITATIVE_OBSERVATION_MODES = ("STATIC_HTTP", "RENDERED_BROWSER")

#: Modes outside that vocabulary: a case difference, a near-miss, an empty value and tokens a
#: rendered runtime might plausibly invent. None may validate.
UNKNOWN_OBSERVATION_MODES = ("static_http", "STATIC_HTTPS", "", "BROWSER", "HEADLESS_BROWSER")


@pytest.mark.parametrize("mode", AUTHORITATIVE_OBSERVATION_MODES)
def test_the_contract_admits_every_authoritative_observation_mode(mode: str) -> None:
    """The contract represents what the architecture says it represents, producer or no producer."""
    candidate = with_member(example("response-received"), "observation_mode", mode)
    assert valid(candidate), CONTRACTS.validate(CONTRACT, candidate)


@pytest.mark.parametrize("mode", UNKNOWN_OBSERVATION_MODES, ids=lambda m: repr(m))
def test_the_contract_refuses_a_mode_outside_the_authoritative_vocabulary(mode: str) -> None:
    candidate = with_member(example("response-received"), "observation_mode", mode)
    assert ("/observation_mode", "enum") in keys_of(candidate)


def test_the_contract_vocabulary_is_wider_than_what_this_producer_emits() -> None:
    """Schema-valid is not the same thing as valid output of the PXAPI-20 static producer.

    The contract carries both authoritative modes; the static producer emits and accepts one.
    ``tests/domain/test_page_acquisition.py`` proves the other half — a `RENDERED_BROWSER`
    record is contract-valid and still refused by this producer's own invariant.
    """
    declared = schema()["properties"]["observation_mode"]["enum"]
    assert declared == list(AUTHORITATIVE_OBSERVATION_MODES)
    assert OBSERVATION_MODE_STATIC_HTTP in declared
    assert set(declared) - {OBSERVATION_MODE_STATIC_HTTP} == {"RENDERED_BROWSER"}
    assert example("response-received")["observation_mode"] == OBSERVATION_MODE_STATIC_HTTP


# --- shapes: the narrowed acquisition definitions, never the wider common ones ----------------


@pytest.mark.parametrize(
    ("member", "expected"),
    [
        ("url_key", ACQUISITION_URL_KEY),
        ("final_url_key", ACQUISITION_URL_KEY),
        ("sampling_manifest_output_digest", ACQUISITION_DIGEST),
        ("body_digest", ACQUISITION_DIGEST),
        ("run_id", COMMON_ID),
        ("acquisition_id", COMMON_ID),
        ("sampling_manifest_ref", COMMON_ID),
        ("raw_artifact_ref", COMMON_ID),
    ],
)
def test_a_member_references_the_definition_its_meaning_requires(
    member: str, expected: str
) -> None:
    declared = schema()["properties"][member]
    assert declared["$ref"] == expected
    assert set(declared) <= {"$ref", "description"}, f"{member} narrows a shared definition"


def test_no_member_references_the_wider_common_url() -> None:
    """A page URL in this record is an identity, and an identity may never carry a credential."""
    assert COMMON_URL not in set(iter_refs(schema()))
    assert ACQUISITION_URL_KEY in set(iter_refs(schema())), "canary: the walk sees a URL member"


def test_the_measurement_reference_list_refuses_a_repeated_identity() -> None:
    declared = schema()["properties"]["measurement_refs"]
    assert declared["uniqueItems"] is True
    assert declared["items"]["$ref"] == COMMON_ID


# --- the members this record must never grow --------------------------------------------------


def test_no_banned_member_name_appears_in_the_record() -> None:
    declared = set(schema()["properties"])
    offenders = sorted(
        member
        for member in declared
        if member not in ALLOWED_BODY_MEMBERS and any(banned in member for banned in BANNED_MEMBERS)
    )
    assert offenders == []


def test_the_allow_list_only_exempts_members_that_exist() -> None:
    """A stale exemption would quietly permit a name nobody reviews."""
    declared = set(schema()["properties"])
    assert set(ALLOWED_BODY_MEMBERS) <= declared


def test_the_name_ban_would_catch_a_planted_member() -> None:
    """Canary: the scan must reject the names it exists to forbid, and accept the real ones."""
    planted = ("raw_html", "score", "polarity", "response_headers")
    assert all(any(banned in member for banned in BANNED_MEMBERS) for member in planted)
    assert not any(
        member not in ALLOWED_BODY_MEMBERS and any(banned in member for banned in BANNED_MEMBERS)
        for member in ("url_key", "acquired_at", "redirect_count", "body_digest")
    )


def test_the_record_is_closed_at_its_root() -> None:
    assert schema()["additionalProperties"] is False


# --- numeric bounds agree with the Domain constants that derive them --------------------------


def test_the_status_bounds_are_the_domain_s_own() -> None:
    """The Domain derives them from the standard library; the schema must state the same pair."""
    declared = schema()["properties"]["http_status"]
    assert declared["minimum"] == HTTP_STATUS_MIN
    assert declared["maximum"] == HTTP_STATUS_MAX


def test_the_redirect_count_admits_zero_and_refuses_a_negative_one() -> None:
    response = example("response-received")
    assert valid(with_member(response, "redirect_count", 0))
    assert ("/redirect_count", "minimum") in keys_of(with_member(response, "redirect_count", -1))
