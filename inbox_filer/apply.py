"""Carrying out a plan.

This module is short and it is meant to be. Every decision was made in
`plan.py`; all that is left is writing bytes to paths that were already proved
free. That is what lets the dry run be an honest preview — it runs exactly the
code that produced the plan and then simply does not call this.
"""

from __future__ import annotations

from pathlib import Path

from .models import Action, Plan


class ApplyError(Exception):
    """A destination stopped being free between planning and writing."""


def apply_plan(plan: Plan) -> list[Action]:
    """Write every action that writes. Returns the actions that touched disk.

    Files are created with `x` (exclusive), never `w`. The planner already
    guarantees the path is free, so `w` would only ever differ from `x` in one
    situation: the guarantee being wrong. The whole pitch of the tool is that
    it does not overwrite the client's files, and the cheapest way to keep a
    promise like that is to make the filesystem enforce it.
    """
    written: list[Action] = []
    for action in plan.actions:
        if not action.writes:
            continue
        assert action.attachment is not None
        destination = plan.out_dir / action.relpath
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as handle:
                handle.write(action.attachment.content)
        except FileExistsError as exc:
            raise ApplyError(
                f"{action.relpath} appeared after the plan was made; nothing was "
                "overwritten. Re-run to file the rest."
            ) from exc
        written.append(action)
    return written


def tree_state(root: Path) -> dict[str, int]:
    """Every file under `root`, with its size. The dry run's evidence.

    Taken before and after planning so the tool can say what it found rather
    than assert what it did not do. Sizes rather than a bare listing, because
    "same names, different bytes" is exactly the failure this is watching for.
    """
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root).as_posix()): path.stat().st_size
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
