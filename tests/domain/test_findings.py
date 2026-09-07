"""The three authorised rules: when each fires, and what each is allowed to say.

Two properties are proven here and nowhere else.

**The trigger is a decision about one measured value, and nothing else.** A status of 399 is not
an error and 400 is; a transport observed as HTTPS is not a finding and one observed as plain
HTTP is. Each boundary is asserted from both sides, because a threshold only tested from the
firing side is a threshold that could be anything at all.

**The product texts are fixed per rule version.** They are constants, never templates: the
measured value does not appear in them, and there is no placeholder through which it could. The
behavioural half of that proof — that a 418 and a 503 produce byte-identical texts once real
measurements have flowed through the derivation — lives in the application tests, because that
is where a value would have to leak in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pxapi.domain.findings import (
    RULES,
    FindingClass,
    FindingRule,
    RuleId,
)
from pxapi.domain.observations import Metric

#: The pinned evaluation order. The envelope lists findings in this order, so it is a stated
#: fact rather than whatever the rules happen to be declared in.
EXPECTED_ORDER = (
    RuleId.HTTP_ERROR_RESPONSE,
    RuleId.NON_HTTPS_FINAL_TRANSPORT,
    RuleId.MISSING_HOMEPAGE_TITLE,
)

#: The decisive metric each rule reads. A rule that read a different one would be a different
#: rule, so the binding is pinned rather than inferred from whichever metric happens to exist.
EXPECTED_METRIC = {
    RuleId.HTTP_ERROR_RESPONSE: Metric.HTTP_STATUS,
    RuleId.NON_HTTPS_FINAL_TRANSPORT: Metric.TRANSPORT_IS_HTTPS,
    RuleId.MISSING_HOMEPAGE_TITLE: Metric.PAGE_TITLE_PRESENT,
}

EXPECTED_CLASS = {
    RuleId.HTTP_ERROR_RESPONSE: FindingClass.HOMEPAGE_HTTP_ERROR_STATUS,
    RuleId.NON_HTTPS_FINAL_TRANSPORT: FindingClass.HOMEPAGE_FINAL_TRANSPORT_NOT_HTTPS,
    RuleId.MISSING_HOMEPAGE_TITLE: FindingClass.HOMEPAGE_TITLE_MISSING,
}

#: The exact v1 texts, quoted rather than derived. A wording change is a rule version change,
#: and this is where that becomes a decision instead of an edit.
EXPECTED_TEXTS: dict[RuleId, tuple[str, str, str, str]] = {
    RuleId.HTTP_ERROR_RESPONSE: (
        "The analysis client received an HTTP status of 400 or above for the analysed homepage.",
        "A client receiving this response may not receive the intended homepage content; the "
        "effect on real users depends on access, edge, bot and rate-limit policies that were "
        "not assessed.",
        "Review the homepage response path and access or edge configuration. Treat statuses "
        "such as 401, 403 and 429 as potentially intentional or client-specific before "
        "changing site behaviour.",
        "This single automated-client response does not prove that the website is generally "
        "unavailable, that users cannot access it, or that a historical outage occurred.",
    ),
    RuleId.NON_HTTPS_FINAL_TRANSPORT: (
        "The analysed homepage's final response was observed over HTTP rather than HTTPS.",
        "Serving the homepage without HTTPS removes TLS transport protection for that response "
        "and can trigger browser security indicators.",
        "Serve the public homepage over HTTPS and redirect the HTTP entry point to an HTTPS "
        "final response.",
        "This observation covers only the analysed homepage response and does not establish the "
        "TLS configuration, certificate quality or security posture of the entire site.",
    ),
    RuleId.MISSING_HOMEPAGE_TITLE: (
        "No homepage title was observed in the analysed HTML response.",
        "A missing title removes an explicit page-level label used by browsers and search "
        "systems, which can reduce clarity in tabs and search presentation.",
        "Add a concise, page-specific HTML title that accurately identifies the homepage.",
        "This finding covers only the analysed homepage response and does not by itself "
        "establish search ranking, search visibility or site-wide SEO quality.",
    ),
}


def rule(rule_id: RuleId) -> FindingRule:
    return next(candidate for candidate in RULES if candidate.rule_id == rule_id)


def integer(value: int) -> dict[str, Any]:
    return {"value_type": "INTEGER", "integer_value": value}


def boolean(value: bool) -> dict[str, Any]:
    return {"value_type": "BOOLEAN", "boolean_value": value}


# --- the rule set itself ---------------------------------------------------------------------


def test_the_rule_set_is_exactly_the_three_authorised_rules_in_the_pinned_order() -> None:
    assert tuple(candidate.rule_id for candidate in RULES) == EXPECTED_ORDER


@pytest.mark.parametrize("rule_id", EXPECTED_ORDER, ids=list(EXPECTED_ORDER))
def test_each_rule_names_its_class_its_version_and_the_metric_it_decides_on(
    rule_id: RuleId,
) -> None:
    found = rule(rule_id)
    assert found.finding_class == EXPECTED_CLASS[rule_id]
    assert found.rule_version == "1.0.0"
    assert found.metric == EXPECTED_METRIC[rule_id]


# --- the fixed product texts -----------------------------------------------------------------


@pytest.mark.parametrize("rule_id", EXPECTED_ORDER, ids=list(EXPECTED_ORDER))
def test_each_rule_carries_exactly_the_v1_texts(rule_id: RuleId) -> None:
    found = rule(rule_id)
    summary, impact, action, limitation = EXPECTED_TEXTS[rule_id]
    assert found.finding_summary == summary
    assert found.business_impact == impact
    assert found.recommended_action == action
    assert found.limitation == limitation


#: Fragments through which a measured value could reach a product text. A text carrying one is
#: a template, and a template is how "status 418" ends up in prose no contract validates.
PLACEHOLDERS = ("{", "}", "%s", "%d", "%(", "$")


@pytest.mark.parametrize("rule_id", EXPECTED_ORDER, ids=list(EXPECTED_ORDER))
def test_no_product_text_is_a_template(rule_id: RuleId) -> None:
    found = rule(rule_id)
    for text in (
        found.finding_summary,
        found.business_impact,
        found.recommended_action,
        found.limitation,
    ):
        for placeholder in PLACEHOLDERS:
            assert placeholder not in text, f"{rule_id}: {placeholder!r} in {text!r}"


@pytest.mark.parametrize("rule_id", EXPECTED_ORDER, ids=list(EXPECTED_ORDER))
def test_every_rule_states_what_it_does_not_establish(rule_id: RuleId) -> None:
    """The bound is not decoration: it is the member that stops one page becoming a verdict."""
    assert rule(rule_id).limitation.strip()


# --- R1: the HTTP error threshold, from both sides -------------------------------------------

R1 = RuleId.HTTP_ERROR_RESPONSE

#: Statuses below the threshold. None of them is an error, and a redirect least of all.
R1_QUIET = [100, 200, 204, 301, 302, 304, 399]

#: Statuses at or above it, including the two the no-interpolation proof uses.
R1_FIRING = [400, 401, 403, 404, 418, 429, 500, 503, 599]


@pytest.mark.parametrize("status", R1_QUIET)
def test_a_status_below_the_error_threshold_does_not_fire_r1(status: int) -> None:
    assert rule(R1).triggers(integer(status)) is False


@pytest.mark.parametrize("status", R1_FIRING)
def test_a_status_at_or_above_the_error_threshold_fires_r1(status: int) -> None:
    assert rule(R1).triggers(integer(status)) is True


def test_the_r1_threshold_is_inclusive_at_four_hundred() -> None:
    """The one boundary the whole rule turns on, asserted as a pair rather than a single case."""
    assert rule(R1).triggers(integer(399)) is False
    assert rule(R1).triggers(integer(400)) is True


def test_r1_reads_only_an_integer_status() -> None:
    """A value of another type is not a low status: it is no status at all."""
    assert rule(R1).triggers(boolean(True)) is False
    assert rule(R1).triggers({"value_type": "TEXT", "text_value": "503"}) is False
    assert rule(R1).triggers({"value_type": "INTEGER"}) is False
    assert rule(R1).triggers({}) is False


def test_a_boolean_true_is_not_read_as_an_integer_status() -> None:
    """``bool`` is a subclass of ``int`` in Python, so this has to be refused explicitly."""
    assert rule(R1).triggers({"value_type": "INTEGER", "integer_value": True}) is False


# --- R2: the transport, from both sides ------------------------------------------------------

R2 = RuleId.NON_HTTPS_FINAL_TRANSPORT


def test_a_transport_observed_as_https_does_not_fire_r2() -> None:
    assert rule(R2).triggers(boolean(True)) is False


def test_a_transport_observed_as_plain_http_fires_r2() -> None:
    assert rule(R2).triggers(boolean(False)) is True


def test_r2_reads_only_a_boolean_transport() -> None:
    assert rule(R2).triggers(integer(0)) is False
    assert rule(R2).triggers({"value_type": "TEXT", "text_value": "false"}) is False
    assert rule(R2).triggers({"value_type": "BOOLEAN"}) is False
    assert rule(R2).triggers({}) is False


# --- R3: the title, from both sides ----------------------------------------------------------

R3 = RuleId.MISSING_HOMEPAGE_TITLE


def test_a_title_observed_as_present_does_not_fire_r3() -> None:
    assert rule(R3).triggers(boolean(True)) is False


def test_a_title_observed_as_absent_fires_r3() -> None:
    assert rule(R3).triggers(boolean(False)) is True


def test_r3_reads_only_a_boolean_presence() -> None:
    assert rule(R3).triggers(integer(0)) is False
    assert rule(R3).triggers({"value_type": "TEXT", "text_value": ""}) is False
    assert rule(R3).triggers({"value_type": "BOOLEAN"}) is False
    assert rule(R3).triggers({}) is False


# --- the domain ring stays a domain ring -----------------------------------------------------


def test_the_rules_are_pure_data_and_hold_no_transport_or_validator() -> None:
    """Canary for the layer rule the architecture test enforces from the outside."""
    import pxapi.domain.findings as module

    source = module.__file__
    assert source is not None
    text = Path(source).read_text(encoding="utf-8")
    for forbidden in ("import jsonschema", "import fastapi", "import requests", "urllib.request"):
        assert forbidden not in text, forbidden
