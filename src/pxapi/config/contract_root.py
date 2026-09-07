"""Where the contract registry lives on disk.

The registry is data shipped beside the package rather than inside it, so its location is a
configuration fact and not a package constant. ``PXAPI_CONTRACTS_DIR`` overrides it, which is
what lets a test point the runtime at a throwaway registry without touching the real one.

Config is a leaf layer: this module imports no other ``pxapi`` layer and no third party.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The environment variable that overrides the location of the contract root.
CONTRACT_ROOT_ENV = "PXAPI_CONTRACTS_DIR"

#: Repository layout: ``<repo>/src/pxapi/config/contract_root.py`` -> ``<repo>/contracts/v1``.
_REPO_RELATIVE = Path(__file__).resolve().parents[3] / "contracts" / "v1"


def contract_root() -> Path:
    """The directory holding ``manifest.json``.

    Reads the environment on every call rather than caching at import time, so a test that
    sets the variable does not depend on having been imported first.
    """
    override = os.environ.get(CONTRACT_ROOT_ENV)
    return Path(override) if override else _REPO_RELATIVE
