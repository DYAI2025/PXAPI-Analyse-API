"""Global run state and stage execution stay orthogonal, and are mechanically kept so.

The superseded design projected stage outcomes onto the global lifecycle: a mapping from a
stage to the run state its failure produced, and a helper that advanced the run by running a
pass of stages. Both are structurally excluded here, in three independent ways:

* the Domain module's top-level surface is pinned, so a projection helper cannot be added
  without changing a test that says what the module is allowed to be;
* the RunState module boundary is scanned: no identifier or runtime string in
  ``domain/run_state.py`` may mention a stage, a superseded helper or a release concept, so a
  stage vocabulary — open or closed — cannot enter the global run state. Separately, the
  superseded design's *own* names may not reappear anywhere under ``src/pxapi``. Prose *about*
  the boundary is deliberately still allowed: only identifiers and runtime strings are scanned;
* the two contracts are checked against each other: neither declares a member of the other's
  vocabulary, and a failed stage record and a globally succeeded run state validate side by
  side.

The generic ``stage`` fragment is enforced at the RunState module, not across every layer. PXK-60
decides that the global run state holds no stage concept; it does not decide what a later,
separately authorised orchestration module may be called. Such a module may legitimately name a
``stage_execution``, and this suite is not the place that forbids it.

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
DOMAIN = SRC / "domain"
SOURCE_FILES = sorted(SRC.rglob("*.py"))
SOURCE_IDS = [str(path.relative_to(SRC)) for path in SOURCE_FILES]
DOMAIN_IDS = [str(path.relative_to(SRC)) for path in sorted(DOMAIN.rglob("*.py"))]

#: The module boundary this suite owns: the global run state, and nothing else.
RUN_STATE_PATH = Path(run_state.__file__).resolve()

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

#: Banned inside the RunState module boundary, and only there. ``stage`` and ``customer_release``
#: are *generic* fragments: an outer layer a later slice authorises may legitimately need them,
#: and PXK-60 does not decide that. What PXK-60 does decide is that the global run state itself
#: holds neither concept — so the generic ban is enforced at the boundary that owns the rule
#: rather than turned into a permanent architecture lock over every future layer.
BANNED_IN_THE_RUN_STATE_MODULE: tuple[str, ...] = (
    "stage",
    "failure_state_for",
    "project_pass_one",
    "pass_one",
    "customer_release",
)

#: Names of the superseded design *itself*, banned everywhere under ``src/pxapi``. These are not
#: generic concepts a later slice might legitimately reach for: they name the rejected
#: stage-to-run projection — a mapping from a stage to the run state its failure produced, and a
#: helper that advanced the run by running a pass of stages. Wherever one of them reappears, the
#: rejected design has reappeared with it, whichever layer it is hiding in.
SUPERSEDED_DESIGN_NAMES: tuple[str, ...] = (
    "failure_state_for",
    "project_pass_one",
    "pass_one",
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


def _offenders(source: str, banned: tuple[str, ...]) -> list[str]:
    """Every identifier or runtime string in ``source`` carrying one of the banned fragments."""
    found = _identifiers_and_runtime_strings(source)
    return sorted({name for name in found for part in banned if part in name.lower()})


# --- the Domain surface ----------------------------------------------------------------------


def test_the_run_state_module_defines_exactly_its_decision_surface() -> None:
    path = Path(run_state.__file__)
    assert _top_level_definitions(path) == set(EXPECTED_MODULE_SURFACE)


def test_this_slice_adds_no_stage_module_to_the_domain_ring() -> None:
    """No Domain ``stage_execution.py``: a stage has no Domain representation in this slice.

    This states what PXK-60 builds, not a permanent architecture rule. An outer layer a later
    slice authorises may hold a ``stage_orchestrator``; what may not happen is a Domain stage
    module appearing as a side effect of this slice, unnoticed and unattributed.
    """
    named = [name for name in DOMAIN_IDS if "stage" in name.lower()]
    assert named == [], f"stage-named Domain modules: {named}"
    assert DOMAIN_IDS, f"no Python source found under {DOMAIN}"


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


def test_the_scanned_boundary_is_the_real_run_state_module() -> None:
    """Canary: the scan below reads the module it protects, not an empty or unrelated file."""
    assert (DOMAIN / "run_state.py").resolve() == RUN_STATE_PATH
    source = RUN_STATE_PATH.read_text(encoding="utf-8")
    assert "class RunState" in source and "ALLOWED_TRANSITIONS" in source


def test_the_run_state_module_names_no_stage_and_no_superseded_helper() -> None:
    """A stage vocabulary, a stage-to-state mapping and a pass runner cannot exist here.

    The scan covers identifiers and runtime strings, not documentation: the module may explain
    that it holds no stage concept, and may not quietly acquire one.
    """
    offenders = _offenders(
        RUN_STATE_PATH.read_text(encoding="utf-8"), BANNED_IN_THE_RUN_STATE_MODULE
    )
    assert offenders == [], f"{RUN_STATE_PATH.relative_to(ROOT)} names {offenders}"


def test_a_projection_planted_in_the_run_state_module_is_rejected(tmp_path: Path) -> None:
    """Mutation canary on the real module: reviving the superseded design is mechanically red.

    The mutation is applied to ``run_state.py``'s own source rather than to a synthetic
    stand-in, so the guard is proven on the file it protects. Both independent guards fire: the
    identifier scan sees the names, and the pinned module surface no longer matches.
    """
    mutated = RUN_STATE_PATH.read_text(encoding="utf-8") + (
        "\n\nFAILURE_STATE_FOR = {RunState.RUNNING: RunState.FAILED}\n\n\n"
        "def project_pass_one(stage_records):\n"
        "    return RunState.FAILED\n"
    )
    offenders = _offenders(mutated, BANNED_IN_THE_RUN_STATE_MODULE)
    assert "FAILURE_STATE_FOR" in offenders
    assert "project_pass_one" in offenders
    assert "stage_records" in offenders

    planted = tmp_path / "run_state.py"
    planted.write_text(mutated, encoding="utf-8")
    assert _top_level_definitions(planted) != set(EXPECTED_MODULE_SURFACE)


def test_an_outer_layer_stage_identifier_is_not_rejected_by_this_guard(tmp_path: Path) -> None:
    """A later slice's authorised orchestration module is not this suite's business.

    The narrowing is a scope decision, not a weakening: the very same source is still rejected
    by the RunState module's own ban list. What changed is where the generic ``stage`` fragment
    is enforced — at the boundary that owns the rule, instead of over every future layer.
    """
    outer = tmp_path / "stage_orchestrator.py"
    outer.write_text(
        '"""A later, separately authorised orchestration module."""\n\n\n'
        "def record_stage_execution(run_id, stage_execution):\n"
        "    return {run_id: stage_execution}\n",
        encoding="utf-8",
    )
    source = outer.read_text(encoding="utf-8")
    assert _offenders(source, SUPERSEDED_DESIGN_NAMES) == []
    assert _offenders(source, BANNED_IN_THE_RUN_STATE_MODULE) == [
        "record_stage_execution",
        "stage_execution",
    ]


def test_the_source_scan_is_not_vacuous() -> None:
    """Canary: an empty file list would make the parametrized scan below pass by default."""
    assert SOURCE_IDS, f"no Python source found under {SRC}"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=SOURCE_IDS)
def test_no_source_anywhere_revives_the_superseded_projection(path: Path) -> None:
    """Everywhere under ``src/pxapi``: the rejected stage-to-run projection stays gone.

    These fragments name one specific rejected design rather than a generic concept, so barring
    them outside the Domain locks nothing a later slice legitimately needs.
    """
    offenders = _offenders(path.read_text(encoding="utf-8"), SUPERSEDED_DESIGN_NAMES)
    assert offenders == [], f"{path.relative_to(ROOT)} revives {offenders}"


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
