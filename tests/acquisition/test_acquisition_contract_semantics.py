"""What the two acquisition contracts make structurally impossible.

The rules under proof here are the ones PXAPI-19.A exists to fix in place, and each is checked
against the declared vocabularies rather than against a hand-picked example: widening a
vocabulary widens these matrices too, so a token nobody thought about cannot slip past on the
strength of the cases someone happened to write.

* A technical condition of the analysis — an absent sitemap, a malformed source, an exhausted
  budget, a refusal, a provider or runtime failure, a timeout, an unclassified page, a bounded
  selection — cannot become a judgement about the website, because no member able to carry one
  exists and the closed roots refuse an added one.
* ``sources`` is the only root authority on discovery source state.
* An inventory is never emitted empty; a discovery that found nothing beyond the homepage is a
  one-candidate inventory, not a zero-candidate one.
* Observations that share a canonical identity aggregate provenance; duplication is not an
  exclusion, not a defect and not a vocabulary token.
* A credential-bearing URL can never become persisted canonical contract data.
* Selection is Pixelkiez methodology: nothing here lets a provider own page selection, and no
  census-to-sampling threshold is invented.

Where a rule is already owned by a generic registry test — closure, version pinning, example
validity, the vocabulary pins — it is not restated here.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.contracts.support import CONTRACTS, load_json
from tests.test_closed_vocabularies import (
    ADMITTING_SOURCE_OUTCOMES,
    CANDIDATE_EXCLUSION_REASONS,
    ELIGIBILITY_STATES,
    SAMPLING_MODES,
    SELECTION_EXCLUSION_REASONS,
    SELECTION_REASONS,
    SOURCE_OUTCOMES,
)

INVENTORY = "site-inventory"
MANIFEST = "sampling-manifest"
SHARED = "acquisition"
CONTRACT_NAMES = (INVENTORY, MANIFEST)

#: The shapes a URL-valued member of these contracts may use. ``common#/$defs/url`` is
#: deliberately not among them: it permits userinfo, which D-PXAPI19-PO-007 forbids from ever
#: becoming persisted canonical data.
URL_REFS = frozenset(
    {
        "urn:pxapi:schema:acquisition:1.0.0#/$defs/public_url",
        "urn:pxapi:schema:acquisition:1.0.0#/$defs/url_key",
    }
)
WEAKER_URL_REF = "urn:pxapi:schema:common:1.0.0#/$defs/url"

CREDENTIAL_URL = "https://admin:s3cret@example.com/"

#: Member-name fragments that would let one of these contracts state a verdict about a site.
#: None may appear as, or inside, a declared member name at any depth.
JUDGEMENT_FRAGMENTS = (
    "score",
    "severity",
    "polarity",
    "grade",
    "rating",
    "priority",
    "confidence",
    "penalty",
    "weight",
    "quality",
    "defect",
    "recommend",
)

#: Member-name fragments that would let a crawl provider own page selection, or would drag raw
#: page text into a canonical contract.
DELEGATION_FRAGMENTS = ("crawl", "provider", "browser", "render", "threshold")
TRANSIENT_FRAGMENTS = ("anchor_label", "link_text", "rejected_url", "raw_", "html", "body")

#: The distinctions D-PXAPI19-PO-005 requires the source-state vocabulary to be able to make,
#: mapped to the token that makes each. The test below proves the mapping is total in both
#: directions, so neither a missing authority requirement nor an unauthorised extra token can
#: pass unnoticed.
AUTHORITY_REQUIRED_SOURCE_DISTINCTIONS: dict[str, str] = {
    "successful / used": "USED",
    "applicable empty valid sitemap": "EMPTY",
    "absent": "ABSENT",
    "malformed": "MALFORMED",
    "applicable present-without-sitemap-declaration": "NO_SITEMAP_DECLARATION",
    "budget exhausted": "BUDGET_EXHAUSTED",
    "target-policy refusal": "TARGET_POLICY_REFUSED",
    "provider failure": "PROVIDER_FAILURE",
    "runtime failure": "RUNTIME_ERROR",
    "timeout": "TIMEOUT",
}


def schema_of(contract: str) -> dict[str, Any]:
    return load_json(CONTRACTS.schema_path(contract))


def examples_of(contract: str) -> list[dict[str, Any]]:
    return [load_json(path) for path in CONTRACTS.example_paths(contract)]


def _example_named(contract: str, fragment: str) -> dict[str, Any]:
    path = next(p for p in CONTRACTS.example_paths(contract) if fragment in p.name)
    return load_json(path)


def inventory(**overrides: Any) -> dict[str, Any]:
    """The minimal valid inventory — the homepage-only example — with members replaced.

    The digests are not recomputed: a digest is not a schema constraint, and what these proofs
    are about is what the schema admits.
    """
    document = copy.deepcopy(_example_named(INVENTORY, "homepage-only"))
    document.update(copy.deepcopy(overrides))
    return document


def manifest(**overrides: Any) -> dict[str, Any]:
    document = copy.deepcopy(_example_named(MANIFEST, "sampling-manifest.example"))
    document.update(copy.deepcopy(overrides))
    return document


def source(**overrides: Any) -> dict[str, Any]:
    return dict({"source_id": "SITEMAP", "outcome": "USED", "candidate_count": 0}, **overrides)


def candidate(**overrides: Any) -> dict[str, Any]:
    base = {
        "url_key": "https://example.org/leistungen",
        "observed_forms": ["https://example.org/leistungen"],
        "provenance": ["SITEMAP"],
        "eligibility": {"state": "ELIGIBLE"},
    }
    return dict(base, **overrides)


def _keys(contract: str, document: Any) -> set[tuple[str, str]]:
    return {violation.key for violation in CONTRACTS.validate(contract, document)}


def _valid(contract: str, document: Any) -> bool:
    return CONTRACTS.validate(contract, document) == ()


def _member_names(node: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                names |= set(value)
                for member in value.values():
                    names |= _member_names(member)
            else:
                names |= _member_names(value)
    elif isinstance(node, list):
        for value in node:
            names |= _member_names(value)
    return names


def _refs(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            found.append(node["$ref"])
        for value in node.values():
            found.extend(_refs(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_refs(value))
    return found


def _vocabularies(node: Any) -> list[list[str]]:
    found: list[list[str]] = []
    if isinstance(node, dict):
        declared = node.get("enum")
        if isinstance(declared, list):
            found.append([token for token in declared if isinstance(token, str)])
        for value in node.values():
            found.extend(_vocabularies(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_vocabularies(value))
    return found


# --- canaries ---------------------------------------------------------------------------------


def test_the_two_contracts_are_registered_and_the_lexical_block_is_shared() -> None:
    """A shape both carriers embed is a shared definition, never a registered contract."""
    for contract in CONTRACT_NAMES:
        assert CONTRACTS.has_contract(contract), contract
    assert SHARED in {entry["name"] for entry in CONTRACTS.shared_definitions()}
    assert not CONTRACTS.has_contract(SHARED), (
        "a registered contract must pin its own schema_version at its root, which an embedded "
        "lexical definition would drag into every document that references it"
    )


def test_the_builders_produce_valid_documents() -> None:
    """Without this every rejection proof below could be passing for the wrong reason."""
    assert _valid(INVENTORY, inventory())
    assert _valid(MANIFEST, manifest())
    assert _valid(INVENTORY, inventory(sources=[source()], candidates=[candidate()]))


def test_every_declared_vocabulary_is_non_empty() -> None:
    assert SOURCE_OUTCOMES and CANDIDATE_EXCLUSION_REASONS and ELIGIBILITY_STATES
    assert SAMPLING_MODES and SELECTION_REASONS and SELECTION_EXCLUSION_REASONS


def test_the_member_name_scanner_sees_a_planted_member() -> None:
    """Canary for the name scans below."""
    planted = {"properties": {"ok": {"properties": {"score": {"type": "integer"}}}}}
    assert _member_names(planted) == {"ok", "score"}


# --- D-PXAPI19-PO-005: one authority for discovery source state -------------------------------


def test_the_source_vocabulary_makes_every_distinction_the_authority_requires() -> None:
    """Total in both directions: no requirement unmet, and no token nobody authorised."""
    mapped = AUTHORITY_REQUIRED_SOURCE_DISTINCTIONS
    assert len(set(mapped.values())) == len(mapped), "two distinctions share one token"
    unmet = sorted(name for name, token in mapped.items() if token not in SOURCE_OUTCOMES)
    assert unmet == [], f"the vocabulary cannot express: {unmet}"
    unauthorised = sorted(set(SOURCE_OUTCOMES) - set(mapped.values()))
    assert unauthorised == [], f"tokens no authority asked for: {unauthorised}"


def test_no_root_member_is_a_second_authority_on_a_discovery_source() -> None:
    """D-PXAPI19-PO-005: no root sitemap_state or robots_state beside ``sources``."""
    declared = set(schema_of(INVENTORY)["properties"])
    offenders = sorted(member for member in declared if "sitemap" in member or "robots" in member)
    assert offenders == [], f"root members shadowing sources: {offenders}"
    assert "sources" in declared


@pytest.mark.parametrize("member", ["sitemap_state", "robots_state", "sitemap_outcome"])
def test_a_parallel_root_source_state_is_refused(member: str) -> None:
    assert ("", "additionalProperties") in _keys(INVENTORY, inventory(**{member: "PRESENT"}))


@pytest.mark.parametrize("outcome", SOURCE_OUTCOMES)
def test_every_declared_source_outcome_validates_on_a_source_entry(outcome: str) -> None:
    count = 1 if outcome in ADMITTING_SOURCE_OUTCOMES else 0
    document = inventory(sources=[source(outcome=outcome, candidate_count=count)])
    assert _valid(INVENTORY, document), f"{outcome}: {sorted(_keys(INVENTORY, document))}"


NON_ADMITTING = [outcome for outcome in SOURCE_OUTCOMES if outcome not in ADMITTING_SOURCE_OUTCOMES]


@pytest.mark.parametrize("outcome", NON_ADMITTING)
def test_a_source_that_could_not_admit_anything_may_not_report_candidates(outcome: str) -> None:
    """An absent, malformed, undeclared, refused or failed source cannot arrive downstream as
    'this source contributed N pages', and a zero from one is never a claim about the site."""
    document = inventory(sources=[source(outcome=outcome, candidate_count=1)])
    assert ("/sources/0/candidate_count", "const") in _keys(INVENTORY, document)


@pytest.mark.parametrize("outcome", ADMITTING_SOURCE_OUTCOMES)
def test_an_outcome_under_which_admission_happened_may_report_a_count(outcome: str) -> None:
    """The rule above must not have made every count impossible."""
    assert _valid(INVENTORY, inventory(sources=[source(outcome=outcome, candidate_count=7)]))


def test_the_non_admitting_set_is_not_empty() -> None:
    assert NON_ADMITTING, "canary: every outcome may admit, so the zero rule proves nothing"


@pytest.mark.parametrize("token", ["OK", "used", "PARTIALLY_USED", "NEGATIVE", "POOR", ""])
def test_an_unrecognised_or_evaluative_source_outcome_is_refused(token: str) -> None:
    document = inventory(sources=[source(outcome=token)])
    assert ("/sources/0/outcome", "enum") in _keys(INVENTORY, document)


def test_a_source_entry_may_not_grow_a_member_that_judges_the_website() -> None:
    for member in ("polarity", "severity", "site_quality", "score"):
        document = inventory(sources=[source(**{member: "NEGATIVE"})])
        assert ("/sources/0", "additionalProperties") in _keys(INVENTORY, document), member


def test_a_source_entry_always_states_how_many_candidates_it_contributed() -> None:
    entry = source()
    del entry["candidate_count"]
    assert ("/sources/0", "required") in _keys(INVENTORY, inventory(sources=[entry]))


def test_an_inventory_that_names_no_attempted_source_is_refused() -> None:
    assert ("/sources", "minItems") in _keys(INVENTORY, inventory(sources=[]))


def test_a_fractional_candidate_count_is_refused() -> None:
    """No floating-point member may reach a digest-relevant projection."""
    document = inventory(sources=[source(candidate_count=2.5)])
    assert ("/sources/0/candidate_count", "type") in _keys(INVENTORY, document)


# --- D-PXAPI19-PO-006: bootstrap truth --------------------------------------------------------


def test_an_inventory_with_no_candidate_is_not_representable() -> None:
    """A successful zero-candidate inventory would read as 'this site has no pages'."""
    assert ("/candidates", "minItems") in _keys(INVENTORY, inventory(candidates=[]))


def test_the_homepage_only_inventory_is_the_valid_no_further_discovery_shape() -> None:
    """The registered replacement for an ``empty-discovery`` example: one candidate, and every
    other source recording a neutral technical outcome."""
    document = _example_named(INVENTORY, "homepage-only")
    assert _valid(INVENTORY, document)
    assert len(document["candidates"]) == 1
    assert document["candidates"][0]["url_key"] == document["target_origin"]
    outcomes = {entry["outcome"] for entry in document["sources"]}
    assert outcomes - {"USED"}, "the example must record at least one neutral non-USED outcome"


def test_no_registered_example_is_an_empty_discovery() -> None:
    """D-PXAPI19-PO-006 replaced that example; nothing may reintroduce it by name or by shape."""
    for path in CONTRACTS.example_paths(INVENTORY):
        assert "empty-discovery" not in path.name, path.name
    for document in examples_of(INVENTORY):
        assert document["candidates"], document["inventory_id"]


def test_every_registered_inventory_contains_its_canonical_target_seed() -> None:
    """An emitted inventory always holds the seed, and its identity is the target origin.

    JSON Schema cannot compare two members of one document, so this rule is enforced over every
    registered example rather than by the schema; the schema enforces the part it can, that the
    candidate list is never empty.
    """
    for document in examples_of(INVENTORY):
        keys = {entry["url_key"] for entry in document["candidates"]}
        assert document["target_origin"] in keys, document["inventory_id"]


def test_every_registered_inventory_marks_its_seed_eligible() -> None:
    for document in examples_of(INVENTORY):
        seed = next(
            entry
            for entry in document["candidates"]
            if entry["url_key"] == document["target_origin"]
        )
        assert seed["eligibility"] == {"state": "ELIGIBLE"}, document["inventory_id"]


# --- neutrality -------------------------------------------------------------------------------


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
@pytest.mark.parametrize("fragment", JUDGEMENT_FRAGMENTS)
def test_no_declared_member_could_carry_a_judgement_about_the_site(
    contract: str, fragment: str
) -> None:
    offenders = sorted(name for name in _member_names(schema_of(contract)) if fragment in name)
    assert offenders == [], f"{contract} declares {offenders}"


#: Every neutral technical condition these contracts can record, as
#: ``(contract, description, document)``. It is built from the declared vocabularies, so a new
#: token joins this matrix automatically.
NEUTRAL_CONDITIONS: list[tuple[str, str, dict[str, Any]]] = (
    [
        (
            INVENTORY,
            f"source-{outcome}",
            inventory(
                sources=[
                    source(
                        outcome=outcome,
                        candidate_count=1 if outcome in ADMITTING_SOURCE_OUTCOMES else 0,
                    )
                ]
            ),
        )
        for outcome in SOURCE_OUTCOMES
    ]
    + [
        (
            INVENTORY,
            f"excluded-{reason}",
            inventory(
                candidates=[
                    candidate(eligibility={"state": "EXCLUDED", "exclusion_reason": reason})
                ]
            ),
        )
        for reason in CANDIDATE_EXCLUSION_REASONS
    ]
    + [(INVENTORY, "unclassified-candidate", inventory(candidates=[candidate()]))]
    + [
        (MANIFEST, "bounded-selection", manifest(selection_complete=False)),
        (MANIFEST, "complete-selection", manifest(selection_complete=True)),
    ]
    + [
        (
            MANIFEST,
            f"not-selected-{reason}",
            manifest(exclusions=[{"reason": reason, "candidate_count": 3}]),
        )
        for reason in SELECTION_EXCLUSION_REASONS
    ]
)
NEUTRAL_IDS = [f"{contract}/{name}" for contract, name, _ in NEUTRAL_CONDITIONS]


def test_the_neutrality_matrix_is_not_empty() -> None:
    """Without this, every neutrality proof below would pass over an empty list."""
    expected = (
        len(SOURCE_OUTCOMES)
        + len(CANDIDATE_EXCLUSION_REASONS)
        + 1
        + 2
        + len(SELECTION_EXCLUSION_REASONS)
    )
    assert len(NEUTRAL_CONDITIONS) == expected > 0


@pytest.mark.parametrize(("contract", "name", "document"), NEUTRAL_CONDITIONS, ids=NEUTRAL_IDS)
def test_every_neutral_technical_condition_is_representable(
    contract: str, name: str, document: dict[str, Any]
) -> None:
    """A condition that could not be recorded at all would be recorded as something else."""
    assert _valid(contract, document), f"{name}: {sorted(_keys(contract, document))}"


@pytest.mark.parametrize(("contract", "name", "document"), NEUTRAL_CONDITIONS, ids=NEUTRAL_IDS)
@pytest.mark.parametrize("verdict", [("polarity", "NEGATIVE"), ("score", 12), ("severity", "HIGH")])
def test_no_neutral_technical_condition_can_be_given_a_verdict(
    contract: str, name: str, document: dict[str, Any], verdict: tuple[str, Any]
) -> None:
    """The structural guarantee: there is no member for a verdict, and the closed root refuses
    one — so a timeout, a refusal, a failure, an unclassified page or a bounded selection cannot
    become a statement about the customer's website."""
    member, value = verdict
    candidate_document = dict(document, **{member: value})
    assert ("", "additionalProperties") in _keys(contract, candidate_document), name


def test_an_unclassified_candidate_is_valid_and_says_nothing_about_the_page() -> None:
    """Absence of a page type is a fact about the classifier, and absence cannot carry a
    judgement."""
    unclassified = candidate()
    assert "page_type" not in unclassified
    assert _valid(INVENTORY, inventory(candidates=[unclassified]))


@pytest.mark.parametrize("token", ["homepage", "Offer", "OFFER!", ""])
def test_a_page_type_stays_a_stable_token_rather_than_prose(token: str) -> None:
    document = inventory(candidates=[candidate(page_type=token)])
    assert ("/candidates/0/page_type", "pattern") in _keys(INVENTORY, document)


@pytest.mark.parametrize("state", ELIGIBILITY_STATES)
def test_each_eligibility_state_is_representable(state: str) -> None:
    eligibility: dict[str, Any] = {"state": state}
    if state == "EXCLUDED":
        eligibility["exclusion_reason"] = CANDIDATE_EXCLUSION_REASONS[0]
    assert _valid(INVENTORY, inventory(candidates=[candidate(eligibility=eligibility)]))


@pytest.mark.parametrize("reason", CANDIDATE_EXCLUSION_REASONS)
def test_an_eligible_candidate_may_never_carry_an_exclusion_reason(reason: str) -> None:
    eligibility = {"state": "ELIGIBLE", "exclusion_reason": reason}
    document = inventory(candidates=[candidate(eligibility=eligibility)])
    assert ("/candidates/0/eligibility", "not") in _keys(INVENTORY, document)


def test_an_excluded_candidate_must_name_its_technical_reason() -> None:
    document = inventory(candidates=[candidate(eligibility={"state": "EXCLUDED"})])
    assert ("/candidates/0/eligibility", "required") in _keys(INVENTORY, document)


@pytest.mark.parametrize("token", ["THIN_CONTENT", "LOW_QUALITY", "off_origin", "NOT_RELEVANT"])
def test_an_exclusion_reason_outside_the_closed_vocabulary_is_refused(token: str) -> None:
    eligibility = {"state": "EXCLUDED", "exclusion_reason": token}
    document = inventory(candidates=[candidate(eligibility=eligibility)])
    assert ("/candidates/0/eligibility/exclusion_reason", "enum") in _keys(INVENTORY, document)


# --- D-PXAPI19-PO-007: duplicate, rejected and transient URL truth ----------------------------


def test_observations_sharing_one_identity_aggregate_provenance() -> None:
    """Two sources and three observed forms collapsing onto one identity is one candidate."""
    aggregated = candidate(
        observed_forms=[
            "https://example.org/leistungen",
            "https://example.org/leistungen?utm_source=mail",
            "https://example.org/leistungen#top",
        ],
        provenance=["CANONICAL_SEED", "SAME_ORIGIN_PAGE_LINKS", "SITEMAP"],
    )
    assert _valid(INVENTORY, inventory(candidates=[aggregated]))


def test_duplication_is_not_an_exclusion_reason_anywhere_in_either_contract() -> None:
    """D-PXAPI19-PO-007: no DUPLICATE_URL_KEY token without a proven new semantic need."""
    for contract in CONTRACT_NAMES:
        declared = _vocabularies(schema_of(contract))
        tokens = {token for vocabulary in declared for token in vocabulary}
        offenders = sorted(token for token in tokens if "DUPLICATE" in token)
        assert offenders == [], f"{contract} declares {offenders}"


def test_a_candidate_must_name_at_least_one_source_and_no_source_twice() -> None:
    assert ("/candidates/0/provenance", "minItems") in _keys(
        INVENTORY, inventory(candidates=[candidate(provenance=[])])
    )
    assert ("/candidates/0/provenance", "uniqueItems") in _keys(
        INVENTORY, inventory(candidates=[candidate(provenance=["SITEMAP", "SITEMAP"])])
    )


def test_a_candidate_must_name_at_least_one_observed_form_and_no_form_twice() -> None:
    form = "https://example.org/leistungen"
    assert ("/candidates/0/observed_forms", "minItems") in _keys(
        INVENTORY, inventory(candidates=[candidate(observed_forms=[])])
    )
    assert ("/candidates/0/observed_forms", "uniqueItems") in _keys(
        INVENTORY, inventory(candidates=[candidate(observed_forms=[form, form])])
    )


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
def test_no_url_valued_member_uses_the_shape_that_permits_a_credential(contract: str) -> None:
    """The blanket guarantee: every URL-shaped member of these contracts resolves to the
    credential-free shape, so a member someone forgets cannot become the way userinfo is
    persisted."""
    used = set(_refs(schema_of(contract)))
    assert WEAKER_URL_REF not in used, f"{contract} references the userinfo-permitting url shape"
    assert used & URL_REFS, f"{contract} references no credential-free URL shape at all"


CREDENTIAL_SITES: list[tuple[str, str, dict[str, Any]]] = [
    (INVENTORY, "/target_origin", inventory(target_origin=CREDENTIAL_URL)),
    (
        INVENTORY,
        "/candidates/0/url_key",
        inventory(candidates=[candidate(url_key=CREDENTIAL_URL)]),
    ),
    (
        INVENTORY,
        "/candidates/0/observed_forms/0",
        inventory(candidates=[candidate(observed_forms=[CREDENTIAL_URL])]),
    ),
]
CREDENTIAL_IDS = [pointer for _, pointer, _ in CREDENTIAL_SITES]


@pytest.mark.parametrize(("contract", "pointer", "document"), CREDENTIAL_SITES, ids=CREDENTIAL_IDS)
def test_a_credential_bearing_url_is_refused_wherever_a_url_appears(
    contract: str, pointer: str, document: dict[str, Any]
) -> None:
    assert (pointer, "pattern") in _keys(contract, document)


def test_a_credential_bearing_url_is_refused_in_a_selection_too() -> None:
    selections = [{"url_key": CREDENTIAL_URL, "selection_rank": 1, "selection_reason": "SEED"}]
    document = manifest(selections=selections)
    assert ("/selections/0/url_key", "pattern") in _keys(MANIFEST, document)


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
@pytest.mark.parametrize("fragment", TRANSIENT_FRAGMENTS)
def test_no_declared_member_persists_transient_or_rejected_input(
    contract: str, fragment: str
) -> None:
    """Raw anchor labels stay PXAPI-19.B input, and an arbitrary rejected URL string is never
    persisted merely so a digest can be recomputed."""
    offenders = sorted(name for name in _member_names(schema_of(contract)) if fragment in name)
    assert offenders == [], f"{contract} declares {offenders}"


@pytest.mark.parametrize(
    "member", ["anchor_label", "link_text", "rejected_urls", "raw_html", "discovered_labels"]
)
def test_an_added_transient_member_is_refused_by_the_closed_root(member: str) -> None:
    assert ("", "additionalProperties") in _keys(INVENTORY, inventory(**{member: "x"}))


# --- sampling semantics -----------------------------------------------------------------------


@pytest.mark.parametrize("mode", SAMPLING_MODES)
def test_each_declared_sampling_mode_is_representable(mode: str) -> None:
    assert _valid(MANIFEST, manifest(mode=mode))


@pytest.mark.parametrize(
    "token", ["census", "SAMPLE", "CRAWL4AI_DECIDED", "PROVIDER_CHOSEN", "AUTO", ""]
)
def test_a_mode_outside_the_closed_vocabulary_is_refused(token: str) -> None:
    assert ("/mode", "enum") in _keys(MANIFEST, manifest(mode=token))


@pytest.mark.parametrize("contract", CONTRACT_NAMES)
@pytest.mark.parametrize("fragment", DELEGATION_FRAGMENTS)
def test_no_declared_member_lets_a_provider_own_page_selection(
    contract: str, fragment: str
) -> None:
    """Selection is Pixelkiez methodology, and the census threshold is not invented here.

    The scan is over member names. ``PROVIDER_FAILURE`` deliberately remains a *source outcome*:
    it attributes a failure to a component, which is the opposite of handing that component a
    decision.
    """
    offenders = sorted(name for name in _member_names(schema_of(contract)) if fragment in name)
    assert offenders == [], f"{contract} declares {offenders}"


@pytest.mark.parametrize("fragment", DELEGATION_FRAGMENTS)
def test_no_selection_vocabulary_token_names_a_provider_or_a_threshold(fragment: str) -> None:
    schema = schema_of(MANIFEST)
    tokens = {token for vocabulary in _vocabularies(schema) for token in vocabulary}
    offenders = sorted(token for token in tokens if fragment.upper() in token)
    assert offenders == [], f"the sampling vocabularies declare {offenders}"


def test_no_numeric_threshold_is_declared_by_either_contract() -> None:
    """C-PXAPI-005 keeps the census-to-sampling threshold MISSING. The only numeric constant
    either contract declares is the zero that pins a non-admitting source's count."""
    for contract in CONTRACT_NAMES:
        constants = _numeric_constants(schema_of(contract))
        assert set(constants) <= {0}, f"{contract} declares numeric constant(s) {constants}"


def _numeric_constants(node: Any) -> list[Any]:
    found: list[Any] = []
    if isinstance(node, dict):
        for keyword in ("const", "enum"):
            value = node.get(keyword)
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, int) and not isinstance(item, bool):
                    found.append(item)
        for value in node.values():
            found.extend(_numeric_constants(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_numeric_constants(value))
    return found


def test_the_numeric_constant_scanner_sees_a_planted_number() -> None:
    assert _numeric_constants({"properties": {"n": {"const": 250}}}) == [250]
    assert _numeric_constants({"properties": {"n": {"minimum": 250}}}) == []


@pytest.mark.parametrize("member", ["policy_id", "policy_version", "selection_complete", "mode"])
def test_the_manifest_always_states_its_method_and_its_completeness(member: str) -> None:
    document = manifest()
    del document[member]
    assert ("", "required") in _keys(MANIFEST, document)
    assert member in schema_of(MANIFEST)["required"]


@pytest.mark.parametrize("value", [True, False])
def test_selection_complete_is_neutral_in_both_values(value: bool) -> None:
    assert _valid(MANIFEST, manifest(selection_complete=value))


@pytest.mark.parametrize("token", ["COMPLETE", "yes", 1, None])
def test_selection_complete_is_a_boolean_and_never_a_vocabulary(token: Any) -> None:
    assert ("/selection_complete", "type") in _keys(MANIFEST, manifest(selection_complete=token))


@pytest.mark.parametrize("reason", SELECTION_REASONS)
def test_each_declared_selection_reason_is_representable(reason: str) -> None:
    selections = [
        {"url_key": "https://example.com/", "selection_rank": 1, "selection_reason": reason}
    ]
    assert _valid(MANIFEST, manifest(selections=selections))


def test_a_manifest_that_selected_nothing_is_refused() -> None:
    assert ("/selections", "minItems") in _keys(MANIFEST, manifest(selections=[]))


@pytest.mark.parametrize("rank", [0, -1])
def test_a_selection_rank_below_one_is_refused(rank: int) -> None:
    """The rank carries the deterministic order, so it must be a real position."""
    selections = [
        {"url_key": "https://example.com/", "selection_rank": rank, "selection_reason": "SEED"}
    ]
    assert ("/selections/0/selection_rank", "minimum") in _keys(
        MANIFEST, manifest(selections=selections)
    )


def test_a_selection_may_not_grow_a_score_or_a_fetch_result() -> None:
    for member in ("score", "priority", "http_status", "raw_html"):
        selections = [
            {
                "url_key": "https://example.com/",
                "selection_rank": 1,
                "selection_reason": "SEED",
                member: 1,
            }
        ]
        assert ("/selections/0", "additionalProperties") in _keys(
            MANIFEST, manifest(selections=selections)
        ), member


def test_an_exclusion_summary_entry_must_account_for_at_least_one_candidate() -> None:
    """A reason that excluded nothing is noise, and a zero could be read as a claim."""
    exclusions = [{"reason": SELECTION_EXCLUSION_REASONS[0], "candidate_count": 0}]
    assert ("/exclusions/0/candidate_count", "minimum") in _keys(
        MANIFEST, manifest(exclusions=exclusions)
    )


def test_an_empty_exclusion_summary_is_valid_and_means_nothing_was_left_out() -> None:
    assert _valid(MANIFEST, manifest(exclusions=[]))


def test_a_declared_budget_is_a_whole_number_and_a_declared_budget_object_is_never_empty() -> None:
    assert ("/budgets", "minProperties") in _keys(MANIFEST, manifest(budgets={}))
    assert ("/budgets/max_selected_pages", "type") in _keys(
        MANIFEST, manifest(budgets={"max_selected_pages": 2.5})
    )
    assert ("/budgets", "additionalProperties") in _keys(
        MANIFEST, manifest(budgets={"max_seconds": 30})
    )


def test_a_manifest_with_no_declared_budget_is_valid() -> None:
    document = manifest()
    del document["budgets"]
    assert _valid(MANIFEST, document)


# --- the registered examples are coherent, not merely valid -----------------------------------


def test_every_source_admitted_count_matches_the_candidates_naming_it() -> None:
    """An example whose counts contradict its own provenance would document a rule nobody
    follows."""
    for document in examples_of(INVENTORY):
        named: dict[str, int] = {}
        for entry in document["candidates"]:
            for source_id in entry["provenance"]:
                named[source_id] = named.get(source_id, 0) + 1
        for entry in document["sources"]:
            expected = named.get(entry["source_id"], 0)
            assert entry["candidate_count"] == expected, (
                f"{document['inventory_id']}/{entry['source_id']}: states "
                f"{entry['candidate_count']}, provenance shows {expected}"
            )


def test_every_registered_manifest_accounts_for_every_candidate_of_its_inventory() -> None:
    """Selections plus the exclusion summary account for the whole bound population."""
    populations = {
        document["inventory_id"]: len(document["candidates"]) for document in examples_of(INVENTORY)
    }
    for document in examples_of(MANIFEST):
        accounted = len(document["selections"]) + sum(
            entry["candidate_count"] for entry in document["exclusions"]
        )
        expected = populations[document["inventory_ref"]]
        assert accounted == expected, (
            f"{document['sampling_manifest_id']}: accounts for {accounted} of {expected}"
        )


def test_every_registered_manifest_selects_only_identities_its_inventory_carries() -> None:
    keys_by_inventory = {
        document["inventory_id"]: {entry["url_key"] for entry in document["candidates"]}
        for document in examples_of(INVENTORY)
    }
    for document in examples_of(MANIFEST):
        available = keys_by_inventory[document["inventory_ref"]]
        selected = {entry["url_key"] for entry in document["selections"]}
        assert selected <= available, (
            f"{document['sampling_manifest_id']}: selects {sorted(selected - available)}"
        )


def test_selection_ranks_are_dense_and_ascending_in_every_registered_manifest() -> None:
    """The rank is the order authority, so the ranks of one manifest must be a real sequence."""
    for document in examples_of(MANIFEST):
        ranks = [entry["selection_rank"] for entry in document["selections"]]
        assert ranks == sorted(ranks), document["sampling_manifest_id"]
        assert ranks == list(range(1, len(ranks) + 1)), document["sampling_manifest_id"]


def test_a_census_manifest_never_records_a_stratum_quota_selection() -> None:
    """Coherence between the mode and the reasons, over the registered examples: the contracts
    fix the two vocabularies and JSON Schema cannot couple a root member to an array item, so
    this is a producer rule proved here rather than a schema constraint."""
    for document in examples_of(MANIFEST):
        reasons = {entry["selection_reason"] for entry in document["selections"]}
        if document["mode"] == "CENSUS":
            assert "STRATUM_QUOTA" not in reasons, document["sampling_manifest_id"]
        else:
            assert "CENSUS" not in reasons, document["sampling_manifest_id"]


def test_the_shared_lexical_block_references_its_own_defs_by_absolute_uri() -> None:
    """A relative ``#/$defs/...`` in a shared file resolves against whichever schema embeds it,
    which is the trap PXK-61 hit; every internal reference here is a full URI."""
    schema = load_json(CONTRACTS.schema_path(SHARED))
    relative = sorted(ref for ref in _refs(schema) if ref.startswith("#"))
    assert relative == [], f"{SHARED} uses relative internal reference(s) {relative}"
    assert _refs(schema), "canary: the shared block declares no reference at all"
