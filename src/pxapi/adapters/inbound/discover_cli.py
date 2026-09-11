"""The operator entry point for site discovery: one URL in, the canonical documents out.

It exists so a real discovery can be run and read back without standing up a server, which is
what the PXAPI-19 Real-Boundary-Smoke needs. It drives the same use case through the same
composition root under the same strict target policy as every other entry point, and it
validates every document the run produced against the contract registry before printing any:
a document this service built that fails its own contract is withheld and reported as
``CANONICAL_OUTPUT_INVALID``, which names a defect in this service and never the website.

Run it as ``python -m pxapi.adapters.inbound.discover_cli <url>``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from pxapi.adapters.composition import build_site_discovery, default_registry
from pxapi.adapters.contracts.registry import ContractRegistry
from pxapi.adapters.inbound.cli import REQUEST_CONTRACT, build_request
from pxapi.domain.site_identity import UrlRefusal, refuse

#: ``envelope member -> the contract every document under it must satisfy``. A list member is
#: checked item by item.
PRODUCED_DOCUMENTS: dict[str, str] = {
    "analysis_run_state": "analysis-run-state",
    "stage_executions": "stage-execution-record",
    "site_inventory": "site-inventory",
    "sampling_manifest": "sampling-manifest",
}


def invalid_documents(registry: ContractRegistry, envelope: dict[str, Any]) -> list[str]:
    """The contract name of every produced document that fails its contract."""
    failures: list[str] = []
    for member, contract in PRODUCED_DOCUMENTS.items():
        if member not in envelope:
            continue
        value = envelope[member]
        documents = value if isinstance(value, list) else [value]
        failures += [contract for document in documents if registry.validate(contract, document)]
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pxapi-discover",
        description="Discover one public site's page population and plan its census.",
    )
    parser.add_argument("url", help="an absolute public http(s) URL")
    arguments = parser.parse_args(argv)

    if refuse(arguments.url) is UrlRefusal.CREDENTIALS_PRESENT:
        # Refused before a request document exists, so the credential is never echoed into
        # one, onto stdout, or into a log that captures it. The run would refuse it anyway.
        sys.stderr.write(
            "pxapi-discover: a target carrying credentials in its authority is refused.\n"
        )
        return 2

    registry = default_registry()
    request = build_request(arguments.url)
    found = registry.validate(REQUEST_CONTRACT, request)
    if found:
        json.dump(registry.to_problem(REQUEST_CONTRACT, found), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2

    envelope = build_site_discovery().run(request)
    if invalid_documents(registry, envelope):
        problem = registry.problem(
            "CANONICAL_OUTPUT_INVALID",
            "Canonical output invalid",
            "A document this service produced does not satisfy its contract and was withheld.",
            run_id=request["run_id"],
        )
        json.dump(problem, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 3

    json.dump(envelope, sys.stdout, indent=2)
    sys.stdout.write("\n")
    # A run that failed technically is still a correctly produced analysis result, so the exit
    # status reports whether the command worked, never what the website is like.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
