"""Meta-rules every registered schema must satisfy, checked over the schema files themselves.

These are the requiredness rules made mechanical: every object is closed where it declares
properties, every property belongs to exactly one category (required non-null, required
nullable, conditional, optional non-null) and says so in its description, every pattern is
fully anchored in the dialect the tests actually run, and every ``$ref`` resolves offline.

Nothing here names a contract. The inventory comes from the registry, so a contract added
later is covered by these same rules without a new test.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from tests.contracts.support import (
    CONTRACTS,
    SchemaWalk,
    iter_patterns,
    iter_refs,
    load_json,
)

ALL_SCHEMAS = [(path.name, path) for path in CONTRACTS.all_schema_paths()]
SCHEMA_IDS = [name for name, _ in ALL_SCHEMAS]

#: Shorthand classes whose meaning depends on the regex flavour and on Unicode settings.
#: The contracts spell every class out so a JavaScript or Go validator agrees with Python.
SHORTHAND_CLASSES = ("\\d", "\\s", "\\w", "\\D", "\\S", "\\W", "\\b")


def test_the_schema_set_is_not_empty() -> None:
    """Canary: without this, every parametrised rule below would pass over an empty list."""
    assert ALL_SCHEMAS, "the registry names no schema file"


@pytest.mark.parametrize(("name", "path"), ALL_SCHEMAS, ids=SCHEMA_IDS)
def test_schema_is_a_valid_draft_2020_12_schema(name: str, path: Path) -> None:
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == CONTRACTS.dialect(), name
    assert schema["$id"].startswith(CONTRACTS.id_namespace()), name


#: Raw characters that must never appear in a schema file. Tab and newline are the file's
#: own whitespace and are exempt; everything else here would make the file unreviewable and
#: would smuggle a literal control character into a pattern or a description.
RAW_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]")


@pytest.mark.parametrize(("name", "path"), ALL_SCHEMAS, ids=SCHEMA_IDS)
def test_schema_file_contains_no_raw_control_characters(name: str, path: Path) -> None:
    found = RAW_CONTROL.search(path.read_text(encoding="utf-8"))
    assert found is None, (
        f"{name}: raw control character {found.group()!r} at offset {found.start()}; "
        "write it as a JSON or regex escape instead"
    )


def test_every_ref_resolves_inside_the_registry() -> None:
    """Offline resolution: a dangling or remote reference raises instead of silently passing."""
    resolver = CONTRACTS.jsonschema_registry().resolver()
    seen = 0
    visited = 0
    for _name, path in ALL_SCHEMAS:
        schema = load_json(path)
        base = resolver.lookup(schema["$id"]).resolver
        visited += 1
        for ref in iter_refs(schema):
            base.lookup(ref)  # raises Unresolvable on a dangling reference
            seen += 1
    assert visited == len(ALL_SCHEMAS), "the reference walk skipped a registered schema"
    assert seen > 0, "canary: the reference walk resolved nothing at all"


@pytest.mark.parametrize("entry", CONTRACTS.entries(), ids=CONTRACTS.names())
def test_every_contract_is_a_closed_object_pinning_its_own_version(entry: dict[str, Any]) -> None:
    schema = load_json(CONTRACTS.path / entry["schema"])
    name = entry["name"]
    assert schema["type"] == "object", name
    assert schema["additionalProperties"] is False, name
    assert "schema_version" in schema["required"], name
    declared = schema["properties"]["schema_version"]
    assert declared["type"] == "string", name
    assert declared["const"] == entry["version"], (
        f"{name}: the schema pins {declared.get('const')!r} but the registry says "
        f"{entry['version']!r}"
    )


def test_no_schema_relies_on_a_format_annotation() -> None:
    """``format`` is an annotation by default: it validates nothing unless a checker is wired."""
    for name, path in ALL_SCHEMAS:
        assert "format" not in _keywords(load_json(path)), (
            f"{name}: 'format' is not asserted by default; use an explicit pattern"
        )


def _keywords(node: Any) -> set[str]:
    """Every schema keyword used anywhere in ``node`` (member names and values excluded)."""
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for member in value.values():
                    keys |= _keywords(member)
            elif key in ("enum", "const", "required", "description", "title"):
                continue
            else:
                keys.add(key)
                keys |= _keywords(value)
    elif isinstance(node, list):
        for value in node:
            keys |= _keywords(value)
    return keys


# --- closed objects and the property categories -------------------------------------------


@pytest.mark.parametrize(("name", "path"), ALL_SCHEMAS, ids=SCHEMA_IDS)
def test_objects_are_closed_and_every_property_states_its_category(name: str, path: Path) -> None:
    walk = SchemaWalk(name, load_json(path), CONTRACTS.jsonschema_registry()).run()
    assert walk.errors == [], "\n".join(walk.errors)


def test_the_walk_actually_inspected_declared_objects() -> None:
    """Canary against a vacuous walk: the rules above must have visited real objects."""
    declaring = sum(
        SchemaWalk(name, load_json(path), CONTRACTS.jsonschema_registry()).run().declaring_objects
        for name, path in ALL_SCHEMAS
    )
    assert declaring >= len(CONTRACTS.entries()), (
        "fewer objects inspected than registered contracts"
    )


# --- pattern dialect -----------------------------------------------------------------------


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
    for name, path in ALL_SCHEMAS:
        for where, pattern in iter_patterns(load_json(path)):
            seen += 1
            assert pattern.startswith("^"), f"{name} {where}: not anchored at start"
            # Python's `$` also matches before a trailing newline; the lookahead closes that.
            # The escape is written `\n`, not a literal newline, so every schema file stays
            # free of raw control characters and reviewable as plain text.
            assert pattern.endswith(r"(?!\n)$"), f"{name} {where}: must end with (?!\\n)$"
            for shorthand in SHORTHAND_CLASSES:
                assert shorthand not in pattern, f"{name} {where}: shorthand class {shorthand!r}"
            assert not _unescaped_dot_outside_class(pattern), f"{name} {where}: unescaped '.'"
            re.compile(pattern)
    assert seen > 0, "canary: the pattern walk visited nothing"
