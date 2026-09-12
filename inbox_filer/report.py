"""What the run prints.

Two audiences. `--report` is for the person who ran it and wants to know the
mailbox is handled. `--dry-run` is for the person deciding whether to let it
run at all, which is a harder sell and gets the longer output: every
destination, the exceptions called out, and then the output directory's actual
state, re-read after planning, so the "nothing was written" line is a
measurement rather than a promise.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .models import (
    ALREADY_FILED,
    FILED,
    FILED_RENAMED,
    NO_ATTACHMENT,
    UNREADABLE,
    UNSORTED,
    Action,
    Plan,
)
from .rules import RuleSet

def human_size(size: int) -> str:
    if size < 1000:
        return f"{size} B"
    if size < 1_000_000:
        return f"{size / 1000:.1f} kB"
    return f"{size / 1_000_000:.1f} MB"


def needs_attention(action: Action) -> bool:
    """Somebody has to decide something about this one.

    A message with no attachment is not on this list: nothing was filed and
    nothing should have been. It is in the index because the index accounts for
    the mailbox, and in the counts because it explains the arithmetic, but
    putting it in front of a person would be crying wolf.
    """
    return action.rule == UNSORTED or action.status == UNREADABLE


def _is_exception(action: Action) -> bool:
    """Anything that is not "a rule matched and it was filed"."""
    return needs_attention(action) or action.status == NO_ATTACHMENT


def _plan_order(action: Action) -> tuple:
    """Ordinary filings first, then everything that needs reading.

    The plan is long — one line per attachment — so whatever is last is what a
    reader's eye lands on. Putting the exceptions there is the same instinct as
    the rejects file in the feed cleaner: the interesting rows should not be
    the ones you have to scroll for.
    """
    return (_is_exception(action), action.relpath, action.message.source.name)


def render_plan(plan: Plan, rules: RuleSet, before: dict[str, int], after: dict[str, int]) -> str:
    lines: list[str] = []
    lines.append(
        f"DRY RUN — planning {plan.attachment_count} attachments from "
        f"{plan.message_count} messages, using {rules.source}."
    )
    lines.append(f"Destination would be {plan.out_dir}/ — nothing below is written.")
    lines.append("")

    width = max((len(a.status) for a in plan.actions), default=6)
    for action in sorted(plan.actions, key=_plan_order):
        verb = _would(action)
        if action.relpath:
            lines.append(f"  {verb:<{width + 6}} {action.relpath}")
        else:
            lines.append(f"  {verb:<{width + 6}} ({action.message.source.name})")
        if action.note:
            lines.append(f"  {'':<{width + 6}}   why: {action.note}")

    lines.append("")
    lines.extend(_counts_block(plan))
    lines.append("")
    lines.extend(_evidence(plan.out_dir, before, after))
    return "\n".join(lines) + "\n"


def _would(action: Action) -> str:
    """The plan's verb column. This is the one place the run matters: a reader
    deciding whether to let it loose wants to know what it will *do*, which is
    different from the status the index records."""
    if action.existing:
        return "already filed"
    return {
        FILED: "would file",
        FILED_RENAMED: "would file (renamed)",
        NO_ATTACHMENT: "nothing to file",
        UNREADABLE: "cannot read",
    }.get(action.status, action.status)


def _evidence(out_dir: Path, before: dict[str, int], after: dict[str, int]) -> list[str]:
    """The dry run's closing argument, and the only part of it that is a fact
    about the disk rather than about the plan."""
    if before != after:
        changed = sorted(set(before) ^ set(after)) or sorted(
            name for name in after if before.get(name) != after[name]
        )
        return [
            "SOMETHING WAS WRITTEN DURING A DRY RUN. This is a bug, please report it.",
            f"  changed: {', '.join(changed[:5])}",
        ]
    if not after:
        return [
            f"Nothing was written: {out_dir}/ does not exist. "
            "Re-read after planning, not assumed."
        ]
    total = sum(after.values())
    return [
        f"Nothing was written: {out_dir}/ still holds the same {len(after)} files "
        f"({human_size(total)}). Re-read after planning, not assumed."
    ]


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _counts_block(plan: Plan) -> list[str]:
    counts = plan.counts()
    by_rule = Counter(a.rule for a in plan.actions if a.attachment)
    unsorted = len(plan.unsorted)
    to_write = sum(1 for a in plan.actions if a.writes)
    # Three short lines rather than one long one: this goes to a terminal, and
    # a sentence that wraps is a sentence nobody reads to the end of.
    lines = [
        f"{plan.attachment_count} attachments: {plan.attachment_count - unsorted} filed "
        f"by a rule, {unsorted} sent to unsorted/, "
        f"{counts[FILED_RENAMED]} renamed around a collision.",
        f"{to_write} to write, {counts[ALREADY_FILED]} already filed and left alone.",
        f"Plus {_plural(counts[UNREADABLE], 'attachment')} that would not decode, "
        f"and {_plural(counts[NO_ATTACHMENT], 'message')} with nothing attached.",
    ]
    lines.append("")
    lines.append("by rule:")
    for name, count in sorted(by_rule.items(), key=lambda item: (item[0] == UNSORTED, item[0])):
        lines.append(f"  {name:<22} {count:>4}")
    return lines


def render_report(plan: Plan, rules: RuleSet, written: list[Action], files: dict[str, int]) -> str:
    counts = plan.counts()
    lines = [
        f"inbox-filer — {plan.message_count} messages, {plan.attachment_count} attachments",
        f"rules:  {rules.source} ({len(rules.rules)} rules, first match wins)",
        f"output: {plan.out_dir}/",
        "",
        f"wrote {len(written)} files"
        f"{f' ({human_size(sum(a.size for a in written))})' if written else ''}, "
        f"left {counts[ALREADY_FILED]} already-filed alone, "
        f"overwrote nothing.",
        "",
    ]
    lines.extend(_counts_block(plan))
    lines.append("")

    exceptions = [a for a in plan.actions if needs_attention(a)]
    if exceptions:
        lines.append(f"needs a look ({len(exceptions)}):")
        for action in exceptions:
            where = action.relpath or f"({action.message.source.name})"
            lines.append(f"  {where}")
            lines.append(f"    {action.note}")
        lines.append("")

    for name, count in files.items():
        lines.append(f"index:  {name} ({count} rows)")
    return "\n".join(lines) + "\n"


def render_brief(plan: Plan, written: list[Action], index_path: str) -> str:
    """The version a cron log wants: five lines, no table."""
    counts = plan.counts()
    return (
        f"{plan.message_count} messages, {plan.attachment_count} attachments\n"
        f"wrote {len(written)} ({counts[FILED_RENAMED]} renamed around a collision)\n"
        f"already filed, untouched {counts[ALREADY_FILED]}\n"
        f"unsorted {len(plan.unsorted)}, unreadable {counts[UNREADABLE]}, "
        f"no attachment {counts[NO_ATTACHMENT]}\n"
        f"index {index_path}\n"
    )
