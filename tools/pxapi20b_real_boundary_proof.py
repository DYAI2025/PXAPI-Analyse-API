"""PXAPI-20.B real-boundary proof harness: one locked multi-page acquisition, checked end to end.

Run it with any Python 3.11+ *control* interpreter from a fresh exact-SHA checkout::

    python tools/pxapi20b_real_boundary_proof.py [--expected-sha SHA]

It uses the standard library only and changes nothing on the host. It

1. records the checkout's exact ``HEAD`` SHA, refuses a checkout with tracked modifications,
   refuses untracked entries under ``src`` or ``contracts`` and refuses any checkout-root entry
   named ``pxapi`` or ``pxapi.<ext>`` — the shapes under which untracked content could be
   imported in place of the tracked package (:data:`UNTRACKED_FORBIDDEN`, :data:`SHADOW_NAME`);
2. locates ``uv`` on ``PATH``, else beside ``sys.executable`` or, for a control interpreter under
   ``<home>/.agt-runner/``, in ``<home>/.local/bin`` — read off the interpreter path, not ``HOME``;
3. selects an already installed system Python — 3.14 preferred, else 3.13 — that satisfies the
   checkout's ``requires-python``, with downloads, uv-managed Pythons, ``.python-version`` and
   project or user uv configuration all excluded from discovery; each ``uv python find`` sees the
   inherited ``PATH`` followed by the existing well-known system and package-manager interpreter
   directories for that minor (:data:`WELL_KNOWN_PYTHON_DIRS`), so a sandbox ``PATH`` that omits
   e.g. Homebrew's ``/opt/homebrew/opt/python@3.13/bin`` still lets uv resolve the installed
   interpreter — which is then probed and checked like any other candidate;
4. builds a disposable project environment under ``TMPDIR`` with ``uv sync --locked`` against
   the checkout's own ``pyproject.toml`` and ``uv.lock``, and proves ``uv.lock`` is byte-identical
   afterwards;
5. runs every Python it invokes — interpreter probes, the production command line and the
   verifier below — in isolated mode (``-I``: no ``PYTHON*`` variable, no user site, no script or
   working directory on ``sys.path``) from an empty scratch working directory, never from the
   checkout root, so nothing outside the locked installation can be imported;
6. runs the production command line as the project-runtime Python against the controlled origin
   with an explicit ``--max-selected-pages 3`` and a fresh canonical output directory, trusting
   the locked ``certifi`` bundle;
7. runs a second, independent consumer of the written bundle in the same locked runtime
   (:data:`CONTRACT_VERIFIER`): it reports where the ``pxapi`` package it imported actually lives
   — which must be the tracked ``src/pxapi`` of the checkout or the disposable environment —
   validates every canonical document against its registered contract in the checkout's own
   ``contracts/v1`` and applies the ``PageAcquisitionRecord`` producer invariants to what it read
   back. It does not read the command line's receipt;
8. re-derives, in this control interpreter and with the standard library alone, everything the
   bundle claims about itself: the semantic SHA-256 digests and counts of the page documents,
   the site inventory's ``output_digest``, the sampling manifest's ``input_digest`` and
   ``output_digest``, the complete page-scoped cardinality (selection → acquisition →
   measurement → evidence) and every receipt member derivable from the canonical documents, and
   compares each recomputed value with the documents and with ``receipt.json``. The inventory's
   ``input_digest`` is not reconstructible from the published bundle; only its shape is checked.

Everything lands under the fixed, untracked :data:`PROOF_DIR` of the checkout: the canonical
JSON artifacts in ``canonical/`` and ``proof-receipt.json`` beside them. Any bootstrap, runtime,
isolation, boundary, contract, linkage or artifact failure is recorded in the receipt and exits
nonzero; a malformed bundle is reported as problems, never raised.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Mapping, Sequence
from operator import itemgetter
from pathlib import Path
from typing import Any

TARGET = "https://www.rfc-editor.org/"
MAX_SELECTED_PAGES = 3
MIN_PAGES = 2
#: Installed system Pythons tried in this order (D-20-L prefers 3.14); each must also satisfy
#: the checkout's ``requires-python``.
PREFERRED_PYTHONS = ((3, 14), (3, 13))
#: Every ``uv python`` / ``uv sync`` call: only system Pythons, never a download.
NO_MANAGED = ("--python-preference", "only-system", "--no-python-downloads")
#: Every ``uv python find``: installed system Pythons only, never a download, a virtual
#: environment, a ``.python-version`` pin or any project or user uv configuration.
SYSTEM_FIND = (
    "--no-config",
    "--no-project",
    "--system",
    "--no-managed-python",
    "--no-python-downloads",
)
#: The ``uv python dir`` managed-root probe, independent of project or user uv configuration.
MANAGED_DIR = ("--no-config",)
#: Host variables that name, rank, configure or relocate an interpreter; ``uv python dir`` and
#: ``uv python find`` run without them so :data:`MANAGED_DIR` and :data:`SYSTEM_FIND` alone
#: decide (``UV_PYTHON_PREFERENCE`` would also collide with ``--no-managed-python``).
DISCOVERY_DROPPED = frozenset(
    {
        "UV_PYTHON",
        "UV_PYTHON_PREFERENCE",
        "UV_MANAGED_PYTHON",
        "UV_NO_MANAGED_PYTHON",
        "UV_CONFIG_FILE",
        "UV_PROJECT",
        "UV_PYTHON_INSTALL_DIR",
    }
)
#: Well-known interpreter directories per platform, in lookup order, appended to the inherited
#: ``PATH`` of one ``uv python find`` when they exist. ``{minor}`` is the requested ``X.Y`` and
#: ``{compact}`` its ``XY`` form. Fixed system and package-manager locations only: nothing under
#: the user's home, nothing uv-managed, no project environment, no pin or uv setting.
WELL_KNOWN_PYTHON_DIRS: dict[str, tuple[str, ...]] = {
    "darwin": (
        "/opt/homebrew/opt/python@{minor}/bin",
        "/usr/local/opt/python@{minor}/bin",
        "/Library/Frameworks/Python.framework/Versions/{minor}/bin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/opt/local/bin",
        "/usr/bin",
    ),
    "win32": ("C:\\Program Files\\Python{compact}", "C:\\Python{compact}"),
    "posix": ("/usr/local/bin", "/usr/bin", "/bin"),
}
PROOF_DIR = Path(".proof-output") / "pxapi20b-real-boundary"
CANONICAL_DIR = "canonical"
PROOF_RECEIPT = "proof-receipt.json"
CLI_MODULE = "pxapi.adapters.inbound.acquire_cli"
COMMAND_TIMEOUT_SECONDS = 1_800
#: The Agent-team runner's directory directly under the real user home.
RUNNER_DIR = ".agt-runner"
#: Every Python this harness runs is started in isolated mode: ``PYTHON*`` variables ignored,
#: user site disabled, and neither the script directory nor the working directory on ``sys.path``
#: (``-I`` implies ``-P`` since 3.11). Deleting ``PYTHONPATH`` alone would leave the working
#: directory importable.
ISOLATED_FLAGS = ("-I",)
#: Checkout directories under which no untracked entry may exist: ``src`` is on the locked
#: environment's ``sys.path`` through the editable installation, and ``contracts`` is the
#: registry the runtime validates against. An untracked package directory beside a tracked
#: module, or an untracked ``sitecustomize.py``, would be imported in place of tracked content.
UNTRACKED_FORBIDDEN = ("src", "contracts")
#: A checkout-root entry with this name, or ``<name>.<ext>``, is an importable shadow of the
#: tracked package for any interpreter whose ``sys.path`` holds the checkout root.
SHADOW_NAME = "pxapi"
#: The checkout's contract registry, the only one the runtime and the verifier may read.
CONTRACT_ROOT = Path("contracts") / "v1"
#: The tracked package the locked environment installs.
TRACKED_PACKAGE = Path("src") / "pxapi"

#: ``envelope member -> canonical file``; mirrors ``acquire_cli.PRODUCED_DOCUMENTS``, which this
#: control-runtime harness cannot import. A unit test keeps the two identical.
CANONICAL_FILES: dict[str, str] = {
    "analysis_run_request": "analysis-run-request.json",
    "analysis_run_state": "analysis-run-state.json",
    "stage_executions": "stage-execution-records.json",
    "site_inventory": "site-inventory.json",
    "sampling_manifest": "sampling-manifest.json",
    "page_acquisitions": "page-acquisition-records.json",
    "measurements": "measurement-records.json",
    "website_evidence": "website-evidence.json",
}
#: ``envelope member -> registered contract``; mirrors ``acquire_cli.PRODUCED_DOCUMENTS`` too,
#: and is what the verifier validates each file against. Pinned by the same unit test.
CANONICAL_CONTRACTS: dict[str, str] = {
    "analysis_run_request": "analysis-run-request",
    "analysis_run_state": "analysis-run-state",
    "stage_executions": "stage-execution-record",
    "site_inventory": "site-inventory",
    "sampling_manifest": "sampling-manifest",
    "page_acquisitions": "page-acquisition-record",
    "measurements": "measurement-record",
    "website_evidence": "website-evidence",
}
CLI_RECEIPT = "receipt.json"
LIST_MEMBERS = frozenset(
    {"stage_executions", "page_acquisitions", "measurements", "website_evidence"}
)
#: The page-scoped documents whose semantic digests and counts ``receipt.json`` states.
PAGE_MEMBERS = ("page_acquisitions", "measurements", "website_evidence")

#: The canonical JSON rendering every PXAPI digest is computed over, and the digest projections
#: of the two acquisition contracts — restated from ``pxapi.domain.acquisition_digests`` so this
#: control interpreter recomputes each value without the product package. A unit test keeps the
#: options, the member classes and the resulting digests identical to the shipped producer's.
CANONICAL_JSON: dict[str, Any] = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}
INVENTORY_OUTPUT = (
    "target_origin",
    "discovery_method",
    "discovery_method_version",
    "classifier",
    "classifier_version",
    "sources",
    "candidates",
)
MANIFEST_INPUT = (
    "inventory_ref",
    "inventory_output_digest",
    "policy_id",
    "policy_version",
    "budgets",
)
MANIFEST_OUTPUT = ("mode", "selection_complete", "incompleteness", "selections", "exclusions")
#: ``acquisition#/$defs/digest``, as the contract writes it.
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")

EVIDENCE_CEILING = (
    "One bounded, explicitly budgeted selection of one controlled public origin was acquired "
    "over static HTTP into valid, linked, page-scoped canonical documents. This does not prove "
    "complete site coverage (selection_complete is the only coverage statement), browser "
    "rendering, scoring validity, PDF readiness, production scale or customer value."
)

#: Printed by every interpreter this harness inspects; parsed as one JSON line.
PROBE = (
    "import json, platform, sys; print(json.dumps({'executable': sys.executable, "
    "'prefix': sys.prefix, 'version': platform.python_version(), "
    "'version_info': list(sys.version_info[:3])}))"
)
CERTIFI_PROBE = "import certifi; print(certifi.where())"

#: The second consumer of the bundle, run as the locked project runtime with ``-I`` from the
#: scratch working directory. It receives one JSON argument (:func:`verifier_spec`), imports the
#: product package and prints one JSON report: where ``pxapi`` was imported from, the runtime's
#: contract root, whether isolation was in force, every contract violation of every canonical
#: document against the checkout's registry, and every acquisition producer-invariant violation
#: over the documents as read back. It never raises on a malformed document: unreadable files
#: and misshapen containers are reported as problems. It reads no receipt.
CONTRACT_VERIFIER = """\
import json
import os
import sys
from pathlib import Path

import pxapi
from pxapi.adapters.contracts.registry import ContractRegistry, loads_json
from pxapi.config.contract_root import contract_root
from pxapi.domain.page_acquisition import acquisition_violations

spec = json.loads(sys.argv[1])
canonical = Path(spec["canonical"])
report = {
    "pxapi_origin": os.path.realpath(pxapi.__file__),
    "executable": sys.executable,
    "isolated": bool(sys.flags.isolated),
    "safe_path": bool(getattr(sys.flags, "safe_path", False)),
    "contract_root": os.path.realpath(contract_root()),
    "documents": {},
    "producer_violations": None,
    "problems": [],
}
registry = ContractRegistry(Path(spec["contract_root"]))
loaded = {}
for name, entry in spec["documents"].items():
    try:
        value = loads_json((canonical / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report["problems"].append(f"{name}: unreadable ({type(error).__name__})")
        continue
    plural = entry["plural"]
    if plural:
        shaped = isinstance(value, list) and all(isinstance(item, dict) for item in value)
    else:
        shaped = isinstance(value, dict)
    if not shaped:
        wording = "a JSON array of objects" if plural else "one JSON object"
        report["problems"].append(f"{name}: container is not {wording}")
        continue
    loaded[name] = value
    documents = value if plural else [value]
    violations = [
        {"index": index, "pointer": found.pointer, "keyword": found.keyword}
        for index, document in enumerate(documents)
        for found in registry.validate(entry["contract"], document)
    ]
    report["documents"][name] = {
        "contract": entry["contract"],
        "count": len(documents),
        "violations": violations,
    }
pages = spec["page_documents"]
if all(pages[part] in loaded for part in ("manifest", "records", "measurements", "evidence")):
    try:
        found = acquisition_violations(
            loaded[pages["records"]],
            loaded[pages["manifest"]],
            loaded[pages["measurements"]],
            loaded[pages["evidence"]],
        )
    except Exception as error:
        kind = type(error).__name__
        report["problems"].append(f"page documents: the producer invariants raised {kind}")
    else:
        report["producer_violations"] = [{"pointer": v.pointer, "rule": v.rule} for v in found]
else:
    report["problems"].append("page documents: the producer invariants cannot be applied")
print(json.dumps(report, sort_keys=True))
"""

Runner = Callable[[Sequence[str], Path, Mapping[str, str]], subprocess.CompletedProcess[str]]


class ProofFailure(Exception):
    """One check failed; ``stage`` names which part of the proof it belongs to."""

    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


def run_command(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


# --- pure helpers -------------------------------------------------------------------------------


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.strip().split("."))


def satisfies(version: Sequence[int], spec: str) -> bool:
    """Whether a release ``version`` meets a plain ``requires-python`` specifier set."""
    for raw in spec.split(","):
        clause = raw.strip()
        match = re.fullmatch(r"(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+)*)", clause)
        if match is None:
            raise ValueError(f"unsupported requires-python clause: {clause!r}")
        operator, bound = match.groups()
        limit = parse_version(bound)
        width = max(len(version), len(limit))
        left = tuple(version) + (0,) * (width - len(version))
        right = limit + (0,) * (width - len(limit))
        holds = {
            ">=": left >= right,
            "<=": left <= right,
            ">": left > right,
            "<": left < right,
            "==": left == right,
            "!=": left != right,
        }[operator]
        if not holds:
            return False
    return True


def python_request(requires: str, wanted: Sequence[int]) -> str:
    """``requires`` intersected with one preferred minor, e.g. ``>=3.13,<3.15,==3.13.*``."""
    clauses = [raw.strip() for raw in requires.split(",") if raw.strip()]
    minor = ".".join(str(part) for part in wanted)
    return ",".join([*clauses, f"=={minor}.*"])


def managed_dir_argv(uv: Path) -> list[str]:
    return [str(uv), "python", "dir", *MANAGED_DIR]


def find_argv(uv: Path, request: str) -> list[str]:
    return [str(uv), "python", "find", *SYSTEM_FIND, request]


def discovery_environment(env: Mapping[str, str]) -> dict[str, str]:
    """``env`` without the variables in :data:`DISCOVERY_DROPPED`."""
    return {key: value for key, value in env.items() if key not in DISCOVERY_DROPPED}


def runner_home(interpreter: Path) -> Path | None:
    """``<home>`` when ``interpreter`` lies under ``<home>/.agt-runner/``, else ``None``.

    Read off the interpreter path alone, never off ``HOME``: a proof sandbox may point ``HOME``
    at a scratch directory, while the control interpreter still lives in the real home.
    """
    if not interpreter.is_absolute() or RUNNER_DIR not in interpreter.parts[1:]:
        return None
    index = interpreter.parts.index(RUNNER_DIR, 1)
    return Path(*interpreter.parts[:index])


def uv_candidates(executable: str, resolve: Callable[[str], str] = os.path.realpath) -> list[Path]:
    """Deterministic places ``uv`` sits when ``PATH`` does not name it, in lookup order.

    Beside the control interpreter, as given and resolved; then, for a control interpreter under
    ``<home>/.agt-runner/``, ``<home>/.local/bin`` — where uv's standalone installer puts it.
    """
    names = ("uv.exe", "uv") if os.name == "nt" else ("uv",)
    interpreters = (Path(executable), Path(resolve(executable)))
    directories: list[Path] = [interpreter.parent for interpreter in interpreters]
    for interpreter in interpreters:
        home = runner_home(interpreter)
        if home is not None:
            directories.append(home / ".local" / "bin")
    unique = list(dict.fromkeys(directories))
    return [directory / name for directory in unique for name in names]


def is_executable_file(path: Path) -> bool:
    """Whether ``path`` exists as a regular file this process may execute."""
    return path.is_file() and os.access(path, os.X_OK)


def system_python_directories(
    wanted: Sequence[int], platform_name: str = sys.platform
) -> list[Path]:
    """The :data:`WELL_KNOWN_PYTHON_DIRS` of ``platform_name`` for one preferred minor.

    Deterministic and read off nothing but the two arguments: no ``HOME``, no environment, no
    filesystem. Platforms without an entry get the generic POSIX locations.
    """
    minor = ".".join(str(part) for part in wanted)
    compact = "".join(str(part) for part in wanted)
    templates = WELL_KNOWN_PYTHON_DIRS.get(platform_name, WELL_KNOWN_PYTHON_DIRS["posix"])
    return [Path(template.format(minor=minor, compact=compact)) for template in templates]


def find_search_path(
    path: str | None,
    directories: Sequence[Path],
    excluded: Sequence[Path],
    is_dir: Callable[[Path], bool] = Path.is_dir,
) -> tuple[str, dict[str, list[str]]]:
    """``PATH`` for one ``uv python find`` and where each of its entries came from.

    The inherited ``path`` entries come first, unchanged and in order. Then each of
    ``directories`` (deduplicated, in order) is appended once when it is not already present,
    exists as a directory and does not lie under any of the ``excluded`` real roots (uv's
    managed root, the project environments). The provenance lists the inherited entries, every
    well-known directory considered and which were added, absent, excluded or already present.
    """
    inherited = [entry for entry in (path or "").split(os.pathsep) if entry]
    seen = {os.path.normpath(entry) for entry in inherited}
    considered = list(dict.fromkeys(directories))
    added: list[str] = []
    absent: list[str] = []
    dropped: list[str] = []
    present: list[str] = []
    for directory in considered:
        text = str(directory)
        if os.path.normpath(text) in seen:
            present.append(text)
        elif not is_dir(directory):
            absent.append(text)
        elif any(Path(os.path.realpath(directory)).is_relative_to(root) for root in excluded):
            dropped.append(text)
        else:
            seen.add(os.path.normpath(text))
            added.append(text)
    provenance = {
        "inherited": inherited,
        "well_known": [str(directory) for directory in considered],
        "added": added,
        "absent": absent,
        "excluded": dropped,
        "already_present": present,
    }
    return os.pathsep.join([*inherited, *added]), provenance


def discovered_via(python: Path, provenance: Mapping[str, Sequence[str]]) -> str:
    """Which search-path entry made ``python`` discoverable, for the receipt.

    An entry names ``python`` when it is its directory or holds a link resolving to it (Homebrew's
    ``opt`` directories are links into the Cellar). Added well-known directories are attributed
    before inherited ones.
    """
    real = os.path.realpath(python)
    for kind, key in (("well-known directory", "added"), ("inherited PATH entry", "inherited")):
        for directory in provenance.get(key, ()):
            if os.path.normpath(python.parent) == os.path.normpath(directory):
                return f"{kind} {directory}"
            if os.path.realpath(Path(directory) / python.name) == real:
                return f"{kind} {directory}"
    return "not attributable to a search-path entry"


def find_uv(
    which: Callable[[str], str | None], executable: str, is_executable: Callable[[Path], bool]
) -> Path | None:
    """``uv`` from ``PATH`` first, then from :func:`uv_candidates`; only an executable file."""
    found = which("uv")
    if found and is_executable(Path(found)):
        return Path(found)
    for candidate in uv_candidates(executable):
        if is_executable(candidate):
            return candidate
    return None


def venv_python(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def python_argv(python: Path, *rest: str) -> list[str]:
    """``python`` started in isolated mode, then ``rest`` — the only way this harness runs one."""
    return [str(python), *ISOLATED_FLAGS, *rest]


def cli_argv(python: Path, output_dir: Path) -> list[str]:
    return python_argv(
        python,
        "-m",
        CLI_MODULE,
        TARGET,
        "--max-selected-pages",
        str(MAX_SELECTED_PAGES),
        "--output-dir",
        str(output_dir),
    )


def verifier_spec(canonical: Path, contract_root: Path) -> dict[str, Any]:
    """What :data:`CONTRACT_VERIFIER` is told: the files, their contracts and containers."""
    return {
        "canonical": str(canonical),
        "contract_root": str(contract_root),
        "documents": {
            name: {"contract": CANONICAL_CONTRACTS[member], "plural": member in LIST_MEMBERS}
            for member, name in CANONICAL_FILES.items()
        },
        "page_documents": {
            "manifest": CANONICAL_FILES["sampling_manifest"],
            "records": CANONICAL_FILES["page_acquisitions"],
            "measurements": CANONICAL_FILES["measurements"],
            "evidence": CANONICAL_FILES["website_evidence"],
        },
    }


def verifier_argv(python: Path, spec: Mapping[str, Any]) -> list[str]:
    return python_argv(python, "-c", CONTRACT_VERIFIER, json.dumps(spec, sort_keys=True))


def shadowing_entries(root: Path) -> list[str]:
    """Checkout-root entries an interpreter could import as the ``pxapi`` package or module."""
    names = sorted(entry.name for entry in root.iterdir())
    return [name for name in names if name == SHADOW_NAME or name.startswith(f"{SHADOW_NAME}.")]


def uv_environment(environ: Mapping[str, str], scratch: Path) -> dict[str, str]:
    """The host environment with Python downloads and uv-managed Pythons switched off.

    The project environment and uv's cache both live in ``scratch``, so nothing of the host's
    is written; ``VIRTUAL_ENV`` is dropped so no activated environment is picked up instead.
    """
    env = {key: value for key, value in environ.items() if key != "VIRTUAL_ENV"}
    env.update(
        UV_PYTHON_DOWNLOADS="never",
        UV_PYTHON_PREFERENCE="only-system",
        UV_PROJECT_ENVIRONMENT=str(scratch / "venv"),
        UV_CACHE_DIR=str(scratch / "uv-cache"),
    )
    return env


def cli_environment(environ: Mapping[str, str], trust_bundle: str) -> dict[str, str]:
    """The host environment for the command line and the verifier: locked trust bundle, no
    foreign imports, and the checkout's own contract registry (``PXAPI_CONTRACTS_DIR`` dropped).

    ``-I`` already ignores every ``PYTHON*`` variable; dropping them here as well keeps the
    recorded environment honest about what the command could see.
    """
    dropped = {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "SSL_CERT_DIR", "PXAPI_CONTRACTS_DIR"}
    env = {key: value for key, value in environ.items() if key not in dropped}
    env["SSL_CERT_FILE"] = trust_bundle
    return env


# --- digests, recomputed ------------------------------------------------------------------------


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, **CANONICAL_JSON).encode("utf-8")


def digest_of(value: Any) -> str:
    """The canonical digest of ``value``, exactly as the shipped producer writes it."""
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def is_digest(value: Any) -> bool:
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def _is_rank(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _unique(items: Sequence[Any], member: str) -> bool:
    """Whether no two items carry the same ``member`` value; items without it are skipped."""
    seen: list[Any] = []
    for item in items:
        if not isinstance(item, dict) or member not in item:
            continue
        if item[member] in seen:
            return False
        seen.append(item[member])
    return True


def inventory_output_projection(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """The inventory's stable semantics in canonical order; raises on an ambiguous document."""
    sources = inventory["sources"]
    candidates = inventory["candidates"]
    if not _unique(sources, "source_id") or not _unique(candidates, "url_key"):
        raise ValueError("ambiguous semantic keys")
    projection = {member: inventory[member] for member in INVENTORY_OUTPUT}
    projection["sources"] = sorted(
        (dict(source) for source in sources), key=itemgetter("source_id")
    )
    projection["candidates"] = sorted(
        (
            dict(
                candidate,
                observed_forms=sorted(candidate["observed_forms"]),
                provenance=sorted(candidate["provenance"]),
            )
            for candidate in candidates
        ),
        key=itemgetter("url_key"),
    )
    return projection


def manifest_input_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """What the selection was decided from; ``budgets`` only when one was declared."""
    return {member: manifest[member] for member in MANIFEST_INPUT if member in manifest}


def manifest_output_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """The selection semantics in canonical order; raises on an ambiguous document."""
    selections = manifest["selections"]
    exclusions = manifest["exclusions"]
    if not (
        _unique(selections, "url_key")
        and _unique(selections, "selection_rank")
        and _unique(exclusions, "reason")
    ):
        raise ValueError("ambiguous semantic keys")
    ranks = [selection.get("selection_rank") for selection in selections]
    if (
        ranks
        and all(_is_rank(rank) for rank in ranks)
        and sorted(ranks) != list(range(1, len(ranks) + 1))
    ):
        raise ValueError("selection ranks are not 1..n")
    projection: dict[str, Any] = {
        "mode": manifest["mode"],
        "selection_complete": manifest["selection_complete"],
    }
    if "incompleteness" in manifest:
        projection["incompleteness"] = dict(manifest["incompleteness"])
    projection["selections"] = [
        dict(selection) for selection in sorted(selections, key=itemgetter("selection_rank"))
    ]
    projection["exclusions"] = sorted(
        (dict(exclusion) for exclusion in exclusions), key=itemgetter("reason")
    )
    return projection


def _try_digest(compute: Callable[[], Any]) -> str | None:
    """``digest_of(compute())``, or ``None`` for a document that cannot be projected at all."""
    try:
        return digest_of(compute())
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def recompute_digests(inventory: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Every acquisition digest the bundle can be asked to reproduce, recomputed here.

    The inventory's ``input_digest`` is over discovery observations the bundle does not carry,
    so it is not recomputed: that is the evidence ceiling, and it is stated rather than filled.
    """
    return {
        "site_inventory": {
            "output_digest": _try_digest(lambda: inventory_output_projection(inventory)),
        },
        "sampling_manifest": {
            "input_digest": _try_digest(lambda: manifest_input_projection(manifest)),
            "output_digest": _try_digest(lambda: manifest_output_projection(manifest)),
        },
    }


# --- the receipt, re-derived -----------------------------------------------------------------


def expected_receipt(
    doc: Mapping[str, Any], recomputed: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """``receipt.json`` as the canonical documents alone determine it.

    Mirrors ``acquire_cli.page_receipt`` member for member (a unit test keeps the two identical
    on a real bundle), except that every digest the bundle can reproduce is the recomputed value
    rather than a copy, so a receipt that copied a forged digest differs here.
    """
    state = doc.get("analysis_run_state", {})
    inventory = doc.get("site_inventory")
    manifest = doc.get("sampling_manifest")
    if recomputed is None:
        recomputed = recompute_digests(
            inventory if isinstance(inventory, dict) else {},
            manifest if isinstance(manifest, dict) else {},
        )
    receipt: dict[str, Any] = {"run_id": state.get("run_id"), "run_state": state.get("state")}
    if "failure" in state:
        failure = state["failure"]
        receipt["failure_code"] = failure.get("code") if isinstance(failure, dict) else None
    if isinstance(inventory, dict):
        receipt["site_inventory"] = {
            "inventory_id": inventory.get("inventory_id"),
            "target_origin": inventory.get("target_origin"),
            "candidate_count": _count(inventory.get("candidates", [])),
            "input_digest": inventory.get("input_digest"),
            "output_digest": recomputed["site_inventory"]["output_digest"],
        }
    if isinstance(manifest, dict):
        receipt["sampling_manifest"] = {
            "sampling_manifest_id": manifest.get("sampling_manifest_id"),
            "inventory_ref": manifest.get("inventory_ref"),
            "inventory_output_digest": manifest.get("inventory_output_digest"),
            "budgets": manifest.get("budgets"),
            "mode": manifest.get("mode"),
            "selection_complete": manifest.get("selection_complete"),
            "incompleteness": manifest.get("incompleteness"),
            "selected_count": _count(manifest.get("selections", [])),
            "exclusions": manifest.get("exclusions"),
            "input_digest": recomputed["sampling_manifest"]["input_digest"],
            "output_digest": recomputed["sampling_manifest"]["output_digest"],
        }
    receipt["document_digests"] = {
        member: {"count": len(doc[member]), "digest": digest_of(doc[member])}
        for member in PAGE_MEMBERS
        if member in doc
    }
    receipt["pages"] = _page_rows(doc, manifest if isinstance(manifest, dict) else {})
    return receipt


def _count(value: Any) -> int | None:
    """``len(value)`` for a JSON array; ``None`` where the producer's receipt would not exist."""
    return len(value) if isinstance(value, list) else None


def _items(value: Any) -> list[Any]:
    """``value`` as a JSON array, or nothing: a scalar where an array belongs has no items."""
    return value if isinstance(value, list) else []


def _page_rows(doc: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    ranks = {
        selection.get("url_key"): selection.get("selection_rank")
        for selection in _items(manifest.get("selections"))
        if isinstance(selection, dict)
    }
    measurements = {item.get("measurement_id"): item for item in doc.get("measurements", [])}
    evidence_for: dict[Any, list[Any]] = {}
    for item in doc.get("website_evidence", []):
        for ref in _items(item.get("measurement_refs")):
            evidence_for.setdefault(ref, []).append(item.get("evidence_id"))
    rows: list[dict[str, Any]] = []
    for record in doc.get("page_acquisitions", []):
        refs = _items(record.get("measurement_refs"))
        reasons = sorted(
            {
                measurements[ref]["assessment"]["not_assessed_reason"]
                for ref in refs
                if ref in measurements
                and isinstance(measurements[ref].get("assessment"), dict)
                and "not_assessed_reason" in measurements[ref]["assessment"]
            }
        )
        rows.append(
            {
                "selection_rank": ranks.get(record.get("url_key")),
                "url_key": record.get("url_key"),
                "acquisition_id": record.get("acquisition_id"),
                "acquisition_outcome": record.get("acquisition_outcome"),
                "http_status": record.get("http_status"),
                "final_url_key": record.get("final_url_key"),
                "redirect_count": record.get("redirect_count"),
                "body_truncated": record.get("body_truncated"),
                "body_decoded": record.get("body_decoded"),
                "body_digest": record.get("body_digest"),
                "measurement_refs": list(refs),
                "evidence_refs": [e for ref in refs for e in evidence_for.get(ref, [])],
                "not_assessed_reasons": reasons,
                "measurements_withheld_reason": record.get("measurements_withheld_reason"),
            }
        )
    return rows


# --- the canonical bundle -----------------------------------------------------------------------


def _refuse_constant(token: str) -> Any:
    raise ValueError(f"non-JSON constant: {token}")


def _loads(data: bytes) -> Any:
    """Parse one file, refusing ``NaN``/``Infinity`` exactly as the runtime registry does."""
    return json.loads(data.decode("utf-8"), parse_constant=_refuse_constant)


def check_bundle(
    files: Mapping[str, bytes], stdout: str, budget: int
) -> tuple[list[str], dict[str, Any]]:
    """Every problem with one run's canonical bundle, and what the receipt records about it.

    ``files`` is the output directory's full listing, ``stdout`` the envelope the command
    printed. Nothing here raises on a malformed bundle: every defect is a reported problem.
    """
    expected = {*CANONICAL_FILES.values(), CLI_RECEIPT}
    problems = [f"{name}: missing" for name in sorted(expected - set(files))]
    problems += [f"{name}: not part of the bundle" for name in sorted(set(files) - expected)]
    docs: dict[str, Any] = {}
    for name in sorted(expected & set(files)):
        try:
            docs[name] = _loads(files[name])
        except ValueError:
            problems.append(f"{name}: not valid JSON")
    try:
        envelope = _loads(stdout.encode("utf-8"))
    except ValueError:
        envelope = None
        problems.append("stdout: the printed envelope is not valid JSON")
    for member, name in [*CANONICAL_FILES.items(), ("receipt", CLI_RECEIPT)]:
        if name in docs and not _shaped(member, docs[name]):
            problems.append(f"{name}: unexpected document shape")
    if problems:
        return problems, {}
    try:
        return _check_linkage(docs, envelope, budget)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        return [f"bundle: unexpected structure ({type(error).__name__}: {error})"], {}


def _shaped(member: str, value: Any) -> bool:
    if member in LIST_MEMBERS:
        return isinstance(value, list) and all(isinstance(item, dict) for item in value)
    return isinstance(value, dict)


def _check_linkage(
    docs: dict[str, Any], envelope: Any, budget: int
) -> tuple[list[str], dict[str, Any]]:
    problems: list[str] = []
    doc = {member: docs[name] for member, name in CANONICAL_FILES.items()}
    receipt = docs[CLI_RECEIPT]
    state = doc["analysis_run_state"]
    inventory = doc["site_inventory"]
    manifest = doc["sampling_manifest"]
    records = doc["page_acquisitions"]
    measurements = doc["measurements"]
    evidence = doc["website_evidence"]
    run_id = state.get("run_id")

    if state.get("state") != "SUCCEEDED":
        problems.append(f"run state is {state.get('state')!r}, not 'SUCCEEDED'")
    printed = envelope if isinstance(envelope, dict) else {}
    if any(printed.get(member) != doc[member] for member in CANONICAL_FILES):
        problems.append("stdout: the printed envelope differs from the files written")
    for member, value in doc.items():
        name = CANONICAL_FILES[member]
        for index, item in enumerate(value if isinstance(value, list) else [value]):
            if not isinstance(item.get("schema_version"), str):
                problems.append(f"{name}/{index}: declares no schema_version")
            if item.get("run_id") != run_id:
                problems.append(f"{name}/{index}: belongs to another run")

    recomputed = recompute_digests(inventory, manifest)
    problems += _digest_problems(inventory, manifest, recomputed)
    ranked = _selection_problems(manifest, inventory, budget, problems)
    selected = [selection["url_key"] for selection in ranked]
    by_id, owner = _record_problems(records, manifest, selected, measurements, problems)
    evidence_of = _evidence_problems(evidence, by_id, owner, problems)
    linked = [key for key in selected if key in evidence_of]
    if len(linked) < MIN_PAGES:
        problems.append(
            f"evidence -> measurement -> acquisition resolves for {len(linked)} page(s); "
            f"at least {MIN_PAGES} needed"
        )

    expected = expected_receipt(doc, recomputed)
    problems += _receipt_problems(receipt, expected)

    summary = {
        "run": _run_summary(state, inventory, manifest),
        "recomputed_digests": recomputed,
        "document_digests": expected["document_digests"],
        "pages": expected["pages"],
        "linked_page_refs": linked,
    }
    return problems, summary


def _digest_problems(
    inventory: Mapping[str, Any], manifest: Mapping[str, Any], recomputed: Mapping[str, Any]
) -> list[str]:
    problems: list[str] = []
    inventory_file = CANONICAL_FILES["site_inventory"]
    if not is_digest(inventory.get("input_digest")):
        problems.append(f"{inventory_file}: input_digest is not a sha256 digest")
    documents = {
        "site_inventory": (inventory_file, inventory),
        "sampling_manifest": (CANONICAL_FILES["sampling_manifest"], manifest),
    }
    for member, (name, document) in documents.items():
        for field, value in recomputed[member].items():
            declared = document.get(field)
            if not is_digest(declared):
                problems.append(f"{name}: {field} is not a sha256 digest")
            if value is None:
                problems.append(f"{name}: {field} cannot be recomputed from the document")
            elif declared != value:
                problems.append(f"{name}: {field} does not reproduce from the document")
    return problems


def _selection_problems(
    manifest: Mapping[str, Any], inventory: Mapping[str, Any], budget: int, problems: list[str]
) -> list[dict[str, Any]]:
    """The manifest's selections in rank order, or ``[]`` when no order can be read off them."""
    if manifest.get("inventory_ref") != inventory.get("inventory_id") or manifest.get(
        "inventory_output_digest"
    ) != inventory.get("output_digest"):
        problems.append("sampling manifest is not bound to this run's site inventory")
    if manifest.get("budgets") != {"max_selected_pages": budget}:
        problems.append(f"sampling manifest budget is not max_selected_pages={budget}")

    selections = manifest.get("selections")
    if not isinstance(selections, list) or not all(
        isinstance(selection, dict)
        and _is_rank(selection.get("selection_rank"))
        and isinstance(selection.get("url_key"), str)
        for selection in selections
    ):
        problems.append(
            "sampling manifest selections are not objects with a positive whole-number rank "
            "and a url_key"
        )
        return []
    ranked = sorted(selections, key=itemgetter("selection_rank"))
    ranks = [selection["selection_rank"] for selection in ranked]
    if ranks != list(range(1, len(ranks) + 1)):
        problems.append("sampling manifest ranks are not exactly 1..n")
    selected = [selection["url_key"] for selection in ranked]
    distinct = len(set(selected))
    if distinct != len(selected):
        problems.append("sampling manifest selects a Page Ref twice")
    if distinct < MIN_PAGES:
        problems.append(f"only {distinct} page(s) selected; at least {MIN_PAGES} needed")
    if len(selected) > budget:
        problems.append("sampling manifest selects more pages than its budget")
    candidates = inventory.get("candidates")
    if isinstance(candidates, list):
        keys = {item.get("url_key") for item in candidates if isinstance(item, dict)}
        problems += [
            f"page {key}: not a candidate of the bound inventory"
            for key in selected
            if key not in keys
        ]
    return ranked


def _record_problems(
    records: Sequence[dict[str, Any]],
    manifest: Mapping[str, Any],
    selected: Sequence[str],
    measurements: Sequence[dict[str, Any]],
    problems: list[str],
) -> tuple[dict[Any, dict[str, Any]], dict[Any, dict[str, Any]]]:
    """``(measurement id -> measurement, measurement id -> owning record)``, checking the way."""
    observed = [record.get("url_key") for record in records]
    if observed != list(selected):
        problems.append("acquisition records are not exactly the selection in rank order")
    for key in selected:
        count = observed.count(key)
        if count == 0:
            problems.append(f"page {key}: no acquisition record")
        elif count > 1:
            problems.append(f"page {key}: acquired {count} times")
    problems += [
        f"record {record.get('acquisition_id')}: not a selected page"
        for record in records
        if record.get("url_key") not in selected
    ]

    by_id: dict[Any, dict[str, Any]] = {}
    for item in measurements:
        measurement_id = item.get("measurement_id")
        if measurement_id in by_id:
            problems.append(f"measurement {measurement_id}: identity occurs twice")
        else:
            by_id[measurement_id] = item

    seen: list[Any] = []
    owner: dict[Any, dict[str, Any]] = {}
    for record in records:
        acquisition_id = record.get("acquisition_id")
        if acquisition_id in seen:
            problems.append(f"record {acquisition_id}: acquisition identity occurs twice")
        else:
            seen.append(acquisition_id)
        if record.get("sampling_manifest_ref") != manifest.get(
            "sampling_manifest_id"
        ) or record.get("sampling_manifest_output_digest") != manifest.get("output_digest"):
            problems.append(f"record {acquisition_id}: not bound to the manifest")
        if "raw_artifact_ref" in record:
            problems.append(f"record {acquisition_id}: points at a raw artifact")
        refs = record.get("measurement_refs")
        if not isinstance(refs, list):
            problems.append(f"record {acquisition_id}: measurement_refs is not a list")
            continue
        if (not refs) != ("measurements_withheld_reason" in record):
            problems.append(
                f"record {acquisition_id}: measurements neither carried nor withheld with a reason"
            )
        if len(set(refs)) != len(refs):
            problems.append(f"record {acquisition_id}: names a measurement twice")
        metrics: list[Any] = []
        for ref in refs:
            if ref not in by_id:
                problems.append(f"record {acquisition_id}: unknown measurement {ref}")
                continue
            if ref in owner:
                problems.append(f"measurement {ref}: owned by two records")
                continue
            owner[ref] = record
            item = by_id[ref]
            if item.get("observed_at") != record.get("acquired_at"):
                problems.append(f"measurement {ref}: not observed at its page's acquisition instant")
            metric = item.get("metric_id")
            if metric in metrics:
                problems.append(f"record {acquisition_id}: measures {metric} twice")
            else:
                metrics.append(metric)
        sources = {by_id[ref].get("source_url") for ref in refs if ref in by_id}
        foreign = sources - {record.get("url_key")}
        if record.get("acquisition_outcome") != "RESPONSE_RECEIVED" and foreign:
            problems.append(
                f"record {acquisition_id}: measurements of a page without a response are not "
                "sourced at its Page Ref"
            )
        elif len(foreign) > 1:
            problems.append(
                f"record {acquisition_id}: measurements are sourced at more than one response URL"
            )
    problems += [
        f"measurement {measurement_id}: owned by no record"
        for measurement_id in by_id
        if measurement_id not in owner
    ]
    return by_id, owner


def _evidence_problems(
    evidence: Sequence[dict[str, Any]],
    by_id: Mapping[Any, dict[str, Any]],
    owner: Mapping[Any, dict[str, Any]],
    problems: list[str],
) -> dict[Any, list[Any]]:
    """``page ref -> evidence ids`` for every evidence record linked to exactly one page."""
    evidence_of: dict[Any, list[Any]] = {}
    seen: list[Any] = []
    for item in evidence:
        evidence_id = item.get("evidence_id")
        if evidence_id in seen:
            problems.append(f"evidence {evidence_id}: identity occurs twice")
        else:
            seen.append(evidence_id)
        if "polarity" in item:
            problems.append(f"evidence {evidence_id}: carries a polarity")
        refs = item.get("measurement_refs")
        if not isinstance(refs, list) or not refs:
            problems.append(f"evidence {evidence_id}: references no measurement")
            continue
        pages = {owner[ref].get("url_key") if ref in owner else None for ref in refs}
        if len(pages) != 1 or None in pages:
            problems.append(f"evidence {evidence_id}: not linked to exactly one page")
            continue
        for ref in refs:
            measurement = by_id[ref]
            if item.get("source_url") != measurement.get("source_url") or item.get(
                "observed_at"
            ) != measurement.get("observed_at"):
                problems.append(f"evidence {evidence_id}: context differs from measurement {ref}")
        evidence_of.setdefault(pages.pop(), []).append(evidence_id)
    return evidence_of


def _receipt_problems(receipt: Mapping[str, Any], expected: Mapping[str, Any]) -> list[str]:
    """Every receipt member that does not state what the canonical documents determine."""
    problems: list[str] = []
    for key in sorted(set(receipt) | set(expected)):
        if key == "pages":
            continue
        if key not in receipt:
            problems.append(f"{CLI_RECEIPT}: {key} is missing")
        elif key not in expected:
            problems.append(f"{CLI_RECEIPT}: {key} is not derivable from the canonical documents")
        elif receipt[key] != expected[key]:
            problems.append(f"{CLI_RECEIPT}: {key} does not describe the canonical documents")
    rows = receipt.get("pages")
    wanted = expected["pages"]
    if not isinstance(rows, list):
        problems.append(f"{CLI_RECEIPT}: pages is not a list")
        return problems
    if len(rows) != len(wanted):
        problems.append(
            f"{CLI_RECEIPT}: {len(rows)} page row(s) for {len(wanted)} acquisition record(s)"
        )
    for index, (row, want) in enumerate(zip(rows, wanted, strict=False)):
        if not isinstance(row, dict):
            problems.append(f"{CLI_RECEIPT}: page row {index} is not an object")
        elif row != want:
            differing = sorted(key for key in set(row) | set(want) if row.get(key) != want.get(key))
            problems.append(f"{CLI_RECEIPT}: page row {index} differs in {', '.join(differing)}")
    return problems


def _run_summary(
    state: dict[str, Any], inventory: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    return {
        "run_id": state.get("run_id"),
        "state": state.get("state"),
        "inventory_id": inventory.get("inventory_id"),
        "inventory_input_digest": inventory.get("input_digest"),
        "inventory_output_digest": inventory.get("output_digest"),
        "sampling_manifest_id": manifest.get("sampling_manifest_id"),
        "sampling_manifest_input_digest": manifest.get("input_digest"),
        "sampling_manifest_output_digest": manifest.get("output_digest"),
        "selection_complete": manifest.get("selection_complete"),
        "incompleteness": manifest.get("incompleteness"),
    }


# --- the verifier's report ----------------------------------------------------------------------


def origin_binding(origin: Any, root: Path, environment: Path) -> str | None:
    """Which locked installation the imported ``pxapi`` package belongs to, or ``None``.

    Either the tracked ``src/pxapi`` of the checkout (the editable installation ``uv sync``
    makes, whose cleanliness ``git status`` proved) or a ``pxapi`` package inside the disposable
    environment. Anything else — a checkout-root package, a user site, another checkout — is
    not the implementation the recorded SHA names.
    """
    if not isinstance(origin, str) or not origin:
        return None
    real = Path(os.path.realpath(origin))
    if real.name != "__init__.py" or real.parent.name != SHADOW_NAME:
        return None
    if real.parent == Path(os.path.realpath(root / TRACKED_PACKAGE)):
        return f"tracked {TRACKED_PACKAGE} of the checkout"
    if real.is_relative_to(Path(os.path.realpath(environment))):
        return "locked disposable project environment"
    return None


def isolation_problem(report: Mapping[str, Any], root: Path, environment: Path) -> str | None:
    """Why the verifier's runtime is not the isolated, locked, tracked one — or ``None``."""
    if not report.get("isolated") or not report.get("safe_path"):
        return "the runtime did not run in isolated mode with a safe sys.path"
    if origin_binding(report.get("pxapi_origin"), root, environment) is None:
        return f"pxapi was imported from {report.get('pxapi_origin')!r}, not the locked project"
    contract_root = report.get("contract_root")
    if not isinstance(contract_root, str) or os.path.realpath(contract_root) != os.path.realpath(
        root / CONTRACT_ROOT
    ):
        return f"the runtime's contract root is {contract_root!r}, not the checkout's"
    return None


def verification_problems(report: Any) -> list[str]:
    """Every contract or producer-invariant violation the verifier reported, as problems.

    A report that is not the expected shape is itself a problem: the verifier that produced it
    is not the one this harness runs, or it failed halfway.
    """
    if not isinstance(report, dict):
        return ["verification: the verifier printed no JSON object"]
    try:
        return _report_problems(report)
    except (AttributeError, KeyError, TypeError) as error:
        return [f"verification: malformed verifier report ({type(error).__name__})"]


def _report_problems(report: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    reported = [str(problem) for problem in report.get("problems", [])]
    documents = report.get("documents")
    if not isinstance(documents, dict):
        return ["verification: the verifier validated no document", *reported]
    for name in sorted(CANONICAL_FILES.values()):
        entry = documents.get(name)
        if entry is None:
            if not any(problem.startswith(f"{name}:") for problem in reported):
                problems.append(f"{name}: not validated")
            continue
        contract = entry["contract"]
        for violation in entry["violations"]:
            problems.append(
                f"{name}/{violation['index']}: violates {contract} at "
                f"{violation['pointer']} [{violation['keyword']}]"
            )
    producer = report.get("producer_violations")
    if isinstance(producer, list):
        problems += [f"page documents: {v['pointer']} [{v['rule']}]" for v in producer]
    elif not any(problem.startswith("page documents:") for problem in reported):
        problems.append("page documents: the producer invariants were not applied")
    return [*problems, *reported]


# --- the proof ----------------------------------------------------------------------------------


def _checked(
    runner: Runner, stage: str, argv: Sequence[str], cwd: Path, env: Mapping[str, str]
) -> str:
    try:
        completed = runner(argv, cwd, env)
    except (OSError, subprocess.SubprocessError) as error:
        raise ProofFailure(stage, f"{argv[0]} could not run ({type(error).__name__})") from error
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip()[-2_000:]
        raise ProofFailure(stage, f"exit {completed.returncode}: {tail}")
    return completed.stdout


def _last_json(stage: str, output: str, what: str) -> dict[str, Any]:
    try:
        parsed = json.loads(output.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise ProofFailure(stage, f"{what} printed no JSON") from error
    if not isinstance(parsed, dict):
        raise ProofFailure(stage, f"{what} printed no JSON object")
    return parsed


def _probe(
    runner: Runner, stage: str, python: Path, cwd: Path, env: Mapping[str, str]
) -> dict[str, Any]:
    output = _checked(runner, stage, python_argv(python, "-c", PROBE), cwd, env)
    return _last_json(stage, output, "interpreter probe")


def version_info(probed: Mapping[str, Any]) -> tuple[int, ...] | None:
    """The probed ``sys.version_info[:3]``, or ``None`` when the probe did not report one."""
    info = probed.get("version_info")
    if not isinstance(info, list) or not info or not all(type(part) is int for part in info):
        return None
    return tuple(info)


def select_python(
    runner: Runner,
    uv: Path,
    root: Path,
    env: Mapping[str, str],
    requires: str,
    candidates: list[dict[str, Any]],
    system_directories: Callable[[Sequence[int]], Sequence[Path]] = system_python_directories,
    workdir: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """The first :data:`PREFERRED_PYTHONS` interpreter fit to build the project runtime.

    A candidate is what ``uv python find`` names for ``requires`` intersected with the preferred
    minor, run with :data:`SYSTEM_FIND` and without :data:`DISCOVERY_DROPPED`, so neither a
    ``.python-version`` pin nor project or user uv configuration chooses it. That one lookup's
    ``PATH`` is the inherited ``PATH`` followed by the existing well-known system directories
    ``system_directories`` names for the minor (:func:`find_search_path`), so a restricted
    sandbox ``PATH`` does not hide an installed system interpreter from uv; no executable is
    trusted outright. A candidate is accepted only when it is not under uv's managed directory
    (``uv python dir`` with :data:`MANAGED_DIR`, also without :data:`DISCOVERY_DROPPED`) and its
    probe — run in isolated mode from ``workdir``, the scratch directory, never the checkout —
    reports the requested minor version and a release satisfying ``requires``. Each candidate's
    outcome and search-path provenance is appended to ``candidates``; a missing or rejected one
    moves on to the next, and none left fails the bootstrap. Nothing is installed, downloaded
    or looked up under ``HOME``.
    """
    find_env = discovery_environment(env)
    managed = _checked(runner, "bootstrap", managed_dir_argv(uv), root, find_env).strip()
    managed_root = os.path.realpath(managed) if managed else None
    excluded = [Path(managed_root)] if managed_root else []
    project_environment = env.get("UV_PROJECT_ENVIRONMENT")
    if project_environment:
        excluded.append(Path(os.path.realpath(project_environment)))
    excluded.append(Path(os.path.realpath(root / ".venv")))
    probe_cwd = root if workdir is None else workdir
    for wanted in PREFERRED_PYTHONS:
        version = ".".join(str(part) for part in wanted)
        request = python_request(requires, wanted)
        entry: dict[str, Any] = {"requested": version, "request": request}
        candidates.append(entry)
        search_path, provenance = find_search_path(
            find_env.get("PATH"), system_directories(wanted), excluded
        )
        entry["search_path"] = provenance
        lookup_env = {**find_env, "PATH": search_path} if search_path else find_env
        find = find_argv(uv, request)
        try:
            completed = runner(find, root, lookup_env)
        except (OSError, subprocess.SubprocessError) as error:
            detail = f"{uv} could not run ({type(error).__name__})"
            raise ProofFailure("bootstrap", detail) from error
        found = (completed.stdout or "").strip() if completed.returncode == 0 else ""
        if not found:
            entry["outcome"] = "not installed"
            continue
        python = Path(found)
        entry["path"] = str(python)
        entry["discovered_via"] = discovered_via(python, provenance)
        if managed_root and Path(os.path.realpath(python)).is_relative_to(managed_root):
            entry["outcome"] = "rejected: uv-managed Python"
            continue
        try:
            probed = _probe(runner, "bootstrap", python, probe_cwd, env)
        except ProofFailure as failure:
            entry["outcome"] = f"rejected: probe failed ({failure.detail[-200:]})"
            continue
        entry["version"] = probed.get("version")
        info = version_info(probed)
        if info is None or info[:2] != wanted:
            entry["outcome"] = f"rejected: not Python {version}"
            continue
        if not satisfies(info, requires):
            entry["outcome"] = f"rejected: does not satisfy {requires}"
            continue
        entry["outcome"] = "selected"
        return python, probed
    tried = ", ".join(".".join(str(part) for part in wanted) for wanted in PREFERRED_PYTHONS)
    raise ProofFailure("bootstrap", f"no installed system Python ({tried}) satisfies {requires}")


def _check_checkout(
    runner: Runner, root: Path, environ: Mapping[str, str], facts: dict[str, Any]
) -> None:
    """Tracked files clean, nothing untracked under the import roots, nothing shadowing."""
    status = ["git", "status", "--porcelain", "--untracked-files=no"]
    if _checked(runner, "checkout", status, root, environ).strip():
        raise ProofFailure("checkout", "tracked files differ from the exact SHA")
    untracked_argv = [
        "git",
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *UNTRACKED_FORBIDDEN,
    ]
    untracked = _checked(runner, "checkout", untracked_argv, root, environ).strip()
    shadows = shadowing_entries(root)
    facts["isolation"] = {
        "untracked_forbidden_under": list(UNTRACKED_FORBIDDEN),
        "untracked_entries": untracked.splitlines(),
        "checkout_root_shadowing_entries": shadows,
        "interpreter_flags": list(ISOLATED_FLAGS),
    }
    if untracked:
        roots = ", ".join(UNTRACKED_FORBIDDEN)
        raise ProofFailure("isolation", f"untracked entries under {roots}: {untracked[:2_000]}")
    if shadows:
        raise ProofFailure(
            "isolation", f"checkout root holds importable {SHADOW_NAME!r} entries: {shadows}"
        )


def run_proof(
    root: Path,
    proof_dir: Path,
    facts: dict[str, Any],
    *,
    runner: Runner = run_command,
    environ: Mapping[str, str] = os.environ,
    which: Callable[[str], str | None] = shutil.which,
    executable: str = sys.executable,
    expected_sha: str | None = None,
    system_directories: Callable[[Sequence[int]], Sequence[Path]] = system_python_directories,
) -> None:
    """Execute the proof, recording every fact into ``facts``; raise ``ProofFailure`` on a miss."""
    facts["control_runtime"] = {"executable": executable, "version": platform.python_version()}

    sha = _checked(runner, "checkout", ["git", "rev-parse", "HEAD"], root, environ).strip()
    facts["exact_sha"] = sha
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ProofFailure("checkout", f"HEAD is not a full SHA: {sha!r}")
    if expected_sha is not None and sha != expected_sha:
        raise ProofFailure("checkout", f"HEAD {sha} is not the expected {expected_sha}")
    _check_checkout(runner, root, environ, facts)

    uv = find_uv(which, executable, is_executable_file)
    if uv is None:
        raise ProofFailure("bootstrap", "uv not found on PATH or at any deterministic candidate")
    uv_version = _checked(runner, "bootstrap", [str(uv), "--version"], root, environ).strip()
    facts["uv"] = {"path": str(uv), "version": uv_version}

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    requires = pyproject["project"]["requires-python"]
    facts["requires_python"] = requires
    try:
        satisfies((0,), requires)
    except ValueError as error:
        raise ProofFailure("bootstrap", f"requires-python {requires!r}: {error}") from error
    lock = root / "uv.lock"
    before = sha256_hex(lock.read_bytes())
    facts["lock"] = {"sha256_before": before}

    with tempfile.TemporaryDirectory(prefix="pxapi20b-proof-") as scratch_name:
        scratch = Path(scratch_name)
        workdir = scratch / "cwd"
        workdir.mkdir()
        facts["isolation"]["working_directory"] = str(workdir)
        uv_env = uv_environment(environ, scratch)
        candidates: list[dict[str, Any]] = []
        facts["python_candidates"] = candidates
        base_python, base = select_python(
            runner, uv, root, uv_env, requires, candidates, system_directories, workdir
        )
        base_info = version_info(base)
        facts["selected_python"] = {
            "path": str(base_python),
            "version": base.get("version"),
            "requires_python": requires,
        }

        sync = [str(uv), "sync", "--locked", "--python", str(base_python), *NO_MANAGED]
        _checked(runner, "bootstrap", sync, root, uv_env)
        after = sha256_hex(lock.read_bytes())
        facts["lock"].update(sha256_after=after, unchanged=after == before)
        if after != before:
            raise ProofFailure("bootstrap", "uv.lock changed during uv sync --locked")

        environment = scratch / "venv"
        python = venv_python(environment)
        project = _probe(runner, "runtime", python, workdir, uv_env)
        facts["project_runtime"] = {
            "executable": str(python),
            "version": project.get("version"),
            "prefix": project.get("prefix"),
        }
        project_info = version_info(project)
        if project_info is None or not satisfies(project_info, requires):
            detail = f"the project environment's Python {project.get('version')!r} is outside"
            raise ProofFailure("runtime", f"{detail} {requires}")
        if base_info is None or project_info[:2] != base_info[:2]:
            raise ProofFailure("runtime", "the project environment is not the selected Python")
        if os.path.realpath(project.get("prefix", "")) != os.path.realpath(environment):
            raise ProofFailure("runtime", "the project interpreter is not the disposable venv")

        certifi_argv = python_argv(python, "-c", CERTIFI_PROBE)
        bundle = _checked(runner, "runtime", certifi_argv, workdir, uv_env).strip()
        if not Path(bundle).is_file():
            raise ProofFailure("runtime", "the locked certifi trust bundle is not a file")

        canonical = proof_dir / CANONICAL_DIR
        argv = cli_argv(python, canonical)
        cli_env = cli_environment(environ, bundle)
        facts["cli"] = {"argv": argv, "target": TARGET, "trust_bundle": bundle}
        try:
            completed = runner(argv, workdir, cli_env)
        except (OSError, subprocess.SubprocessError) as error:
            detail = f"the CLI could not run ({type(error).__name__})"
            raise ProofFailure("boundary", detail) from error
        facts["cli"]["exit_code"] = completed.returncode
        facts["cli"]["stderr"] = (completed.stderr or "")[-4_000:]
        if completed.returncode != 0:
            raise ProofFailure("boundary", f"the CLI exited {completed.returncode}")

        if not canonical.is_dir():
            raise ProofFailure("artifact", "the CLI wrote no canonical output directory")
        files = {path.name: path.read_bytes() for path in sorted(canonical.iterdir())}
        facts["file_digests"] = {name: sha256_hex(data) for name, data in files.items()}

        spec = verifier_spec(canonical, root / CONTRACT_ROOT)
        output = _checked(runner, "verification", verifier_argv(python, spec), workdir, cli_env)
        report = _last_json("verification", output, "the contract verifier")
        facts["verification"] = {
            "contract_root": report.get("contract_root"),
            "pxapi_origin": report.get("pxapi_origin"),
            "bound_to": origin_binding(report.get("pxapi_origin"), root, environment),
            "isolated": report.get("isolated"),
            "safe_path": report.get("safe_path"),
            "documents": report.get("documents"),
            "producer_violations": report.get("producer_violations"),
        }
        isolation = isolation_problem(report, root, environment)
        if isolation is not None:
            raise ProofFailure("isolation", isolation)
        contract_problems = verification_problems(report)

    problems, summary = check_bundle(files, completed.stdout, MAX_SELECTED_PAGES)
    facts.update(summary)
    facts["problems"] = [*contract_problems, *problems]
    if contract_problems:
        raise ProofFailure(
            "contract", f"{len(contract_problems)} contract or producer-invariant check(s) failed"
        )
    if problems:
        raise ProofFailure("linkage", f"{len(problems)} bundle check(s) failed")


def build_receipt(facts: Mapping[str, Any], failure: ProofFailure | None) -> dict[str, Any]:
    receipt = {
        "proof": "PXAPI-20.B real-boundary multi-page acquisition",
        "verdict": "FAILED" if failure else "PASSED",
        "failure": {"stage": failure.stage, "detail": failure.detail} if failure else None,
        "target": TARGET,
        "max_selected_pages": MAX_SELECTED_PAGES,
        "minimum_pages": MIN_PAGES,
        "evidence_ceiling": EVIDENCE_CEILING,
    }
    receipt.update(facts)
    receipt.setdefault("problems", [])
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--expected-sha", default=None, help="fail unless HEAD is this SHA")
    arguments = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    proof_dir = root / PROOF_DIR
    try:
        proof_dir.mkdir(parents=True)
    except FileExistsError:
        sys.stderr.write(f"proof: {proof_dir} already exists; every proof starts fresh.\n")
        return 2

    facts: dict[str, Any] = {}
    failure: ProofFailure | None = None
    try:
        run_proof(root, proof_dir, facts, expected_sha=arguments.expected_sha)
    except ProofFailure as error:
        failure = error
    except Exception as error:  # a harness defect must still leave a failing receipt
        failure = ProofFailure("harness", f"{type(error).__name__}: {error}")

    receipt = build_receipt(facts, failure)
    text = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (proof_dir / PROOF_RECEIPT).write_text(text, encoding="utf-8")
    sys.stdout.write(f"proof: {receipt['verdict']} -> {proof_dir / PROOF_RECEIPT}\n")
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
