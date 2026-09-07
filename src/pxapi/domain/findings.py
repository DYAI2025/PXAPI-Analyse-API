"""The three authorised diagnostic rules: what fires, and what each is allowed to say.

A rule is a decision about **one** measured value, plus four fixed texts. Keeping those two
things in one small, pure object is what makes the slice's central rule checkable rather than
intended:

* **The texts are constants, not templates.** A measured value never reaches prose. Two runs
  that observed 418 and 503 carry byte-identical texts, because there is no place in this
  module where a value could be interpolated into one. The number stays in the measurement
  record, which is contract-validated, instead of leaking into free text that nothing validates.
* **A trigger reads a value that was actually established.** Every predicate here is handed the
  ``result`` block of a measurement whose assessment already said ``KNOWN``; whether it *was*
  known is the caller's decision and deliberately not re-litigated here. What this module does
  refuse is a value of the wrong shape: a boolean is not a status, a text "503" is not a status,
  and a missing member is not a low one.

Absence of a finding means only that these rules emitted none. It never means the site is good,
complete or fully assessed — a statement each rule also carries in its own ``limitation``.

Standard library only. The domain ring imports no third-party distribution at all.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from pxapi.domain.observations import Metric


class RuleId(StrEnum):
    """The rules this slice implements. Values are ``code`` tokens: upper snake case.

    The contract holds ``rule_id`` open, so this enum names the set for this slice without any
    contract changing — exactly as ``Metric`` does for ``metric_id``.
    """

    #: The analysis client received an HTTP status at or above the error threshold.
    HTTP_ERROR_RESPONSE = "HTTP_ERROR_RESPONSE"
    #: The final response arrived over plain HTTP rather than HTTPS.
    NON_HTTPS_FINAL_TRANSPORT = "NON_HTTPS_FINAL_TRANSPORT"
    #: The document declared no title.
    MISSING_HOMEPAGE_TITLE = "MISSING_HOMEPAGE_TITLE"


class FindingClass(StrEnum):
    """What kind of finding was emitted. A classification, and deliberately not a severity."""

    HOMEPAGE_HTTP_ERROR_STATUS = "HOMEPAGE_HTTP_ERROR_STATUS"
    HOMEPAGE_FINAL_TRANSPORT_NOT_HTTPS = "HOMEPAGE_FINAL_TRANSPORT_NOT_HTTPS"
    HOMEPAGE_TITLE_MISSING = "HOMEPAGE_TITLE_MISSING"


#: The version of every rule in this module. A rule whose trigger condition or whose texts
#: change is a new version of that rule, so two findings are comparable only when this agrees.
RULE_VERSION: Final = "1.0.0"

#: The status at and above which a response is an error. Stated once, and inclusive: 400 is an
#: error and 399 is not. The boundary is the whole of R1, so it is a named fact rather than a
#: literal inside a predicate.
HTTP_ERROR_THRESHOLD: Final = 400


def _integer_value(result: Mapping[str, Any]) -> int | None:
    """The integer a KNOWN result carries, or ``None`` when it carries something else.

    ``bool`` is a subclass of ``int`` in Python, so a JSON ``true`` would otherwise satisfy a
    numeric comparison. It is refused explicitly rather than left to arithmetic.
    """
    if result.get("value_type") != "INTEGER":
        return None
    value = result.get("integer_value")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _boolean_value(result: Mapping[str, Any]) -> bool | None:
    """The boolean a KNOWN result carries, or ``None`` when it carries something else."""
    if result.get("value_type") != "BOOLEAN":
        return None
    value = result.get("boolean_value")
    return value if isinstance(value, bool) else None


def observed_http_error(result: Mapping[str, Any]) -> bool:
    """The status was established and is at or above the error threshold."""
    status = _integer_value(result)
    return status is not None and status >= HTTP_ERROR_THRESHOLD


def observed_transport_not_https(result: Mapping[str, Any]) -> bool:
    """The transport was established and is not HTTPS.

    ``is False`` rather than ``not value``: a result that established nothing arrives here as
    ``None``, and "we do not know" must never be read as "it was plain HTTP".
    """
    return _boolean_value(result) is False


def observed_title_absent(result: Mapping[str, Any]) -> bool:
    """Title presence was established and the title is absent.

    Same rule as the transport, for the same reason: ``UNKNOWN`` never becomes an absence, and
    a title too long for the contract to carry is still a title that is *present*.
    """
    return _boolean_value(result) is False


@dataclass(frozen=True)
class FindingRule:
    """One rule: the value it decides on, and the four fixed texts it emits.

    The texts are fields rather than methods on purpose. There is no formatting step anywhere
    in this object, so there is no seam through which a measured value could enter them.
    """

    rule_id: RuleId
    rule_version: str
    finding_class: FindingClass
    #: The metric whose measurement record decides this rule. A rule reading another metric
    #: would be another rule.
    metric: Metric
    #: Decides on the ``result`` block of a KNOWN measurement of ``metric``.
    triggers: Callable[[Mapping[str, Any]], bool]
    finding_summary: str
    business_impact: str
    recommended_action: str
    limitation: str


#: The rules, in the order findings are emitted. The order is pinned here and asserted in the
#: tests, so two runs over the same evidence produce the same sequence.
RULES: Final[tuple[FindingRule, ...]] = (
    FindingRule(
        rule_id=RuleId.HTTP_ERROR_RESPONSE,
        rule_version=RULE_VERSION,
        finding_class=FindingClass.HOMEPAGE_HTTP_ERROR_STATUS,
        metric=Metric.HTTP_STATUS,
        triggers=observed_http_error,
        finding_summary=(
            "The analysis client received an HTTP status of 400 or above for the analysed homepage."
        ),
        business_impact=(
            "A client receiving this response may not receive the intended homepage content; "
            "the effect on real users depends on access, edge, bot and rate-limit policies "
            "that were not assessed."
        ),
        recommended_action=(
            "Review the homepage response path and access or edge configuration. Treat "
            "statuses such as 401, 403 and 429 as potentially intentional or client-specific "
            "before changing site behaviour."
        ),
        limitation=(
            "This single automated-client response does not prove that the website is "
            "generally unavailable, that users cannot access it, or that a historical outage "
            "occurred."
        ),
    ),
    FindingRule(
        rule_id=RuleId.NON_HTTPS_FINAL_TRANSPORT,
        rule_version=RULE_VERSION,
        finding_class=FindingClass.HOMEPAGE_FINAL_TRANSPORT_NOT_HTTPS,
        metric=Metric.TRANSPORT_IS_HTTPS,
        triggers=observed_transport_not_https,
        finding_summary=(
            "The analysed homepage's final response was observed over HTTP rather than HTTPS."
        ),
        business_impact=(
            "Serving the homepage without HTTPS removes TLS transport protection for that "
            "response and can trigger browser security indicators."
        ),
        recommended_action=(
            "Serve the public homepage over HTTPS and redirect the HTTP entry point to an "
            "HTTPS final response."
        ),
        limitation=(
            "This observation covers only the analysed homepage response and does not "
            "establish the TLS configuration, certificate quality or security posture of the "
            "entire site."
        ),
    ),
    FindingRule(
        rule_id=RuleId.MISSING_HOMEPAGE_TITLE,
        rule_version=RULE_VERSION,
        finding_class=FindingClass.HOMEPAGE_TITLE_MISSING,
        metric=Metric.PAGE_TITLE_PRESENT,
        triggers=observed_title_absent,
        finding_summary="No homepage title was observed in the analysed HTML response.",
        business_impact=(
            "A missing title removes an explicit page-level label used by browsers and search "
            "systems, which can reduce clarity in tabs and search presentation."
        ),
        recommended_action=(
            "Add a concise, page-specific HTML title that accurately identifies the homepage."
        ),
        limitation=(
            "This finding covers only the analysed homepage response and does not by itself "
            "establish search ranking, search visibility or site-wide SEO quality."
        ),
    ),
)
