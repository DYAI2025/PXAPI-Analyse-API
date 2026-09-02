"""Meta-rules every v1 schema must satisfy, checked over the schema files themselves.

These are the AC2 "requiredness rules" made mechanical: every object is closed where it
declares properties, every property belongs to exactly one of the three categories
(required non-null, required nullable, optional non-null) and says so, every pattern is
fully anchored in the dialect the tests actually run, and the customer projection declares
no property whose name would leak internal analysis vocabulary.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from tests.contracts.support import (
    CANONICAL_CONTRACT_NAMES,
    CONTRACTS_VERSION,
    SUPPORT_CONTRACT_NAMES,
    all_schema_paths,
    contract_entries,
    load_json,
    registry,
    schema_id,
    schema_path,
)

SCHEMA_VERSION_REF = f"{schema_id('common')}#/$defs/schema_version"

#: Keywords whose subschemas constrain the SAME instance as the owning object, so a
#: `properties` / `required` inside them refers to the owner's members.
SAME_INSTANCE_APPLICATORS = ("allOf", "anyOf", "oneOf", "if", "then", "else", "not")

#: Keywords whose subschemas describe a DIFFERENT instance (array items, definitions).
FRESH_CONTEXT_KEYWORDS = ("items", "prefixItems", "contains", "$defs", "properties")

#: Property names that must never appear in the customer projection (Confluence 39846055
#: §12 and §19 Leakage Gate; oracle INV-LEAK-01).
CUSTOMER_LEAK_NAME = re.compile(
    r"(audit|coverage|qa|runtime|provider|confidence|assessment|not_assessed|gate|pipeline|"
    r"contract|evidence|measurement|collector|model|debug|internal)"
)

ALL_SCHEMAS = [(path.name, path) for path in all_schema_paths()]


def _schemas() -> Iterator[tuple[str, dict[str, Any]]]:
    for name, path in ALL_SCHEMAS:
        yield name, load_json(path)


@pytest.mark.parametrize(("name", "path"), ALL_SCHEMAS, ids=[n for n, _ in ALL_SCHEMAS])
def test_schema_is_a_valid_draft_2020_12_schema(name: str, path: Path) -> None:
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def _iter_refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            yield node["$ref"]
        for value in node.values():
            yield from _iter_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_refs(value)


def test_every_ref_resolves_inside_the_v1_registry() -> None:
    resolver = registry().resolver()
    seen = 0
    for _name, schema in _schemas():
        base = resolver.lookup(schema["$id"]).resolver
        for ref in _iter_refs(schema):
            base.lookup(ref)  # raises Unresolvable on a dangling reference
            seen += 1
    assert seen > 50, "canary: the reference walk visited almost nothing"


def test_every_contract_is_a_closed_object_with_a_const_schema_version() -> None:
    for entry in contract_entries():
        schema = load_json(schema_path(entry["name"]))
        assert schema["type"] == "object", entry["name"]
        assert schema["additionalProperties"] is False, entry["name"]
        assert "schema_version" in schema["required"], entry["name"]
        assert schema["properties"]["schema_version"]["$ref"] == SCHEMA_VERSION_REF, entry["name"]
    common = load_json(schema_path("common"))
    assert common["$defs"]["schema_version"] == {
        "type": "string",
        "const": CONTRACTS_VERSION,
        "description": common["$defs"]["schema_version"]["description"],
    }


def test_every_canonical_contract_requires_run_id() -> None:
    for name in CANONICAL_CONTRACT_NAMES:
        schema = load_json(schema_path(name))
        assert "run_id" in schema["required"], name
        assert schema["properties"]["run_id"]["$ref"] == f"{schema_id('common')}#/$defs/id"


def test_no_schema_relies_on_a_format_annotation() -> None:
    for name, schema in _schemas():
        assert "format" not in _dump_keys(schema), f"{name}: 'format' is not asserted; use pattern"


def _dump_keys(node: Any) -> set[str]:
    """Every schema keyword used anywhere in ``node`` (member names and values excluded)."""
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for member in value.values():
                    keys |= _dump_keys(member)
            elif key in ("enum", "const", "required", "description", "title"):
                continue
            else:
                keys.add(key)
                keys |= _dump_keys(value)
    elif isinstance(node, list):
        for value in node:
            keys |= _dump_keys(value)
    return keys


# --- closed objects and the three property categories ------------------------------------


class _Walk:
    """Walks one schema file, checking object closure and property categories.

    ``owner`` is the ``properties`` mapping of the nearest declaring object (``type: object``)
    whose instance the current subschema constrains. Inside a same-instance applicator
    (``if``/``then``/``allOf``/``not``…) a subschema may only name members of that owner; when
    it descends into ``properties/<member>`` there, the member's declared schema (resolved
    through ``$ref``) becomes the new owner, so nested conditional constraints such as
    ``then.properties.artifacts.properties.scorecard`` are checked against real members.
    """

    def __init__(self, name: str, schema: dict[str, Any]) -> None:
        self.name = name
        self.schema = schema
        self.resolver = registry().resolver().lookup(schema["$id"]).resolver
        self.declaring_objects = 0
        self.conditionals = 0
        self.errors: list[str] = []

    def run(self) -> None:
        self._walk(self.schema, owner=None, in_applicator=False, path="#")

    def _declared_properties(self, sub: Any) -> dict[str, Any] | None:
        """The ``properties`` of the object a property schema declares, following ``$ref``."""
        if not isinstance(sub, dict):
            return None
        if isinstance(sub.get("$ref"), str):
            sub = self.resolver.lookup(sub["$ref"]).contents
        if isinstance(sub, dict) and _declares_object(sub):
            return sub.get("properties", {})
        return None

    def _walk(
        self, node: Any, *, owner: dict[str, Any] | None, in_applicator: bool, path: str
    ) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                self._walk(item, owner=owner, in_applicator=in_applicator, path=f"{path}/{index}")
            return
        if not isinstance(node, dict):
            return

        if _declares_object(node):
            owner = self._check_declaring_object(node, path)
            in_applicator = False
        elif "properties" in node or "required" in node:
            if not in_applicator or owner is None:
                self.errors.append(
                    f"{path}: names properties/required without being a declared object "
                    "or an applicator of one"
                )
            else:
                named = set(node.get("properties", {})) | set(node.get("required", []))
                if not named <= set(owner):
                    self.errors.append(
                        f"{path}: names members outside the owner: {sorted(named - set(owner))}"
                    )

        for key, value in node.items():
            child_path = f"{path}/{key}"
            if key == "properties":
                for member, sub in value.items():
                    member_path = f"{child_path}/{member}"
                    if in_applicator and owner is not None and member in owner:
                        # A constraint on an existing member: its declared object (if any)
                        # is the owner for anything the constraint names.
                        nested = self._declared_properties(owner[member])
                        self._walk(sub, owner=nested, in_applicator=True, path=member_path)
                    else:
                        self._walk(sub, owner=None, in_applicator=False, path=member_path)
            elif key == "$defs":
                for member, sub in value.items():
                    self._walk(sub, owner=None, in_applicator=False, path=f"{child_path}/{member}")
            elif key in ("items", "prefixItems", "contains"):
                self._walk(value, owner=None, in_applicator=False, path=child_path)
            elif key in SAME_INSTANCE_APPLICATORS:
                if key == "if":
                    self.conditionals += 1
                self._walk(value, owner=owner, in_applicator=True, path=child_path)

    def _check_declaring_object(self, node: dict[str, Any], path: str) -> dict[str, Any]:
        self.declaring_objects += 1
        properties: dict[str, Any] = node.get("properties", {})
        if properties and node.get("additionalProperties") is not False:
            self.errors.append(f"{path}: declares properties but is not closed")
        required = node.get("required", [])
        if not set(required) <= set(properties):
            undeclared = sorted(set(required) - set(properties))
            self.errors.append(f"{path}: requires undeclared members {undeclared}")
        conditionally_required = self._conditionally_required(node)
        for member, sub in properties.items():
            member_path = f"{path}/properties/{member}"
            nullable = _is_nullable(sub)
            description = sub.get("description", "")
            if member in required:
                expected = "Required, nullable." if nullable else "Required."
            elif nullable:
                self.errors.append(f"{member_path}: optional AND nullable — pick one category")
                continue
            elif member in conditionally_required:
                expected = "Conditional."
            else:
                expected = "Optional."
            if not description.startswith(expected):
                self.errors.append(f"{member_path}: description must start with {expected!r}")
        return properties

    @staticmethod
    def _conditionally_required(node: dict[str, Any]) -> set[str]:
        found: set[str] = set()

        def collect(sub: Any) -> None:
            if isinstance(sub, dict):
                found.update(sub.get("required", []))
                for key, value in sub.items():
                    if key in SAME_INSTANCE_APPLICATORS:
                        collect(value)
            elif isinstance(sub, list):
                for item in sub:
                    collect(item)

        for key in SAME_INSTANCE_APPLICATORS:
            if key in node:
                collect(node[key])
        return found


def _declares_object(node: dict[str, Any]) -> bool:
    """``type: object`` or ``type: [object, null]`` — a node that owns its properties."""
    declared = node.get("type")
    return declared == "object" or (isinstance(declared, list) and "object" in declared)


def _is_nullable(sub: dict[str, Any]) -> bool:
    declared = sub.get("type")
    if declared == "null" or (isinstance(declared, list) and "null" in declared):
        return True
    for key in ("anyOf", "oneOf"):
        if any(branch.get("type") == "null" for branch in sub.get(key, [])):
            return True
    return False


@pytest.mark.parametrize(("name", "path"), ALL_SCHEMAS, ids=[n for n, _ in ALL_SCHEMAS])
def test_objects_are_closed_and_every_property_states_its_category(name: str, path: Path) -> None:
    walk = _Walk(name, load_json(path))
    walk.run()
    assert walk.errors == [], "\n".join(walk.errors)
    assert walk.declaring_objects >= 1, f"{name}: canary — no object was inspected"


def test_the_walk_saw_conditionals_and_nested_objects() -> None:
    """Canary against a vacuous walk: the rules above must have visited real if/then nodes."""
    conditionals = 0
    declaring = 0
    for _name, schema in _schemas():
        walk = _Walk(_name, schema)
        walk.run()
        conditionals += walk.conditionals
        declaring += walk.declaring_objects
    assert conditionals >= 15
    assert declaring >= 30


# --- pattern dialect -----------------------------------------------------------------------


def _iter_patterns(node: Any, path: str = "#") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        if isinstance(node.get("pattern"), str):
            yield path, node["pattern"]
        for key, value in node.items():
            yield from _iter_patterns(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_patterns(value, f"{path}/{index}")


def _unescaped_dot_outside_class(pattern: str) -> bool:
    in_class = False
    escaped = False
    for char in pattern:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif in_class:
            if char == "]":
                in_class = False
        elif char == "[":
            in_class = True
        elif char == ".":
            return True
    return False


def test_every_pattern_is_fully_anchored_and_free_of_shorthand_classes() -> None:
    seen = 0
    for name, schema in _schemas():
        for where, pattern in _iter_patterns(schema):
            seen += 1
            assert pattern.startswith("^"), f"{name} {where}: not anchored at start"
            # Python's `$` also matches before a trailing newline; the lookahead closes that.
            assert pattern.endswith("(?!\n)$"), f"{name} {where}: must end with (?!\\n)$"
            for shorthand in ("\\d", "\\s", "\\w", "\\D", "\\S", "\\W", "\\b"):
                assert shorthand not in pattern, f"{name} {where}: shorthand class {shorthand!r}"
            assert not _unescaped_dot_outside_class(pattern), f"{name} {where}: unescaped '.'"
            re.compile(pattern)
    assert seen >= 12, "canary: the pattern walk visited almost nothing"


# --- customer projection leakage boundary ---------------------------------------------------


def _resolved_property_names(name: str) -> set[str]:
    """Every property name reachable in the contract, following $ref across files."""
    resolver = registry().resolver()
    names: set[str] = set()
    visited: set[int] = set()  # id() of resolved contents; the registry keeps them alive

    def walk(node: Any, base: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("$ref"), str):
                resolved = base.lookup(node["$ref"])
                if id(resolved.contents) not in visited:
                    visited.add(id(resolved.contents))
                    walk(resolved.contents, resolved.resolver)
            for key, value in node.items():
                if key == "properties":
                    names.update(value)
                    for sub in value.values():
                        walk(sub, base)
                elif key != "$ref":
                    walk(value, base)
        elif isinstance(node, list):
            for item in node:
                walk(item, base)

    resource = resolver.lookup(schema_id(name))
    walk(resource.contents, resource.resolver)
    return names


def test_client_report_model_declares_no_internal_vocabulary() -> None:
    names = _resolved_property_names("client-report-model")
    assert len(names) >= 10, "canary: the leak walk resolved almost nothing"
    leaking = sorted(n for n in names if CUSTOMER_LEAK_NAME.search(n))
    assert leaking == [], f"customer projection leaks internal vocabulary: {leaking}"


def test_leak_walk_sees_internal_vocabulary_where_it_exists() -> None:
    """Canary: the same walk over the internal record must find the words the customer must not."""
    names = _resolved_property_names("internal-analysis-record")
    assert any(CUSTOMER_LEAK_NAME.search(n) for n in names)


def test_support_and_canonical_sets_are_disjoint_and_named_consistently() -> None:
    assert not set(CANONICAL_CONTRACT_NAMES) & set(SUPPORT_CONTRACT_NAMES)
    for name in (*CANONICAL_CONTRACT_NAMES, *SUPPORT_CONTRACT_NAMES):
        assert re.fullmatch(r"[a-z]+(-[a-z]+)*", name), name
