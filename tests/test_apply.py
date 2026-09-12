"""Writing the plan out, and the one thing that must never happen."""

from __future__ import annotations

from pathlib import Path

import pytest

from inbox_filer.apply import ApplyError, apply_plan, tree_state
from inbox_filer.plan import build_plan


def test_apply_writes_exactly_what_the_plan_said(messages, rules, tmp_path):
    plan = build_plan(messages, rules, tmp_path)

    written = apply_plan(plan)

    assert {a.relpath for a in written} == {a.relpath for a in plan.actions if a.writes}
    for action in written:
        assert (tmp_path / action.relpath).read_bytes() == action.attachment.content


def test_apply_writes_nothing_else(messages, rules, tmp_path):
    plan = build_plan(messages, rules, tmp_path)

    apply_plan(plan)

    on_disk = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert on_disk == {a.relpath for a in plan.actions if a.writes}


def test_a_second_apply_writes_nothing(messages, rules, tmp_path):
    apply_plan(build_plan(messages, rules, tmp_path))
    before = tree_state(tmp_path)

    written = apply_plan(build_plan(messages, rules, tmp_path))

    assert written == []
    assert tree_state(tmp_path) == before


def test_a_destination_appearing_after_planning_is_refused_not_overwritten(
    messages, rules, tmp_path
):
    """Files are created with `x`, not `w`. If the planner's guarantee is ever
    wrong, the filesystem stops it rather than the client losing a document."""
    plan = build_plan(messages, rules, tmp_path)
    first = next(a for a in plan.actions if a.writes)
    target = tmp_path / first.relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"something the client put there")

    with pytest.raises(ApplyError, match="nothing was overwritten"):
        apply_plan(plan)

    assert target.read_bytes() == b"something the client put there"


def test_tree_state_is_empty_for_a_directory_that_does_not_exist(tmp_path):
    assert tree_state(tmp_path / "absent") == {}


def test_tree_state_notices_a_changed_file_not_just_a_new_one(tmp_path):
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    before = tree_state(tmp_path)

    (tmp_path / "a.txt").write_text("different length", encoding="utf-8")

    assert tree_state(tmp_path) != before
