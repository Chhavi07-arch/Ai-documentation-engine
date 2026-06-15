"""Tests for AST-aware change detection and severity classification."""

import hashlib

from app.diffing.entity_diff import EntityState, diff_snapshots
from app.models.enums import ChangeType, StalenessSeverity


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _state(name: str, *, sig: str, ret: str, params: str, body: str) -> EntityState:
    return EntityState(
        qualified_name=name,
        kind="function",
        signature=sig,
        return_type=ret,
        parameters_json=params,
        docstring=None,
        structure_hash=_hash(sig + ret + params),
        body_hash=_hash(body),
        source_code=body,
    )


def test_parameter_change_is_broken():
    old = [_state("m.f", sig="f(a)", ret="int", params='[{"name":"a"}]', body="x")]
    new = [
        _state("m.f", sig="f(a,b)", ret="int", params='[{"name":"a"},{"name":"b"}]', body="x")
    ]
    (change,) = diff_snapshots(old, new)
    assert change.change_type is ChangeType.PARAMETERS_CHANGED
    assert change.severity is StalenessSeverity.BROKEN


def test_body_change_is_potentially_outdated():
    old = [_state("m.f", sig="f(a)", ret="int", params='[{"name":"a"}]', body="return 1")]
    new = [_state("m.f", sig="f(a)", ret="int", params='[{"name":"a"}]', body="return 2")]
    (change,) = diff_snapshots(old, new)
    assert change.change_type is ChangeType.BODY_MODIFIED
    assert change.severity is StalenessSeverity.POTENTIALLY_OUTDATED


def test_rename_detected_via_identical_body():
    old = [_state("m.old", sig="old(a)", ret="int", params='[{"name":"a"}]', body="SAME")]
    new = [_state("m.new", sig="new(a)", ret="int", params='[{"name":"a"}]', body="SAME")]
    (change,) = diff_snapshots(old, new)
    assert change.change_type is ChangeType.RENAMED
    assert change.renamed_from == "m.old"


def test_deletion_is_broken():
    old = [_state("m.gone", sig="gone()", ret="None", params="[]", body="pass")]
    (change,) = diff_snapshots(old, [])
    assert change.change_type is ChangeType.DELETED
    assert change.severity is StalenessSeverity.BROKEN
