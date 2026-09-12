"""Arguments, the order things happen in, and exit codes you can alert on."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import index, report
from .apply import ApplyError, apply_plan, tree_state
from .mailbox import MailboxError, read_mailbox
from .models import UNREADABLE
from .plan import PlanError, build_plan
from .rules import RuleError, load_rules

OK = 0
NEEDS_ATTENTION = 1
"""With --fail-on-unsorted: something reached unsorted/ or would not decode."""

USAGE = 3
UNREADABLE_INPUT = 4
BUG = 5
"""A dry run that touched the disk, or a destination that moved under us.
Separate from the others because it means the tool, not the mailbox."""

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES = ROOT / "rules" / "office.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file_mail.py",
        description="File every attachment in a mailbox into named folders, and write an index sheet.",
    )
    parser.add_argument("mailbox", help="a directory of .eml files, or a Maildir")
    parser.add_argument(
        "--rules",
        default=str(DEFAULT_RULES),
        help="the rule file that decides folders and names (default: rules/office.json)",
    )
    parser.add_argument(
        "--out", default="filed", help="where the filing cabinet lives (default: filed)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the whole plan and write nothing, then re-read the output "
        "directory and report what is actually there",
    )
    parser.add_argument("--report", action="store_true", help="print the full summary")
    parser.add_argument(
        "--brief", action="store_true", help="print the five-line version: what a cron log wants"
    )
    parser.add_argument("--quiet", action="store_true", help="say nothing except the summary")
    parser.add_argument(
        "--fail-on-unsorted",
        action="store_true",
        help=f"exit {NEEDS_ATTENTION} if anything landed in unsorted/ or would not decode",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    say = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))

    try:
        rules = load_rules(args.rules)
    except RuleError as exc:
        print(f"file_mail.py: {exc}", file=sys.stderr)
        return USAGE

    try:
        messages = read_mailbox(Path(args.mailbox))
    except MailboxError as exc:
        print(f"file_mail.py: {exc}", file=sys.stderr)
        return UNREADABLE_INPUT

    out_dir = Path(args.out)
    say(f"read {len(messages)} messages from {args.mailbox}")

    # Taken before planning so the dry run has something to compare against.
    # Planning reads this directory (that is how it recognises files it has
    # already filed), so "did reading it change it" is a real question.
    before = tree_state(out_dir)

    try:
        plan = build_plan(messages, rules, out_dir)
    except PlanError as exc:
        print(f"file_mail.py: {exc}", file=sys.stderr)
        return USAGE

    if args.dry_run:
        after = tree_state(out_dir)
        print(report.render_plan(plan, rules, before, after), end="")
        return BUG if before != after else _exit_code(args, plan)

    try:
        written = apply_plan(plan)
    except ApplyError as exc:
        print(f"file_mail.py: {exc}", file=sys.stderr)
        return BUG

    csv_path = out_dir / "index.csv"
    xlsx_path = out_dir / "index.xlsx"
    files = {
        str(csv_path): index.write_csv(csv_path, plan),
        str(xlsx_path): index.write_xlsx(xlsx_path, plan),
    }

    if args.brief:
        print(report.render_brief(plan, written, str(csv_path)), end="")
    elif args.report:
        print(report.render_report(plan, rules, written, files), end="")
    else:
        say(
            f"filed {len(written)}, left {plan.counts()['already-filed']} alone, "
            f"{len(plan.unsorted)} unsorted. Wrote {csv_path} and {xlsx_path}."
        )

    return _exit_code(args, plan)


def _exit_code(args: argparse.Namespace, plan) -> int:
    if args.fail_on_unsorted and (plan.unsorted or plan.counts()[UNREADABLE]):
        return NEEDS_ATTENTION
    return OK
