"""The operator entry point: analyse one URL and print the canonical documents.

It exists so a real analysis can be run and read back without standing up a server, which is
what the real-boundary smoke needs. It drives the same use case, through the same composition
root, under the same strict target policy as the HTTP endpoint: the command line is a different
way in, never a different set of rules.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from pxapi.adapters.composition import (
    SUPPORTED_SCAN_MODE,
    build_analyzer,
    default_registry,
    new_identifier,
    utc_now,
)

REQUEST_CONTRACT = "analysis-run-request"


def build_request(url: str) -> dict:
    """The request document for one homepage analysis."""
    return {
        "schema_version": "1.0.0",
        "run_id": new_identifier(),
        "request_id": new_identifier(),
        "requested_at": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_url": url,
        "scan_mode": SUPPORTED_SCAN_MODE,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pxapi-analyze",
        description="Analyse one public homepage and print the canonical analysis documents.",
    )
    parser.add_argument("url", help="an absolute public http(s) URL")
    arguments = parser.parse_args(argv)

    registry = default_registry()
    request = build_request(arguments.url)

    # The command line submits a document to the same contract the endpoint enforces, so a
    # malformed URL is refused by the contract rather than by a second, weaker check here.
    found = registry.validate(REQUEST_CONTRACT, request)
    if found:
        json.dump(registry.to_problem(REQUEST_CONTRACT, found), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2

    envelope = build_analyzer(registry).run(request)
    json.dump(envelope, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")

    # A run that failed technically is still a successfully produced analysis document, so the
    # exit status reports whether the command worked, not what the website is like.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
