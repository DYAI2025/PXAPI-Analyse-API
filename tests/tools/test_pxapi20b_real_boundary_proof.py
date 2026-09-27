"""Offline checks of the PXAPI-20.B real-boundary proof harness.

The harness is a standard-library script run by the control interpreter, not part of the
product package, so it is imported here by file path. Nothing in this module touches the
network, ``uv`` or any interpreter other than the one running the tests.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from pxapi.adapters.inbound import acquire_cli

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tools" / "pxapi20b_real_boundary_proof.py"

#: The accepted Agent-team control interpreter and the uv its readiness evidence located.
CONTROL = "/Users/benjaminpoersch/.agt-runner/venv/bin/python"
LIVE_UV = Path("/Users/benjaminpoersch/.local/bin/uv")
SCRATCH_HOME = "/private/tmp/agent-proof-sandbox/home"

SHA = "0123456789abcdef0123456789abcdef01234567"
RUN = "run-0001"
PAGES = ("https://www.rfc-editor.org/", "https://www.rfc-editor.org/about/")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pxapi20b_real_boundary_proof", HARNESS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


proof = _load()


def _forbidden(*_args: object) -> str:
    pytest.fail("uv discovery must not consult the (possibly scratch) home directory")


# --- uv discovery -------------------------------------------------------------------------------


def test_uv_on_path_is_taken_first() -> None:
    asked: list[str] = []

    def which(name: str) -> str | None:
        asked.append(name)
        return "/opt/tools/uv"

    assert proof.find_uv(which, CONTROL, lambda _path: True) == Path("/opt/tools/uv")
    assert asked == ["uv"]


def test_live_uv_is_derived_from_the_control_interpreter_not_from_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", SCRATCH_HOME)
    monkeypatch.setattr(Path, "home", _forbidden)
    monkeypatch.setattr(os.path, "expanduser", _forbidden)

    assert proof.runner_home(Path(CONTROL)) == Path("/Users/benjaminpoersch")
    candidates = proof.uv_candidates(CONTROL, resolve=lambda path: path)
    assert candidates == [Path("/Users/benjaminpoersch/.agt-runner/venv/bin/uv"), LIVE_UV]
    assert not any(str(candidate).startswith(SCRATCH_HOME) for candidate in candidates)

    found = proof.find_uv(lambda _name: None, CONTROL, lambda path: path == LIVE_UV)
    assert found == LIVE_UV


def test_live_uv_is_derived_from_the_resolved_interpreter_too() -> None:
    linked = "/usr/local/bin/python3"
    candidates = proof.uv_candidates(linked, resolve=lambda _path: CONTROL)
    assert candidates == [
        Path("/usr/local/bin/uv"),
        Path("/Users/benjaminpoersch/.agt-runner/venv/bin/uv"),
        LIVE_UV,
    ]


@pytest.mark.parametrize(
    "interpreter",
    [
        "/usr/bin/python3",
        "/opt/homebrew/bin/python3.11",
        "venv/.agt-runner/bin/python",
        "/Users/someone/agt-runner/venv/bin/python",
    ],
)
def test_no_home_is_derived_outside_a_runner_directory(interpreter: str) -> None:
    assert proof.runner_home(Path(interpreter)) is None
    candidates = proof.uv_candidates(interpreter, resolve=lambda path: path)
    assert candidates == [Path(interpreter).parent / "uv"]


def test_uv_on_path_that_is_not_an_executable_file_is_not_accepted() -> None:
    found = proof.find_uv(lambda _name: "/opt/tools/uv", CONTROL, lambda path: path == LIVE_UV)
    assert found == LIVE_UV


def test_uv_is_absent_when_no_candidate_is_an_executable_file() -> None:
    assert proof.find_uv(lambda _name: None, CONTROL, lambda _path: False) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_only_an_existing_executable_regular_file_is_accepted(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "uv"
    directory = tmp_path / "directory" / "uv"
    directory.mkdir(parents=True)
    plain = tmp_path / "plain" / "uv"
    plain.parent.mkdir()
    plain.write_text("#!/bin/sh\n")
    plain.chmod(0o644)
    runnable = tmp_path / "runnable" / "uv"
    runnable.parent.mkdir()
    runnable.write_text("#!/bin/sh\n")
    runnable.chmod(0o755)

    assert not proof.is_executable_file(missing)
    assert not proof.is_executable_file(directory)
    assert not proof.is_executable_file(plain)
    assert proof.is_executable_file(runnable)


def test_a_missing_uv_fails_the_bootstrap_stage(tmp_path: Path) -> None:
    def runner(
        argv: Sequence[str], _cwd: Path, _env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        stdout = SHA + "\n" if list(argv[:2]) == ["git", "rev-parse"] else ""
        return subprocess.CompletedProcess(list(argv), 0, stdout=stdout, stderr="")

    facts: dict[str, Any] = {}
    with pytest.raises(proof.ProofFailure) as failure:
        proof.run_proof(
            tmp_path,
            tmp_path / "proof",
            facts,
            runner=runner,
            environ={},
            which=lambda _name: None,
            executable="/nonexistent-control/bin/python",
        )
    assert failure.value.stage == "bootstrap"
    assert facts["exact_sha"] == SHA
    assert "uv" not in facts


# --- runtime selection and command line ---------------------------------------------------------


def test_the_project_requires_python_admits_both_preferred_pythons() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requires = pyproject["project"]["requires-python"]
    assert proof.PREFERRED_PYTHONS == ((3, 14), (3, 13))
    assert proof.satisfies((3, 14, 0), requires)
    assert proof.satisfies((3, 13, 13), requires)
    assert not proof.satisfies((3, 12, 9), requires)
    assert not proof.satisfies((3, 15, 0), requires)


@pytest.mark.parametrize(
    ("version", "spec", "expected"),
    [
        ((3, 14, 0), ">=3.14", True),
        ((3, 14, 2), ">=3.13,<3.15", True),
        ((3, 13, 7), ">=3.14", False),
        ((3, 15, 0), ">=3.13,<3.15", False),
        ((3, 14), "==3.14.0", True),
        ((3, 14, 1), "!=3.14.1", False),
    ],
)
def test_requires_python_predicate(version: tuple[int, ...], spec: str, expected: bool) -> None:
    assert proof.satisfies(version, spec) is expected


def test_an_unsupported_requires_python_clause_is_refused() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        proof.satisfies((3, 14, 0), "~=3.14")


def test_the_cli_argv_is_exact() -> None:
    argv = proof.cli_argv(Path("/scratch/venv/bin/python"), Path("/checkout/out/canonical"))
    assert argv == [
        "/scratch/venv/bin/python",
        "-m",
        "pxapi.adapters.inbound.acquire_cli",
        "https://www.rfc-editor.org/",
        "--max-selected-pages",
        "3",
        "--output-dir",
        "/checkout/out/canonical",
    ]


def test_the_canonical_files_mirror_the_command_line() -> None:
    produced = {member: name for member, (_c, name) in acquire_cli.PRODUCED_DOCUMENTS.items()}
    assert produced == proof.CANONICAL_FILES
    assert acquire_cli.RECEIPT_FILE == proof.CLI_RECEIPT
    plural = {member for member, shape in acquire_cli.CONTAINER_SHAPES.items() if shape is list}
    assert plural == proof.LIST_MEMBERS


# --- the canonical bundle -----------------------------------------------------------------------


def _envelope(pages: Sequence[str] = PAGES) -> dict[str, Any]:
    ranks = list(enumerate(pages, start=1))
    return {
        "analysis_run_request": {"run_id": RUN},
        "analysis_run_state": {"run_id": RUN, "state": "SUCCEEDED"},
        "stage_executions": [{"run_id": RUN, "stage": "PAGE_ACQUISITION"}],
        "site_inventory": {"run_id": RUN, "inventory_id": "inv-1", "output_digest": "sha256:i"},
        "sampling_manifest": {
            "run_id": RUN,
            "sampling_manifest_id": "man-1",
            "inventory_ref": "inv-1",
            "inventory_output_digest": "sha256:i",
            "budgets": {"max_selected_pages": 3},
            "selections": [{"url_key": key, "selection_rank": rank} for rank, key in ranks],
            "selection_complete": True,
            "incompleteness": [],
            "input_digest": "sha256:mi",
            "output_digest": "sha256:mo",
        },
        "page_acquisitions": [
            {
                "run_id": RUN,
                "acquisition_id": f"acq-{rank}",
                "url_key": key,
                "sampling_manifest_ref": "man-1",
                "sampling_manifest_output_digest": "sha256:mo",
                "acquisition_outcome": "RESPONSE_RECEIVED",
                "http_status": 200,
                "measurement_refs": [f"m-{rank}"],
            }
            for rank, key in ranks
        ],
        "measurements": [
            {"run_id": RUN, "measurement_id": f"m-{rank}", "assessment": _assessment(rank)}
            for rank, _key in ranks
        ],
        "website_evidence": [
            {"run_id": RUN, "evidence_id": f"e-{rank}", "measurement_refs": [f"m-{rank}"]}
            for rank, _key in ranks
        ],
    }


def _assessment(rank: int) -> dict[str, str]:
    if rank == 1:
        return {"result_state": "KNOWN"}
    return {"result_state": "NOT_ASSESSED", "not_assessed_reason": "UNSUPPORTED"}


def _receipt(envelope: dict[str, Any]) -> dict[str, Any]:
    selections = envelope["sampling_manifest"]["selections"]
    return {
        "run_id": envelope["analysis_run_state"]["run_id"],
        "run_state": envelope["analysis_run_state"]["state"],
        "pages": [{"url_key": selection["url_key"]} for selection in selections],
        "sampling_manifest": {"selected_count": len(selections)},
        "document_digests": {"page_acquisitions": {"count": len(selections), "digest": "d"}},
    }


def _rendered(envelope: dict[str, Any]) -> tuple[dict[str, bytes], str]:
    files = {
        name: json.dumps(envelope[member]).encode("utf-8")
        for member, name in proof.CANONICAL_FILES.items()
    }
    files[proof.CLI_RECEIPT] = json.dumps(_receipt(envelope)).encode("utf-8")
    return files, json.dumps(envelope)


def _expected_rows(pages: Sequence[str] = PAGES) -> list[dict[str, Any]]:
    return [
        {
            "selection_rank": rank,
            "url_key": key,
            "acquisition_id": f"acq-{rank}",
            "acquisition_outcome": "RESPONSE_RECEIVED",
            "http_status": 200,
            "measurement_refs": [f"m-{rank}"],
            "evidence_refs": [f"e-{rank}"],
            "not_assessed_reasons": [] if rank == 1 else ["UNSUPPORTED"],
            "measurements_withheld_reason": None,
        }
        for rank, key in enumerate(pages, start=1)
    ]


def test_a_coherent_multi_page_bundle_is_accepted() -> None:
    files, stdout = _rendered(_envelope())
    problems, summary = proof.check_bundle(files, stdout, proof.MAX_SELECTED_PAGES)
    assert problems == []
    assert summary["linked_page_refs"] == list(PAGES)
    assert summary["pages"] == _expected_rows()
    assert summary["run"]["run_id"] == RUN
    assert summary["run"]["state"] == "SUCCEEDED"


def test_a_one_page_bundle_is_rejected() -> None:
    files, stdout = _rendered(_envelope(PAGES[:1]))
    problems, _summary = proof.check_bundle(files, stdout, proof.MAX_SELECTED_PAGES)
    assert "only 1 page(s) selected; at least 2 needed" in problems
    assert any("resolves for 1 page(s)" in problem for problem in problems)


def test_a_missing_file_is_rejected() -> None:
    files, stdout = _rendered(_envelope())
    del files["website-evidence.json"]
    problems, summary = proof.check_bundle(files, stdout, proof.MAX_SELECTED_PAGES)
    assert problems == ["website-evidence.json: missing"]
    assert summary == {}


def test_an_extra_file_is_rejected() -> None:
    files, stdout = _rendered(_envelope())
    files["stray.json"] = b"{}"
    problems, summary = proof.check_bundle(files, stdout, proof.MAX_SELECTED_PAGES)
    assert problems == ["stray.json: not part of the bundle"]
    assert summary == {}


def test_a_document_of_another_run_is_rejected() -> None:
    envelope = _envelope()
    envelope["measurements"][1]["run_id"] = "run-0002"
    files, stdout = _rendered(envelope)
    problems, _summary = proof.check_bundle(files, stdout, proof.MAX_SELECTED_PAGES)
    assert problems == ["measurement-records.json/1: belongs to another run"]


def test_broken_evidence_linkage_is_rejected() -> None:
    envelope = _envelope()
    envelope["website_evidence"][1]["measurement_refs"] = ["m-unknown"]
    files, stdout = _rendered(envelope)
    problems, summary = proof.check_bundle(files, stdout, proof.MAX_SELECTED_PAGES)
    assert "evidence e-2: not linked to exactly one page" in problems
    assert any("resolves for 1 page(s)" in problem for problem in problems)
    assert summary["linked_page_refs"] == [PAGES[0]]


def test_a_printed_envelope_that_differs_from_the_files_is_rejected() -> None:
    files, _stdout = _rendered(_envelope())
    problems, _summary = proof.check_bundle(files, json.dumps(_envelope(PAGES[:1])), 3)
    assert "stdout: the printed envelope differs from the files written" in problems


# --- the proof receipt --------------------------------------------------------------------------


def _minor(request: str) -> str:
    """The preferred minor a ``uv python find`` request pins (``...,==3.14.*`` -> ``"3.14"``)."""
    match = re.search(r"==(\d+\.\d+)\.\*$", request)
    assert match is not None, f"request pins no minor: {request!r}"
    return match.group(1)


class ScriptedHost:
    """Answers every command the proof issues as a healthy host would, and records them.

    ``installed`` maps the minor a ``uv python find`` request pins (``"3.14"``) to the release
    the interpreter it names reports; the interpreter lives in ``<tmp>/python<minor>/bin``. Like
    real ``uv python find --system``, a request is answered as uv does when nothing is installed
    unless that directory is on the ``PATH`` the lookup was given. The project venv reports the
    synced interpreter's release unless ``project_version`` says otherwise.
    """

    def __init__(
        self,
        tmp_path: Path,
        installed: Mapping[str, Sequence[int]] | None = None,
        *,
        project_version: Sequence[int] | None = None,
        managed_dir: Path | None = None,
        lock_rewrite: tuple[Path, bytes] | None = None,
    ) -> None:
        self.uv = tmp_path / "bin" / "uv"
        self.uv.parent.mkdir()
        self.uv.write_text("#!/bin/sh\nexit 1\n")
        self.uv.chmod(0o755)
        self.trust_bundle = tmp_path / "cacert.pem"
        self.trust_bundle.write_text("certificates\n")
        installed = {"3.14": (3, 14, 0)} if installed is None else installed
        self.pythons = {
            request: (tmp_path / f"python{request}" / "bin" / f"python{request}", list(info))
            for request, info in installed.items()
        }
        self.project_version = None if project_version is None else list(project_version)
        self.managed_dir = managed_dir
        self.lock_rewrite = lock_rewrite
        self.synced: str | None = None
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []

    def python(self, request: str) -> Path:
        return self.pythons[request][0]

    def search_path(self) -> str:
        """A ``PATH`` on which every installed interpreter is visible, as on a healthy host."""
        return os.pathsep.join(
            ["/usr/bin", *(str(path.parent) for path, _ in self.pythons.values())]
        )

    def _visible(self, request: str, env: Mapping[str, str]) -> bool:
        if _minor(request) not in self.pythons:
            return False
        entries = env.get("PATH", "").split(os.pathsep)
        return str(self.python(_minor(request)).parent) in entries

    def __call__(
        self, argv: Sequence[str], _cwd: Path, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        argv = list(argv)
        self.calls.append(argv)
        self.envs.append(dict(env))
        if argv[:3] == [str(self.uv), "python", "find"] and not self._visible(argv[-1], env):
            stderr = f"error: No interpreter found for Python {argv[-1]} in system path\n"
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr=stderr)
        if argv[:3] == [str(self.uv), "python", "dir"] and (
            "UV_CONFIG_FILE" in env or "UV_PROJECT" in env
        ):
            # Real uv exits 2 on an unreadable UV_CONFIG_FILE or a UV_PROJECT without a project.
            stderr = "error: Failed to parse the configured uv settings\n"
            return subprocess.CompletedProcess(argv, 2, stdout="", stderr=stderr)
        return subprocess.CompletedProcess(argv, 0, stdout=self._answer(argv, env), stderr="")

    def _answer(self, argv: list[str], env: Mapping[str, str]) -> str:
        if argv[:2] == ["git", "rev-parse"]:
            return SHA + "\n"
        if argv[:2] == ["git", "status"]:
            return ""
        if argv[0] == str(self.uv):
            if argv[1] == "--version":
                return "uv 0.9.99\n"
            if argv[1:3] == ["python", "find"]:
                return f"{self.python(_minor(argv[-1]))}\n"
            if argv[1:3] == ["python", "dir"]:
                install_dir = env.get("UV_PYTHON_INSTALL_DIR", self.managed_dir or "/nowhere")
                return f"{install_dir}\n"
            if argv[1] == "sync":
                self.synced = argv[argv.index("--python") + 1]
                if self.lock_rewrite is not None:
                    self.lock_rewrite[0].write_bytes(self.lock_rewrite[1])
                return ""
        if argv[1:3] == ["-c", proof.PROBE]:
            by_path = {str(path): info for path, info in self.pythons.values()}
            if argv[0] in by_path:
                prefix, info = "/usr/local", by_path[argv[0]]
            else:
                assert argv[0] == str(proof.venv_python(Path(env["UV_PROJECT_ENVIRONMENT"])))
                assert self.synced is not None, "the venv is probed only after uv sync"
                prefix = env["UV_PROJECT_ENVIRONMENT"]
                info = self.project_version or by_path[self.synced]
            version = ".".join(str(part) for part in info)
            probe = {"prefix": prefix, "version": version, "version_info": info}
            return json.dumps({"executable": argv[0], **probe}) + "\n"
        if argv[1:3] == ["-c", proof.CERTIFI_PROBE]:
            return f"{self.trust_bundle}\n"
        if argv[1:3] == ["-m", proof.CLI_MODULE]:
            output = Path(argv[-1])
            output.mkdir(parents=True)
            files, stdout = _rendered(_envelope())
            for name, data in files.items():
                (output / name).write_bytes(data)
            return stdout
        raise AssertionError(f"unexpected command {argv}")


def _checkout(tmp_path: Path, requires: str = ">=3.13,<3.15") -> Path:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "pyproject.toml").write_text(f'[project]\nrequires-python = "{requires}"\n')
    (root / "uv.lock").write_bytes(b"version = 1\n")
    return root


WellKnown = Callable[[Sequence[int]], Sequence[Path]]


def _no_well_known(_wanted: Sequence[int]) -> list[Path]:
    """A host whose well-known directories add nothing: only the inherited ``PATH`` counts."""
    return []


def _run(
    root: Path,
    host: ScriptedHost,
    facts: dict[str, Any],
    *,
    path: str | None = None,
    well_known: WellKnown = _no_well_known,
) -> None:
    proof.run_proof(
        root,
        root / proof.PROOF_DIR,
        facts,
        runner=host,
        environ={
            "PATH": host.search_path() if path is None else path,
            "HOME": SCRATCH_HOME,
            "VIRTUAL_ENV": "/elsewhere",
        },
        which=lambda _name: str(host.uv),
        executable=CONTROL,
        expected_sha=SHA,
        system_directories=well_known,
    )


def _failed(
    root: Path,
    host: ScriptedHost,
    *,
    path: str | None = None,
    well_known: WellKnown = _no_well_known,
) -> tuple[proof.ProofFailure, dict[str, Any]]:
    facts: dict[str, Any] = {}
    with pytest.raises(proof.ProofFailure) as failure:
        _run(root, host, facts, path=path, well_known=well_known)
    assert not any(call[1:3] == ["-m", proof.CLI_MODULE] for call in host.calls)
    return failure.value, facts


def _finds(host: ScriptedHost) -> list[str]:
    return [call[-1] for call in host.calls if call[1:3] == ["python", "find"]]


def _find_paths(host: ScriptedHost) -> list[str]:
    """The ``PATH`` each ``uv python find`` was given, in lookup order."""
    return [
        env.get("PATH", "")
        for call, env in zip(host.calls, host.envs, strict=True)
        if call[1:3] == ["python", "find"]
    ]


def _inherited_only(path: str) -> dict[str, list[str]]:
    """The search-path provenance when no well-known directory was considered."""
    return {
        "inherited": path.split(os.pathsep),
        "well_known": [],
        "added": [],
        "absent": [],
        "excluded": [],
        "already_present": [],
    }


def _synced(host: ScriptedHost) -> list[list[str]]:
    return [call for call in host.calls if call[1:2] == ["sync"]]


def test_a_passing_proof_receipt_preserves_every_recorded_fact(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path)
    proof_dir = root / proof.PROOF_DIR
    facts: dict[str, Any] = {}
    proof.run_proof(
        root,
        proof_dir,
        facts,
        runner=host,
        environ={"PATH": host.search_path()},
        which=lambda _name: str(host.uv),
        executable=CONTROL,
        expected_sha=SHA,
        system_directories=_no_well_known,
    )
    receipt = json.loads(json.dumps(proof.build_receipt(facts, None)))

    lock_digest = "sha256:" + hashlib.sha256(b"version = 1\n").hexdigest()
    assert receipt["verdict"] == "PASSED"
    assert receipt["failure"] is None
    assert receipt["exact_sha"] == SHA
    assert receipt["control_runtime"]["executable"] == CONTROL
    assert receipt["uv"] == {"path": str(host.uv), "version": "uv 0.9.99"}
    assert receipt["selected_python"] == {
        "path": str(host.python("3.14")),
        "version": "3.14.0",
        "requires_python": ">=3.13,<3.15",
    }
    assert receipt["python_candidates"] == [
        {
            "requested": "3.14",
            "request": ">=3.13,<3.15,==3.14.*",
            "search_path": _inherited_only(host.search_path()),
            "path": str(host.python("3.14")),
            "discovered_via": f"inherited PATH entry {host.python('3.14').parent}",
            "version": "3.14.0",
            "outcome": "selected",
        }
    ]
    assert receipt["project_runtime"]["version"] == "3.14.0"
    assert receipt["requires_python"] == ">=3.13,<3.15"
    assert receipt["lock"] == {
        "sha256_before": lock_digest,
        "sha256_after": lock_digest,
        "unchanged": True,
    }
    assert receipt["target"] == "https://www.rfc-editor.org/"
    assert receipt["max_selected_pages"] == 3
    argv = receipt["cli"]["argv"]
    assert argv[3:6] == ["https://www.rfc-editor.org/", "--max-selected-pages", "3"]
    assert argv[-1] == str(proof_dir / proof.CANONICAL_DIR)
    assert receipt["pages"] == _expected_rows()
    assert receipt["linked_page_refs"] == list(PAGES)
    assert receipt["problems"] == []
    assert receipt["evidence_ceiling"] == proof.EVIDENCE_CEILING
    assert set(receipt["file_digests"]) == {*proof.CANONICAL_FILES.values(), proof.CLI_RECEIPT}
    sync = next(call for call in host.calls if call[1:2] == ["sync"])
    assert sync[2] == "--locked"
    assert "--no-python-downloads" in sync


# --- interpreter selection ----------------------------------------------------------------------


def test_an_installed_3_14_is_preferred_over_an_installed_3_13(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.14": (3, 14, 1), "3.13": (3, 13, 13)})
    facts: dict[str, Any] = {}
    _run(root, host, facts)

    assert _finds(host) == [">=3.13,<3.15,==3.14.*"]
    assert facts["selected_python"]["path"] == str(host.python("3.14"))
    assert facts["selected_python"]["version"] == "3.14.1"
    (sync,) = _synced(host)
    assert sync[sync.index("--python") + 1] == str(host.python("3.14"))
    assert facts["project_runtime"]["version"] == "3.14.1"


def test_an_installed_3_13_is_the_automatic_fallback_when_3_14_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    monkeypatch.setattr(Path, "home", _forbidden)
    monkeypatch.setattr(os.path, "expanduser", _forbidden)
    facts: dict[str, Any] = {}
    _run(root, host, facts)
    receipt = json.loads(json.dumps(proof.build_receipt(facts, None)))

    assert receipt["verdict"] == "PASSED"
    assert _finds(host) == [">=3.13,<3.15,==3.14.*", ">=3.13,<3.15,==3.13.*"]
    assert receipt["python_candidates"] == [
        {
            "requested": "3.14",
            "request": ">=3.13,<3.15,==3.14.*",
            "search_path": _inherited_only(host.search_path()),
            "outcome": "not installed",
        },
        {
            "requested": "3.13",
            "request": ">=3.13,<3.15,==3.13.*",
            "search_path": _inherited_only(host.search_path()),
            "path": str(host.python("3.13")),
            "discovered_via": f"inherited PATH entry {host.python('3.13').parent}",
            "version": "3.13.13",
            "outcome": "selected",
        },
    ]
    assert receipt["selected_python"] == {
        "path": str(host.python("3.13")),
        "version": "3.13.13",
        "requires_python": ">=3.13,<3.15",
    }
    assert receipt["requires_python"] == ">=3.13,<3.15"
    assert receipt["project_runtime"]["version"] == "3.13.13"
    (sync,) = _synced(host)
    assert sync[sync.index("--python") + 1] == str(host.python("3.13"))
    assert receipt["pages"] == _expected_rows()
    assert receipt["evidence_ceiling"] == proof.EVIDENCE_CEILING


@pytest.mark.parametrize(
    ("requires", "installed", "outcome_3_14"),
    [
        # The 3.14 uv names reports another release: rejected, 3.13 taken.
        (">=3.13,<3.15", {"3.14": (3, 12, 9), "3.13": (3, 13, 13)}, "rejected: not Python 3.14"),
        # A checkout whose requires-python excludes 3.14 falls back to 3.13.
        (
            ">=3.13,<3.14",
            {"3.14": (3, 14, 0), "3.13": (3, 13, 13)},
            "rejected: does not satisfy >=3.13,<3.14",
        ),
    ],
    ids=["wrong-release", "outside-requires-python"],
)
def test_an_incompatible_3_14_falls_back_to_a_compatible_3_13(
    tmp_path: Path, requires: str, installed: dict[str, Sequence[int]], outcome_3_14: str
) -> None:
    root = _checkout(tmp_path, requires)
    host = ScriptedHost(tmp_path, installed)
    facts: dict[str, Any] = {}
    _run(root, host, facts)

    first, second = facts["python_candidates"]
    assert first["outcome"] == outcome_3_14
    assert second["outcome"] == "selected"
    assert facts["selected_python"]["path"] == str(host.python("3.13"))
    assert facts["requires_python"] == requires


def test_a_uv_managed_candidate_is_rejected(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(
        tmp_path,
        {"3.14": (3, 14, 0), "3.13": (3, 13, 13)},
        managed_dir=tmp_path / "python3.14",
    )
    host.python("3.14").parent.mkdir(parents=True)
    facts: dict[str, Any] = {}
    _run(root, host, facts)

    assert facts["python_candidates"][0]["outcome"] == "rejected: uv-managed Python"
    assert facts["selected_python"]["path"] == str(host.python("3.13"))
    assert not any(call[0] == str(host.python("3.14")) for call in host.calls)


@pytest.mark.parametrize(
    ("requires", "installed", "outcomes"),
    [
        (">=3.13,<3.15", {}, ["not installed", "not installed"]),
        (
            ">=3.13,<3.15",
            {"3.14": (3, 15, 0), "3.13": (3, 12, 9)},
            ["rejected: not Python 3.14", "rejected: not Python 3.13"],
        ),
        (
            ">=3.15",
            {"3.14": (3, 14, 0), "3.13": (3, 13, 13)},
            ["rejected: does not satisfy >=3.15", "rejected: does not satisfy >=3.15"],
        ),
    ],
    ids=["missing", "wrong-releases", "outside-requires-python"],
)
def test_no_compatible_installed_python_fails_the_bootstrap_before_any_sync(
    tmp_path: Path, requires: str, installed: dict[str, Sequence[int]], outcomes: list[str]
) -> None:
    root = _checkout(tmp_path, requires)
    host = ScriptedHost(tmp_path, installed)
    failure, facts = _failed(root, host)

    assert failure.stage == "bootstrap"
    assert "no installed system Python (3.14, 3.13) satisfies" in failure.detail
    assert [entry["outcome"] for entry in facts["python_candidates"]] == outcomes
    assert "selected_python" not in facts
    assert _synced(host) == []
    receipt = proof.build_receipt(facts, failure)
    assert receipt["verdict"] == "FAILED"
    assert receipt["failure"]["stage"] == "bootstrap"
    assert receipt["exact_sha"] == SHA
    assert receipt["requires_python"] == requires
    assert receipt["evidence_ceiling"] == proof.EVIDENCE_CEILING


def test_an_unsupported_requires_python_fails_the_bootstrap(tmp_path: Path) -> None:
    root = _checkout(tmp_path, "~=3.14")
    host = ScriptedHost(tmp_path)
    failure, _facts = _failed(root, host)
    assert failure.stage == "bootstrap"
    assert "unsupported" in failure.detail
    assert _finds(host) == []


def test_every_uv_call_is_locked_system_only_and_isolated(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    facts: dict[str, Any] = {}
    _run(root, host, facts)

    (sync,) = _synced(host)
    assert sync[2] == "--locked"
    assert sync[sync.index("--python-preference") + 1] == "only-system"
    assert "--no-python-downloads" in sync
    for call, env in zip(host.calls, host.envs, strict=True):
        if call[1:2] in (["python"], ["sync"]):
            assert env["UV_PYTHON_DOWNLOADS"] == "never"
            assert "VIRTUAL_ENV" not in env
            scratch = Path(env["UV_PROJECT_ENVIRONMENT"]).parent
            assert not scratch.is_relative_to(root)
            assert Path(env["UV_CACHE_DIR"]).parent == scratch
        if call[1:3] == ["python", "dir"]:
            assert call == proof.managed_dir_argv(host.uv)
            assert not proof.DISCOVERY_DROPPED & set(env)
        elif call[1:3] == ["python", "find"]:
            assert call[3:-1] == list(proof.SYSTEM_FIND)
            assert not proof.DISCOVERY_DROPPED & set(env)
        elif call[1:2] in (["python"], ["sync"]):
            assert env["UV_PYTHON_PREFERENCE"] == "only-system"
    assert facts["lock"]["unchanged"] is True


def test_the_discovery_argv_is_the_runner_proven_system_only_form() -> None:
    assert proof.SYSTEM_FIND == (
        "--no-config",
        "--no-project",
        "--system",
        "--no-managed-python",
        "--no-python-downloads",
    )
    assert proof.find_argv(Path("/opt/bin/uv"), ">=3.13,<3.15,==3.13.*") == [
        "/opt/bin/uv",
        "python",
        "find",
        "--no-config",
        "--no-project",
        "--system",
        "--no-managed-python",
        "--no-python-downloads",
        ">=3.13,<3.15,==3.13.*",
    ]
    assert proof.managed_dir_argv(Path("/opt/bin/uv")) == [
        "/opt/bin/uv",
        "python",
        "dir",
        "--no-config",
    ]
    assert "UV_PYTHON_INSTALL_DIR" in proof.DISCOVERY_DROPPED


@pytest.mark.parametrize(
    ("requires", "wanted", "python_request"),
    [
        (">=3.13,<3.15", (3, 14), ">=3.13,<3.15,==3.14.*"),
        (">=3.13,<3.15", (3, 13), ">=3.13,<3.15,==3.13.*"),
        (" >=3.13 , <3.15 ", (3, 13), ">=3.13,<3.15,==3.13.*"),
        (">=3.13,<3.14", (3, 14), ">=3.13,<3.14,==3.14.*"),
    ],
)
def test_the_discovery_request_intersects_requires_python_with_the_minor(
    requires: str, wanted: tuple[int, int], python_request: str
) -> None:
    assert proof.python_request(requires, wanted) == python_request


def test_discovery_ignores_host_uv_configuration_and_python_pins(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    (root / ".python-version").write_text("3.12\n")
    (root / "uv.toml").write_text('python-preference = "only-managed"\n')
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    environ = {
        "PATH": host.search_path(),
        "UV_PYTHON": "3.12",
        "UV_PYTHON_PREFERENCE": "only-managed",
        "UV_MANAGED_PYTHON": "1",
        "UV_NO_MANAGED_PYTHON": "0",
        "UV_CONFIG_FILE": str(root / "uv.toml"),
        "UV_PROJECT": str(root),
        # Would make every installed system Python look uv-managed.
        "UV_PYTHON_INSTALL_DIR": str(tmp_path),
    }
    facts: dict[str, Any] = {}
    proof.run_proof(
        root,
        root / proof.PROOF_DIR,
        facts,
        runner=host,
        environ=environ,
        which=lambda _name: str(host.uv),
        executable=CONTROL,
        expected_sha=SHA,
        system_directories=_no_well_known,
    )

    probes = [
        (call, env)
        for call, env in zip(host.calls, host.envs, strict=True)
        if call[1:3] == ["python", "dir"]
    ]
    assert [call for call, _env in probes] == [proof.managed_dir_argv(host.uv)]
    for _call, env in probes:
        assert not proof.DISCOVERY_DROPPED & set(env)
        assert env["UV_PYTHON_DOWNLOADS"] == "never"
    finds = [
        (call, env)
        for call, env in zip(host.calls, host.envs, strict=True)
        if call[1:3] == ["python", "find"]
    ]
    assert [call for call, _env in finds] == [
        proof.find_argv(host.uv, ">=3.13,<3.15,==3.14.*"),
        proof.find_argv(host.uv, ">=3.13,<3.15,==3.13.*"),
    ]
    for _call, env in finds:
        assert not proof.DISCOVERY_DROPPED & set(env)
        assert env["UV_PYTHON_DOWNLOADS"] == "never"
    assert facts["selected_python"]["path"] == str(host.python("3.13"))
    assert facts["selected_python"]["version"] == "3.13.13"


def test_a_lock_rewritten_by_the_sync_fails_the_bootstrap(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, lock_rewrite=(root / "uv.lock", b"version = 2\n"))
    failure, facts = _failed(root, host)
    assert failure.stage == "bootstrap"
    assert "uv.lock changed" in failure.detail
    assert facts["lock"]["unchanged"] is False
    assert facts["lock"]["sha256_before"] != facts["lock"]["sha256_after"]


@pytest.mark.parametrize(
    ("installed", "project_version", "detail"),
    [
        ({"3.14": (3, 14, 0)}, (3, 15, 0), "is outside >=3.13,<3.15"),
        ({"3.14": (3, 14, 0)}, (3, 12, 9), "is outside >=3.13,<3.15"),
        ({"3.14": (3, 14, 0)}, (3, 13, 13), "not the selected Python"),
        ({"3.13": (3, 13, 13)}, (3, 14, 0), "not the selected Python"),
    ],
)
def test_the_project_runtime_is_validated_against_requires_python(
    tmp_path: Path,
    installed: dict[str, Sequence[int]],
    project_version: Sequence[int],
    detail: str,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, installed, project_version=project_version)
    failure, facts = _failed(root, host)
    assert failure.stage == "runtime"
    assert detail in failure.detail
    expected = ".".join(str(part) for part in project_version)
    assert facts["project_runtime"]["version"] == expected


def test_a_project_runtime_on_another_patch_release_is_accepted(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 12)}, project_version=(3, 13, 13))
    facts: dict[str, Any] = {}
    _run(root, host, facts)
    assert facts["project_runtime"]["version"] == "3.13.13"
    assert facts["problems"] == []


# --- well-known system directories --------------------------------------------------------------

HOMEBREW_3_13 = Path("/opt/homebrew/opt/python@3.13/bin")
HOMEBREW_3_14 = Path("/opt/homebrew/opt/python@3.14/bin")
EMPTY_PROVENANCE: dict[str, list[str]] = {
    "inherited": [],
    "well_known": [],
    "added": [],
    "absent": [],
    "excluded": [],
    "already_present": [],
}


def _lay_out(host: ScriptedHost) -> None:
    """Create the installed interpreters' directories, so they can be well-known directories."""
    for path, _info in host.pythons.values():
        path.parent.mkdir(parents=True, exist_ok=True)


def _simulated_well_known(tmp_path: Path) -> WellKnown:
    """Well-known directories laid out like the scripted host's interpreters.

    ``<tmp>/python<minor>/bin`` plays Homebrew's minor-specific ``opt/python@<minor>/bin`` and
    ``<tmp>/usr/bin`` the generic system location; neither is on the sandbox ``PATH``.
    """

    def well_known(wanted: Sequence[int]) -> list[Path]:
        minor = ".".join(str(part) for part in wanted)
        return [tmp_path / f"python{minor}" / "bin", tmp_path / "usr" / "bin"]

    return well_known


def test_the_macos_well_known_directories_cover_homebrew_and_the_system_locations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", SCRATCH_HOME)
    monkeypatch.setattr(Path, "home", _forbidden)
    monkeypatch.setattr(os.path, "expanduser", _forbidden)

    for_3_13 = proof.system_python_directories((3, 13), "darwin")
    for_3_14 = proof.system_python_directories((3, 14), "darwin")

    assert for_3_13[0] == HOMEBREW_3_13
    assert for_3_14[0] == HOMEBREW_3_14
    assert Path("/usr/local/opt/python@3.14/bin") in for_3_14
    assert Path("/Library/Frameworks/Python.framework/Versions/3.14/bin") in for_3_14
    assert for_3_13[-4:] == [
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/opt/local/bin"),
        Path("/usr/bin"),
    ]
    assert for_3_13 == proof.system_python_directories((3, 13), "darwin")
    assert len(set(for_3_13)) == len(for_3_13)
    for directory in [*for_3_13, *for_3_14]:
        assert directory.is_absolute()
        assert not str(directory).startswith((SCRATCH_HOME, "/Users", "~"))
        assert not {".venv", ".python-version", ".local", ".agt-runner"} & set(directory.parts)


def test_the_other_platforms_name_fixed_system_locations_only() -> None:
    posix = [Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin")]
    assert proof.system_python_directories((3, 13), "linux") == posix
    assert proof.system_python_directories((3, 14), "freebsd14") == posix
    assert proof.system_python_directories((3, 14), "win32") == [
        Path("C:\\Program Files\\Python314"),
        Path("C:\\Python314"),
    ]
    assert proof.system_python_directories((3, 13)) == proof.system_python_directories(
        (3, 13), sys.platform
    )


def test_the_proof_uses_the_platform_well_known_directories_by_default() -> None:
    assert proof.run_proof.__kwdefaults__["system_directories"] is proof.system_python_directories
    assert proof.select_python.__defaults__ == (proof.system_python_directories,)


def test_the_lookup_path_appends_existing_well_known_directories_once_in_order(
    tmp_path: Path,
) -> None:
    homebrew = tmp_path / "opt" / "homebrew" / "opt" / "python@3.14" / "bin"
    usr_local = tmp_path / "usr" / "local" / "bin"
    absent = tmp_path / "Library" / "Frameworks" / "Python.framework" / "Versions" / "3.14" / "bin"
    usr_bin = tmp_path / "usr" / "bin"
    for directory in (homebrew, usr_local, usr_bin):
        directory.mkdir(parents=True)
    inherited = [f"{usr_bin}{os.sep}", "/sandbox/bin"]

    search_path, provenance = proof.find_search_path(
        os.pathsep.join(inherited), [homebrew, usr_bin, absent, homebrew, usr_local], []
    )

    assert search_path == os.pathsep.join([*inherited, str(homebrew), str(usr_local)])
    assert provenance == {
        "inherited": inherited,
        "well_known": [str(homebrew), str(usr_bin), str(absent), str(usr_local)],
        "added": [str(homebrew), str(usr_local)],
        "absent": [str(absent)],
        "excluded": [],
        "already_present": [str(usr_bin)],
    }


def test_the_lookup_path_excludes_managed_and_project_environment_directories(
    tmp_path: Path,
) -> None:
    managed = tmp_path / "managed"
    managed_bin = managed / "cpython-3.14.0-macos-aarch64-none" / "bin"
    venv_bin = tmp_path / "scratch" / "venv" / "bin"
    system = tmp_path / "usr" / "bin"
    for directory in (managed_bin, venv_bin, system):
        directory.mkdir(parents=True)
    link = tmp_path / "opt" / "python@3.14"
    link.parent.mkdir()
    link.symlink_to(managed_bin.parent)
    excluded = [Path(os.path.realpath(managed)), Path(os.path.realpath(venv_bin.parent))]

    search_path, provenance = proof.find_search_path(
        "/sandbox/bin", [managed_bin, venv_bin, link / "bin", system], excluded
    )

    assert search_path == os.pathsep.join(["/sandbox/bin", str(system)])
    assert provenance["excluded"] == [str(managed_bin), str(venv_bin), str(link / "bin")]
    assert provenance["added"] == [str(system)]
    assert provenance["absent"] == []


def test_an_absent_inherited_path_yields_only_the_well_known_directories(tmp_path: Path) -> None:
    system = tmp_path / "usr" / "bin"
    system.mkdir(parents=True)
    missing = tmp_path / "missing"

    search_path, provenance = proof.find_search_path(None, [system, missing], [])

    assert search_path == str(system)
    assert provenance["inherited"] == []
    assert provenance["added"] == [str(system)]
    assert provenance["absent"] == [str(missing)]
    assert proof.find_search_path("", [], []) == ("", EMPTY_PROVENANCE)


def test_discovery_is_attributed_to_the_entry_that_names_the_interpreter(tmp_path: Path) -> None:
    cellar = tmp_path / "Cellar" / "python@3.13" / "3.13.13" / "bin"
    cellar.mkdir(parents=True)
    (cellar / "python3.13").write_text("")
    opt = tmp_path / "opt" / "python@3.13"
    opt.parent.mkdir()
    opt.symlink_to(cellar.parent)
    provenance = {"inherited": ["/usr/bin"], "added": [str(opt / "bin")]}

    well_known = f"well-known directory {opt / 'bin'}"
    assert proof.discovered_via(opt / "bin" / "python3.13", provenance) == well_known
    # uv may print the resolved interpreter; the link in the added directory still names it.
    assert proof.discovered_via(cellar / "python3.13", provenance) == well_known
    assert (
        proof.discovered_via(Path("/usr/bin/python3.13"), provenance)
        == "inherited PATH entry /usr/bin"
    )
    assert (
        proof.discovered_via(tmp_path / "elsewhere" / "python3.13", provenance)
        == "not attributable to a search-path entry"
    )


def test_a_path_that_hides_every_interpreter_is_augmented_for_each_lookup_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.14": (3, 14, 0), "3.13": (3, 13, 13)})
    _lay_out(host)
    usr_bin = tmp_path / "usr" / "bin"
    usr_bin.mkdir(parents=True)
    monkeypatch.setenv("HOME", SCRATCH_HOME)
    monkeypatch.setattr(Path, "home", _forbidden)
    monkeypatch.setattr(os.path, "expanduser", _forbidden)
    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path))
    receipt = json.loads(json.dumps(proof.build_receipt(facts, None)))

    assert receipt["verdict"] == "PASSED"
    homebrew_like = host.python("3.14").parent
    assert _find_paths(host) == [
        os.pathsep.join(["/sandbox/bin", str(homebrew_like), str(usr_bin)])
    ]
    assert receipt["python_candidates"] == [
        {
            "requested": "3.14",
            "request": ">=3.13,<3.15,==3.14.*",
            "search_path": {
                "inherited": ["/sandbox/bin"],
                "well_known": [str(homebrew_like), str(usr_bin)],
                "added": [str(homebrew_like), str(usr_bin)],
                "absent": [],
                "excluded": [],
                "already_present": [],
            },
            "path": str(host.python("3.14")),
            "discovered_via": f"well-known directory {homebrew_like}",
            "version": "3.14.0",
            "outcome": "selected",
        }
    ]
    assert receipt["selected_python"]["path"] == str(host.python("3.14"))
    # The interpreter uv named was still probed, and the sync still ran locked against it.
    assert [str(host.python("3.14")), "-c", proof.PROBE] in host.calls
    (sync,) = _synced(host)
    assert sync[2] == "--locked"
    assert sync[sync.index("--python") + 1] == str(host.python("3.14"))
    # Only the find lookups see the augmented PATH; every other command keeps the sandbox PATH.
    for call, env in zip(host.calls, host.envs, strict=True):
        if call[1:3] != ["python", "find"]:
            assert env["PATH"] == "/sandbox/bin"
    assert not any(SCRATCH_HOME in path for path in _find_paths(host))


def test_a_hidden_3_13_is_found_when_the_3_14_well_known_directory_is_absent(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    _lay_out(host)
    usr_bin = tmp_path / "usr" / "bin"
    usr_bin.mkdir(parents=True)
    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path))

    first, second = facts["python_candidates"]
    assert first["outcome"] == "not installed"
    assert first["search_path"]["absent"] == [str(tmp_path / "python3.14" / "bin")]
    assert first["search_path"]["added"] == [str(usr_bin)]
    assert "path" not in first
    homebrew_like = host.python("3.13").parent
    assert second["outcome"] == "selected"
    assert second["search_path"]["added"] == [str(homebrew_like), str(usr_bin)]
    assert second["search_path"]["absent"] == []
    assert second["discovered_via"] == f"well-known directory {homebrew_like}"
    paths = _find_paths(host)
    assert paths == [
        os.pathsep.join(["/sandbox/bin", str(usr_bin)]),
        os.pathsep.join(["/sandbox/bin", str(homebrew_like), str(usr_bin)]),
    ]
    assert facts["selected_python"] == {
        "path": str(host.python("3.13")),
        "version": "3.13.13",
        "requires_python": ">=3.13,<3.15",
    }
    (sync,) = _synced(host)
    assert sync[sync.index("--python") + 1] == str(host.python("3.13"))
    assert facts["project_runtime"]["version"] == "3.13.13"
    assert facts["problems"] == []


def test_a_well_known_directory_already_on_the_path_is_not_appended_twice(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    _lay_out(host)
    usr_bin = tmp_path / "usr" / "bin"
    usr_bin.mkdir(parents=True)
    homebrew_like = host.python("3.13").parent
    path = os.pathsep.join(["/sandbox/bin", str(homebrew_like)])
    facts: dict[str, Any] = {}
    _run(root, host, facts, path=path, well_known=_simulated_well_known(tmp_path))

    _first, second = facts["python_candidates"]
    assert second["search_path"]["already_present"] == [str(homebrew_like)]
    assert second["search_path"]["added"] == [str(usr_bin)]
    assert second["discovered_via"] == f"inherited PATH entry {homebrew_like}"
    assert _find_paths(host)[1] == os.pathsep.join([path, str(usr_bin)])
    assert facts["selected_python"]["path"] == str(host.python("3.13"))


def test_a_well_known_directory_under_the_managed_root_is_not_added(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(
        tmp_path,
        {"3.14": (3, 14, 0), "3.13": (3, 13, 13)},
        managed_dir=tmp_path / "python3.14",
    )
    _lay_out(host)
    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path))

    first, second = facts["python_candidates"]
    assert first["outcome"] == "not installed"
    assert first["search_path"]["excluded"] == [str(host.python("3.14").parent)]
    assert first["search_path"]["added"] == []
    assert "path" not in first
    assert not any(call[0] == str(host.python("3.14")) for call in host.calls)
    assert second["outcome"] == "selected"
    assert second["search_path"]["added"] == [str(host.python("3.13").parent)]
    assert facts["selected_python"]["path"] == str(host.python("3.13"))
    assert _find_paths(host)[0] == "/sandbox/bin"


def test_a_project_virtual_environment_is_never_added_as_a_well_known_directory(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.13": (3, 13, 13)})
    _lay_out(host)
    venv_bin = root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    simulated = _simulated_well_known(tmp_path)

    def well_known(wanted: Sequence[int]) -> list[Path]:
        return [venv_bin, *simulated(wanted)]

    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=well_known)

    for entry in facts["python_candidates"]:
        assert entry["search_path"]["well_known"][0] == str(venv_bin)
        assert entry["search_path"]["excluded"] == [str(venv_bin)]
    assert all(str(venv_bin) not in path.split(os.pathsep) for path in _find_paths(host))
    assert facts["selected_python"]["path"] == str(host.python("3.13"))


def test_a_named_interpreter_found_through_a_well_known_directory_is_still_checked(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {"3.14": (3, 12, 9), "3.13": (3, 13, 13)})
    _lay_out(host)
    facts: dict[str, Any] = {}
    _run(root, host, facts, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path))

    first, second = facts["python_candidates"]
    assert first["discovered_via"] == f"well-known directory {host.python('3.14').parent}"
    assert first["outcome"] == "rejected: not Python 3.14"
    assert second["outcome"] == "selected"
    assert facts["selected_python"]["path"] == str(host.python("3.13"))


def test_no_interpreter_anywhere_fails_the_bootstrap_with_the_search_paths_recorded(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    host = ScriptedHost(tmp_path, {})
    failure, facts = _failed(
        root, host, path="/sandbox/bin", well_known=_simulated_well_known(tmp_path)
    )

    assert failure.stage == "bootstrap"
    assert "no installed system Python (3.14, 3.13) satisfies" in failure.detail
    for entry, minor in zip(facts["python_candidates"], ("3.14", "3.13"), strict=True):
        assert entry["outcome"] == "not installed"
        assert entry["search_path"]["inherited"] == ["/sandbox/bin"]
        assert entry["search_path"]["absent"] == [
            str(tmp_path / f"python{minor}" / "bin"),
            str(tmp_path / "usr" / "bin"),
        ]
        assert entry["search_path"]["added"] == []
    assert _find_paths(host) == ["/sandbox/bin", "/sandbox/bin"]
    receipt = proof.build_receipt(facts, failure)
    assert receipt["verdict"] == "FAILED"
    assert receipt["python_candidates"] == facts["python_candidates"]
