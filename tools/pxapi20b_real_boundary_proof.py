"""PXAPI-20.B real-boundary proof harness: one locked multi-page acquisition, checked end to end.

Run it with any Python 3.11+ *control* interpreter from a fresh exact-SHA checkout::

    python tools/pxapi20b_real_boundary_proof.py [--expected-sha SHA]

It uses the standard library only and changes nothing on the host. It

1. records the checkout's exact ``HEAD`` SHA and refuses a checkout with tracked modifications;
2. locates ``uv`` on ``PATH``, else beside ``sys.executable`` or, for a control interpreter under
   ``<home>/.agt-runner/``, in ``<home>/.local/bin`` — read off the interpreter path, not ``HOME``;
3. selects an already installed Python 3.14 with downloads and uv-managed Pythons disabled;
4. builds a disposable project environment under ``TMPDIR`` with ``uv sync --locked`` against
   the checkout's own ``pyproject.toml`` and ``uv.lock``, and proves ``uv.lock`` is byte-identical
   afterwards;
5. runs the production command line as the project-runtime Python against the controlled origin
   with an explicit ``--max-selected-pages 3`` and a fresh canonical output directory, trusting
   the locked ``certifi`` bundle;
6. reads every canonical file back and requires a SUCCEEDED run of at least two distinct pages
   whose run, inventory, manifest and page identities agree and whose
   WebsiteEvidence -> MeasurementRecord -> PageAcquisitionRecord chain resolves.

Everything lands under the fixed, untracked :data:`PROOF_DIR` of the checkout: the canonical
JSON artifacts in ``canonical/`` and ``proof-receipt.json`` beside them. Any bootstrap, runtime,
boundary, linkage or artifact failure is recorded in the receipt and exits nonzero.
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
from pathlib import Path
from typing import Any

TARGET = "https://www.rfc-editor.org/"
MAX_SELECTED_PAGES = 3
MIN_PAGES = 2
REQUIRED_PYTHON = (3, 14)
PROOF_DIR = Path(".proof-output") / "pxapi20b-real-boundary"
CANONICAL_DIR = "canonical"
PROOF_RECEIPT = "proof-receipt.json"
CLI_MODULE = "pxapi.adapters.inbound.acquire_cli"
COMMAND_TIMEOUT_SECONDS = 1_800
#: The Agent-team runner's directory directly under the real user home.
RUNNER_DIR = ".agt-runner"

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
CLI_RECEIPT = "receipt.json"
LIST_MEMBERS = frozenset(
    {"stage_executions", "page_acquisitions", "measurements", "website_evidence"}
)

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


def cli_argv(python: Path, output_dir: Path) -> list[str]:
    return [
        str(python),
        "-m",
        CLI_MODULE,
        TARGET,
        "--max-selected-pages",
        str(MAX_SELECTED_PAGES),
        "--output-dir",
        str(output_dir),
    ]


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
    """The host environment for the command line: locked trust bundle, no foreign imports."""
    dropped = {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "SSL_CERT_DIR"}
    env = {key: value for key, value in environ.items() if key not in dropped}
    env["SSL_CERT_FILE"] = trust_bundle
    return env


# --- the canonical bundle -----------------------------------------------------------------------


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
            docs[name] = json.loads(files[name].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            problems.append(f"{name}: not valid JSON")
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        envelope = None
        problems.append("stdout: the printed envelope is not valid JSON")
    for member, name in [*CANONICAL_FILES.items(), ("receipt", CLI_RECEIPT)]:
        if name in docs and not _shaped(member, docs[name]):
            problems.append(f"{name}: unexpected document shape")
    if problems:
        return problems, {}
    try:
        return _check_linkage(docs, envelope, budget)
    except (AttributeError, KeyError, TypeError) as error:
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
        for index, item in enumerate(value if isinstance(value, list) else [value]):
            if item.get("run_id") != run_id:
                problems.append(f"{CANONICAL_FILES[member]}/{index}: belongs to another run")
    if receipt.get("run_id") != run_id or receipt.get("run_state") != state.get("state"):
        problems.append(f"{CLI_RECEIPT}: does not describe this run")

    if manifest.get("inventory_ref") != inventory.get("inventory_id") or manifest.get(
        "inventory_output_digest"
    ) != inventory.get("output_digest"):
        problems.append("sampling manifest is not bound to this run's site inventory")
    if manifest.get("budgets") != {"max_selected_pages": budget}:
        problems.append(f"sampling manifest budget is not max_selected_pages={budget}")

    ranked = sorted(manifest.get("selections", []), key=lambda s: s["selection_rank"])
    selected = [selection["url_key"] for selection in ranked]
    distinct = len(set(selected))
    if distinct != len(selected):
        problems.append("sampling manifest selects a Page Ref twice")
    if distinct < MIN_PAGES:
        problems.append(f"only {distinct} page(s) selected; at least {MIN_PAGES} needed")
    if len(selected) > budget:
        problems.append("sampling manifest selects more pages than its budget")
    if [record["url_key"] for record in records] != selected:
        problems.append("acquisition records are not exactly the selection in rank order")
    rows = receipt.get("pages", [])
    if [row.get("url_key") for row in rows] != selected:
        problems.append(f"{CLI_RECEIPT}: page rows are not exactly the selection")
    if receipt.get("sampling_manifest", {}).get("selected_count") != len(selected):
        problems.append(f"{CLI_RECEIPT}: selected count differs from the manifest")

    measurement_ids = [item["measurement_id"] for item in measurements]
    if len(set(measurement_ids)) != len(measurement_ids):
        problems.append("a measurement identity occurs twice")
    owner: dict[str, str] = {}
    for record in records:
        if record.get("sampling_manifest_ref") != manifest.get(
            "sampling_manifest_id"
        ) or record.get("sampling_manifest_output_digest") != manifest.get("output_digest"):
            problems.append(f"record {record.get('acquisition_id')}: not bound to the manifest")
        for ref in record.get("measurement_refs", []):
            if ref not in measurement_ids:
                problems.append(f"record {record.get('acquisition_id')}: unknown measurement")
            elif ref in owner:
                problems.append(f"measurement {ref}: owned by two records")
            else:
                owner[ref] = record["url_key"]
    for measurement_id in measurement_ids:
        if measurement_id not in owner:
            problems.append(f"measurement {measurement_id}: owned by no record")

    evidence_of: dict[str, list[str]] = {}
    for item in evidence:
        pages = {owner.get(ref) for ref in item.get("measurement_refs", [])}
        if len(pages) != 1 or None in pages:
            problems.append(f"evidence {item.get('evidence_id')}: not linked to exactly one page")
            continue
        evidence_of.setdefault(pages.pop(), []).append(item["evidence_id"])
    linked = [key for key in selected if key in evidence_of]
    if len(linked) < MIN_PAGES:
        problems.append(
            f"evidence -> measurement -> acquisition resolves for {len(linked)} page(s); "
            f"at least {MIN_PAGES} needed"
        )

    summary = {
        "run": _run_summary(state, inventory, manifest),
        "pages": _page_rows(ranked, records, measurements, evidence),
        "linked_page_refs": linked,
        "document_digests": receipt.get("document_digests"),
    }
    return problems, summary


def _run_summary(
    state: dict[str, Any], inventory: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    return {
        "run_id": state.get("run_id"),
        "state": state.get("state"),
        "inventory_id": inventory.get("inventory_id"),
        "inventory_output_digest": inventory.get("output_digest"),
        "sampling_manifest_id": manifest.get("sampling_manifest_id"),
        "sampling_manifest_input_digest": manifest.get("input_digest"),
        "sampling_manifest_output_digest": manifest.get("output_digest"),
        "selection_complete": manifest.get("selection_complete"),
        "incompleteness": manifest.get("incompleteness"),
    }


def _page_rows(
    ranked: list[dict[str, Any]],
    records: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rank_of = {selection["url_key"]: selection["selection_rank"] for selection in ranked}
    assessment_of = {item["measurement_id"]: item.get("assessment", {}) for item in measurements}
    rows = []
    for record in records:
        refs = list(record.get("measurement_refs", []))
        evidence_refs = [
            item["evidence_id"]
            for item in evidence
            if set(item.get("measurement_refs", [])) & set(refs)
        ]
        reasons = sorted(
            {
                assessment_of[ref]["not_assessed_reason"]
                for ref in refs
                if "not_assessed_reason" in assessment_of.get(ref, {})
            }
        )
        rows.append(
            {
                "selection_rank": rank_of.get(record["url_key"]),
                "url_key": record["url_key"],
                "acquisition_id": record.get("acquisition_id"),
                "acquisition_outcome": record.get("acquisition_outcome"),
                "http_status": record.get("http_status"),
                "measurement_refs": refs,
                "evidence_refs": evidence_refs,
                "not_assessed_reasons": reasons,
                "measurements_withheld_reason": record.get("measurements_withheld_reason"),
            }
        )
    return rows


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


def _probe(runner: Runner, stage: str, python: Path, cwd: Path, env: Mapping[str, str]) -> Any:
    output = _checked(runner, stage, [str(python), "-c", PROBE], cwd, env)
    try:
        return json.loads(output.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise ProofFailure(stage, "interpreter probe printed no JSON") from error


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
) -> None:
    """Execute the proof, recording every fact into ``facts``; raise ``ProofFailure`` on a miss."""
    facts["control_runtime"] = {"executable": executable, "version": platform.python_version()}

    sha = _checked(runner, "checkout", ["git", "rev-parse", "HEAD"], root, environ).strip()
    facts["exact_sha"] = sha
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ProofFailure("checkout", f"HEAD is not a full SHA: {sha!r}")
    if expected_sha is not None and sha != expected_sha:
        raise ProofFailure("checkout", f"HEAD {sha} is not the expected {expected_sha}")
    status = ["git", "status", "--porcelain", "--untracked-files=no"]
    if _checked(runner, "checkout", status, root, environ).strip():
        raise ProofFailure("checkout", "tracked files differ from the exact SHA")

    uv = find_uv(which, executable, is_executable_file)
    if uv is None:
        raise ProofFailure("bootstrap", "uv not found on PATH or at any deterministic candidate")
    uv_version = _checked(runner, "bootstrap", [str(uv), "--version"], root, environ).strip()
    facts["uv"] = {"path": str(uv), "version": uv_version}

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    requires = pyproject["project"]["requires-python"]
    facts["requires_python"] = requires
    lock = root / "uv.lock"
    before = sha256_hex(lock.read_bytes())
    facts["lock"] = {"sha256_before": before}

    with tempfile.TemporaryDirectory(prefix="pxapi20b-proof-") as scratch_name:
        scratch = Path(scratch_name)
        uv_env = uv_environment(environ, scratch)
        no_managed = ["--python-preference", "only-system", "--no-python-downloads"]
        version = ".".join(str(part) for part in REQUIRED_PYTHON)
        find = [str(uv), "python", "find", *no_managed, version]
        base_python = Path(_checked(runner, "bootstrap", find, root, uv_env).strip())
        managed = _checked(runner, "bootstrap", [str(uv), "python", "dir"], root, uv_env).strip()
        managed_root = os.path.realpath(managed) if managed else None
        if managed_root and Path(os.path.realpath(base_python)).is_relative_to(managed_root):
            raise ProofFailure("bootstrap", f"{base_python} is a uv-managed Python")
        base = _probe(runner, "bootstrap", base_python, root, uv_env)
        facts["selected_python"] = {"path": str(base_python), "version": base.get("version")}
        if tuple(base.get("version_info", ()))[:2] != REQUIRED_PYTHON:
            raise ProofFailure("bootstrap", f"{base_python} is not Python {version}")
        if not satisfies(base["version_info"], requires):
            raise ProofFailure("bootstrap", f"Python {base['version']} does not meet {requires}")

        sync = [str(uv), "sync", "--locked", "--python", str(base_python), *no_managed]
        _checked(runner, "bootstrap", sync, root, uv_env)
        after = sha256_hex(lock.read_bytes())
        facts["lock"].update(sha256_after=after, unchanged=after == before)
        if after != before:
            raise ProofFailure("bootstrap", "uv.lock changed during uv sync --locked")

        python = venv_python(scratch / "venv")
        project = _probe(runner, "runtime", python, root, uv_env)
        facts["project_runtime"] = {
            "executable": str(python),
            "version": project.get("version"),
            "prefix": project.get("prefix"),
        }
        if tuple(project.get("version_info", ()))[:2] != REQUIRED_PYTHON:
            raise ProofFailure("runtime", "the project environment is not Python 3.14")
        if os.path.realpath(project.get("prefix", "")) != os.path.realpath(scratch / "venv"):
            raise ProofFailure("runtime", "the project interpreter is not the disposable venv")

        certifi_argv = [str(python), "-c", CERTIFI_PROBE]
        bundle = _checked(runner, "runtime", certifi_argv, root, uv_env).strip()
        if not Path(bundle).is_file():
            raise ProofFailure("runtime", "the locked certifi trust bundle is not a file")

        canonical = proof_dir / CANONICAL_DIR
        argv = cli_argv(python, canonical)
        facts["cli"] = {"argv": argv, "target": TARGET, "trust_bundle": bundle}
        try:
            completed = runner(argv, root, cli_environment(environ, bundle))
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
    problems, summary = check_bundle(files, completed.stdout, MAX_SELECTED_PAGES)
    facts.update(summary)
    facts["problems"] = problems
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
