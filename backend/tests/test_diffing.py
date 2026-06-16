"""Tests for AST-aware change detection and severity classification."""

import hashlib

from app.diffing.entity_diff import EntityState, diff_snapshots
from app.diffing.text_diff import unified_markdown_diff
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


def test_rename_detected_with_real_source_despite_name_in_body():
    """Real renames must match on body, even though the full source (and thus
    body_hash) differs because the def line carries the new name."""
    old_src = "def compute(a, b):\n    return a + b\n"
    new_src = "def calculate(a, b):\n    return a + b\n"
    old = [_state("m.compute", sig="compute(a, b)", ret="None",
                  params='[{"name":"a"},{"name":"b"}]', body=old_src)]
    new = [_state("m.calculate", sig="calculate(a, b)", ret="None",
                  params='[{"name":"a"},{"name":"b"}]', body=new_src)]
    (change,) = diff_snapshots(old, new)
    assert change.change_type is ChangeType.RENAMED
    assert change.renamed_from == "m.compute"


def test_docstring_only_change_is_review_recommended():
    """A docstring-only edit must classify as DOCSTRING_CHANGED, not be swallowed
    by BODY_MODIFIED (the stored body_hash includes the docstring)."""
    old_src = 'def f(a):\n    """Old doc."""\n    return a\n'
    new_src = 'def f(a):\n    """New doc."""\n    return a\n'
    old = [EntityState("m.f", "function", "f(a)", "None", '[{"name":"a"}]',
                       "Old doc.", _hash(old_src), _hash(old_src), old_src)]
    new = [EntityState("m.f", "function", "f(a)", "None", '[{"name":"a"}]',
                       "New doc.", _hash(new_src), _hash(new_src), new_src)]
    (change,) = diff_snapshots(old, new)
    assert change.change_type is ChangeType.DOCSTRING_CHANGED
    assert change.severity is StalenessSeverity.REVIEW_RECOMMENDED


def test_unified_markdown_diff_is_well_formed():
    old = "# Title\n\nLine A\nLine B\n"
    new = "# Title\n\nLine A changed\nLine B\n"
    diff = unified_markdown_diff(old, new)
    assert "@@" in diff
    # Every diff line carries a prefix, so a correct diff never has a blank line
    # (the keepends bug doubled newlines, producing "\n\n").
    assert "\n\n" not in diff
    # Identical documents produce no diff (the UI shows "no differences").
    assert unified_markdown_diff("x\ny", "x\ny") == ""
