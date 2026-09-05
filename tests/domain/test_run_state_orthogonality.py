"""Global run state and stage execution stay orthogonal, and are mechanically kept so.

The superseded design projected stage outcomes onto the global lifecycle: a mapping from a
stage to the run state its failure produced, and a helper that advanced the run by running a
pass of stages. Both are structurally excluded here, in three independent ways:

* the Domain module's top-level surface is pinned, so a projection helper cannot be added
  without changing a test that says what the module is allowed to be;
* no identifier anywhere under ``src/pxapi`` may mention a stage, so a stage vocabulary — open
  or closed — cannot enter the Domain at all. Prose *about* the boundary is deliberately still
  allowed: only identifiers and runtime strings are scanned;
* the two contracts are checked against each other: neither declares a member of the other's
  vocabulary, and a failed stage record and a globally succeeded run state validate side by
  side.

That last property is a statement about the *contracts*, not about operations. It does not say
a stage failure is harmless. It says the contracts do not decide the question: whether a given
stage or provider failure is fatal to a run is orchestration policy, which no contract in this
slice makes and which a later slice must decide explicitly rather than inherit from a schema.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pxapi.domain import run_state
from pxapi.domain.run_state import IllegalTransition, RunState
from tests.contracts.support import CONTRACTS, load_json

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "pxapi"
SOURCE_FILES = sorted(SRC.rglob("*.py"))
SOURCE_IDS = [str(path.relative_to(SRC)) for path in SOURCE_FILES]

RUN_STATE_CONTRACT = "analysis-run-state"
STAGE_CONTRACT = "stage-execution-record"

#: Everything ``run_state`` is allowed to define at module level. A projection helper, a
#: stage-to-state mapping or a retry policy would have to appear here to exist at all.
EXPECTED_MODULE_SURFACE: frozenset[str] = frozenset(
    {
        "RunState",
        "ALLOWED_TRANSITIONS",
        "LEGAL_TRANSITIONS",
        "TERMINAL_STATES",
        "IllegalTransition",
        "is_terminal",
        "can_transition",
        "transition",
    }
)

#: Names from the superseded design, banned by name as well as by shape. The generic stage
#: scan below already covers most of them; naming them makes a regression report say which
#: idea came back rather than only that some identifier matched.
BANNED_IDENTIFIER_PARTS: tuple[str, ...] = (
    "stage",
    "failure_state_for",
    "project_pass_one",
    "pass_one",
    "customer_release",
)


def _top_level_definitions(path: Path) -> set[str]:
    """Every name the module itself defines at top level; imported names are not definitions."""
    defined: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            defined.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.Assign):
            defined.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return defined


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of the constant nodes that are docstrings, so prose can be excluded from the scan."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def _identifiers_and_runtime_strings(source: str) -> set[str]:
    """Every name a module uses, plus every string literal that is not a docstring."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.alias):
            found.update(part for part in (node.name, node.asname) if part)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            found.add(node.value)
    return found


# --- the Domain surface ----------------------------------------------------------------------


def test_the_run_state_module_defines_exactly_its_decision_surface() -> None:
    path = Path(run_state.__file__)
    assert _top_level_definitions(path) == set(EXPECTED_MODULE_SURFACE)


def test_the_domain_holds_no_module_named_for_a_stage() -> None:
    """No ``stage_execution.py``: a stage has no Python representation in this slice at all."""
    named = [name for name in SOURCE_IDS if "stage" in name.lower()]
    assert named == [], f"stage-named Domain modules: {named}"


def test_the_identifier_scanner_sees_what_it_forbids(tmp_path: Path) -> None:
    """Canary: the scan below must detect the superseded design if it were reintroduced."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        '"""A docstring naming a stage is not an identifier."""\n\n'
        "FAILURE_STATE_FOR = {}\n\n\n"
        "def project_pass_one(stage_records):\n"
        '    return {"BASELINE_COLLECTION": "FAILED"}\n',
        encoding="utf-8",
    )
    found = _identifiers_and_runtime_strings(probe.read_text(encoding="utf-8"))
    lowered = " ".join(found).lower()
    assert "failure_state_for" in lowered
    assert "project_pass_one" in lowered
    assert "stage_records" in lowered

    prose_only = tmp_path / "prose.py"
    prose_only.write_text('"""This module deliberately holds no stage concept."""\n', "utf-8")
    assert _identifiers_and_runtime_strings(prose_only.read_text(encoding="utf-8")) == set()


@pytest.mark.parametrize("path", SOURCE_FILES, ids=SOURCE_IDS)
def test_no_source_identifier_mentions_a_stage_or_a_superseded_helper(path: Path) -> None:
    """A stage vocabulary, a stage-to-state mapping and a pass runner cannot exist here.

    The scan covers identifiers and runtime strings, not documentation: a module may explain
    that it holds no stage concept, and may not quietly acquire one.
    """
    found = _identifiers_and_runtime_strings(path.read_text(encoding="utf-8"))
    offenders = sorted(
        name for name in found for part in BANNED_IDENTIFIER_PARTS if part in name.lower()
    )
    assert offenders == [], f"{path.relative_to(ROOT)} names {offenders}"


# --- one vocabulary, two representations ------------------------------------------------------


def test_the_contract_state_enum_and_the_domain_vocabulary_are_the_same_list() -> None:
    """Two statements of one fact. Neither is a copy that may drift from the other unnoticed."""
    schema = load_json(CONTRACTS.schema_path(RUN_STATE_CONTRACT))
    declared = schema["properties"]["state"]["enum"]
    assert declared == [state.value for state in RunState]


def test_the_stage_status_vocabulary_is_not_the_run_state_vocabulary() -> None:
    """They share tokens; they are not one vocabulary and neither is derived from the other."""
    stage = load_json(CONTRACTS.schema_path(STAGE_CONTRACT))
    statuses = set(stage["properties"]["status"]["enum"])
    assert statuses != {state.value for state in RunState}
    assert "PENDING" not in statuses and "QUEUED" not in statuses


def test_the_stage_record_declares_no_global_state_member() -> None:
    stage = load_json(CONTRACTS.schema_path(STAGE_CONTRACT))
    leaked = {"state", "run_state", "execution_status"} & set(stage["properties"])
    assert leaked == set(), f"a global state member leaked into the stage record: {leaked}"


def test_the_stage_id_vocabulary_is_open() -> None:
    """``stage_id`` fixes a lexical shape, never a set of stages; an enum here would close it."""
    stage = load_json(CONTRACTS.schema_path(STAGE_CONTRACT))
    declared = stage["properties"]["stage_id"]
    assert "enum" not in declared and "const" not in declared
    assert declared["$ref"].endswith("#/$defs/code")


def test_the_run_state_contract_declares_no_stage_and_no_release_member() -> None:
    schema = load_json(CONTRACTS.schema_path(RUN_STATE_CONTRACT))
    declared = set(schema["properties"])
    forbidden = {
        "stage_id",
        "stage_executions",
        "stages",
        "failure_stage",
        "customer_release",
        "released",
        "delivery",
        "report",
        "score",
        "transitions",
    }
    leaked = sorted(declared & forbidden)
    assert leaked == [], f"leaked into the run state: {leaked}"
    assert schema["additionalProperties"] is False


def test_the_failure_block_carries_a_code_and_nothing_else() -> None:
    schema = load_json(CONTRACTS.schema_path(RUN_STATE_CONTRACT))
    failure = schema["properties"]["failure"]
    assert list(failure["properties"]) == ["code"]
    assert failure["required"] == ["code"]
    assert failure["additionalProperties"] is False


def test_cancelled_introduces_no_metadata_structure_of_its_own() -> None:
    """CANCELLED is the state plus the terminal timestamp: no reason, requester or retry data."""
    schema = load_json(CONTRACTS.schema_path(RUN_STATE_CONTRACT))
    assert set(schema["properties"]) == {
        "schema_version",
        "run_id",
        "state",
        "entered_at",
        "finished_at",
        "failure",
    }


def test_the_illegal_transition_code_is_registered_in_the_problem_code_list() -> None:
    registered = {item["code"] for item in CONTRACTS.problem_codes()}
    assert IllegalTransition.code in registered


# --- coexistence ------------------------------------------------------------------------------


def _example(name: str) -> dict:
    return load_json(CONTRACTS.path / "examples" / name)


def test_a_failed_stage_execution_coexists_with_a_globally_succeeded_run() -> None:
    """Both documents are valid at once, and they are linked by ``run_id`` alone.

    This is a statement about the contracts, not about operations: it does not say a stage
    failure is harmless. It says neither document decides the other's outcome, so whether a
    particular stage or provider failure is fatal remains an orchestration policy question
    that a later slice must answer deliberately.
    """
    succeeded_run = _example("analysis-run-state.succeeded.example.json")
    failed_stage = _example("stage-execution-record.failed.example.json")

    assert succeeded_run["state"] == "SUCCEEDED"
    assert failed_stage["status"] == "FAILED"
    assert succeeded_run["run_id"] == failed_stage["run_id"]

    assert CONTRACTS.validate(RUN_STATE_CONTRACT, succeeded_run) == ()
    assert CONTRACTS.validate(STAGE_CONTRACT, failed_stage) == ()


def test_neither_contract_expresses_a_fatality_judgement() -> None:
    """No ``optional``/``fatal``/``blocking`` member: the schemas do not rank stage failures.

    A member like ``optional: true`` would invite the inverse reading — that a non-optional
    stage failure implies a globally failed run — which is precisely the projection this slice
    refuses to encode.
    """
    judgement = {"optional", "fatal", "blocking", "required_stage", "severity", "impact"}
    for contract in (RUN_STATE_CONTRACT, STAGE_CONTRACT):
        declared = set(load_json(CONTRACTS.schema_path(contract))["properties"])
        assert declared & judgement == set(), f"{contract} ranks failures: {declared & judgement}"


def test_both_plausible_projections_of_a_failed_stage_are_equally_valid_documents() -> None:
    """The two run-state outcomes a failed stage could be projected onto are both valid, and
    the stage record is unchanged by either. Nothing in the contract set prefers one over the
    other, because that choice does not exist here to be made."""
    for name in ("succeeded", "failed"):
        document = _example(f"analysis-run-state.{name}.example.json")
        assert CONTRACTS.validate(RUN_STATE_CONTRACT, document) == (), name
