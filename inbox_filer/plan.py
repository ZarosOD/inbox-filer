"""Deciding what happens, before anything happens.

Every destination, every collision suffix and every reason for sending
something to unsorted/ is worked out here, against a `Destinations` view that
reads the output directory but never writes to it. `--dry-run` is then not a
special mode with its own code path — it is this module's output, printed. The
only difference between a dry run and a real one is whether `apply_plan` is
called afterwards, which is the property that makes the dry run worth trusting.
"""

from __future__ import annotations

import hashlib
import posixpath
from pathlib import Path

from .models import (
    FILED,
    FILED_RENAMED,
    NO_ATTACHMENT,
    UNREADABLE,
    UNSORTED,
    Action,
    Attachment,
    Message,
    Plan,
)
from .naming import UnusableName, fallback_name, slugify, split_name
from .rules import RuleSet

#: How many `-2`, `-3` … suffixes to try before giving up. A thousand genuinely
#: different files wanting one name is not a collision, it is a broken naming
#: template, and failing loudly beats filing `report-1000.pdf`.
SUFFIX_LIMIT = 999

#: Stands in for a destination that exists but is not a file we can compare
#: against, so it can never be mistaken for "already filed".
_OCCUPIED = "occupied"

#: What `{date}` renders as when the message has no usable one. Only ever
#: reached by an attachment already bound for unsorted/, because a missing date
#: is itself a reason to go there.
UNDATED = "undated"


class Destinations:
    """Which relative paths are taken, and by what bytes.

    Seeded lazily from disk and updated as the plan is built, so two
    attachments planned in the same run cannot both claim one name, and an
    attachment that is already on disk is recognised as itself.
    """

    def __init__(self, out_dir: Path, limit: int = SUFFIX_LIMIT) -> None:
        self.out_dir = out_dir
        self.limit = limit
        self._digests: dict[str, str] = {}

    def claim(self, relpath: str, digest: str) -> tuple[str, bool]:
        """Return (final path, already there) for bytes wanting `relpath`.

        Two outcomes, and the second is the whole idempotency story: a
        destination holding byte-identical content *is* this attachment,
        already filed, so the answer is that path and "nothing to do" — not a
        `-2` copy of everything on every run.
        """
        for candidate in self._candidates(relpath):
            existing = self._digest_of(candidate)
            if existing is None:
                self._digests[candidate] = digest
                return candidate, False
            if existing == digest:
                return candidate, True
        raise PlanError(
            f"{relpath} and {self.limit} suffixed variants are all taken by different "
            "files; the filename_template is not distinguishing them"
        )

    def _candidates(self, relpath: str):
        yield relpath
        stem, extension = posixpath.splitext(relpath)
        for suffix in range(2, self.limit + 2):
            yield f"{stem}-{suffix}{extension}"

    def _digest_of(self, relpath: str) -> str | None:
        if relpath in self._digests:
            return self._digests[relpath]
        path = self.out_dir / relpath
        if not path.exists():
            return None
        if not path.is_file():
            self._digests[relpath] = _OCCUPIED
            return _OCCUPIED
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self._digests[relpath] = digest
        return digest


class PlanError(Exception):
    """The plan cannot be completed. Nothing has been written when this is
    raised: planning finishes before applying starts, on purpose."""


def build_plan(messages: list[Message], rules: RuleSet, out_dir: Path) -> Plan:
    """Turn messages into one `Action` each, and one per attachment.

    Every message produces at least one action even when there is nothing to
    file, because the index sheet is supposed to account for the mailbox, not
    just for the files that came out of it.
    """
    destinations = Destinations(out_dir)
    actions: list[Action] = []

    for message in messages:
        for part in message.unreadable_parts:
            # Nothing to write and nothing to guess, but the client still
            # received it, so it gets a row.
            actions.append(
                Action(
                    message=message,
                    attachment=None,
                    rule="",
                    relpath="",
                    status=UNREADABLE,
                    note=part.reason,
                    declared_filename=part.raw_filename,
                )
            )

        if not message.attachments:
            if not message.unreadable_parts:
                actions.append(
                    Action(
                        message=message,
                        attachment=None,
                        rule="",
                        relpath="",
                        status=NO_ATTACHMENT,
                        note="the message carried no attachments",
                    )
                )
            continue

        for attachment in message.attachments:
            actions.append(_plan_one(message, attachment, rules, destinations))

    return Plan(actions=actions, message_count=len(messages), out_dir=out_dir)


def _plan_one(
    message: Message, attachment: Attachment, rules: RuleSet, destinations: Destinations
) -> Action:
    reasons: list[str] = []

    try:
        split = split_name(attachment.raw_filename, attachment.content_type)
    except UnusableName as exc:
        # Handled, not guessed: it still gets filed, under a name derived from
        # the message rather than invented, and the index carries the reason
        # and the original string next to each other.
        split = fallback_name(
            message.message_id, message.source.name, attachment.part_index, attachment.content_type
        )
        reasons.append(str(exc))

    rule = rules.match(message, attachment)
    if rule is None:
        reasons.append(f"no rule in {rules.source.name} matched this attachment")

    if message.date is None:
        reasons.append("the message has no usable Date header, so there is no year or month to file it under")

    filename = _render_filename(rules, message, split, rule.name if rule else UNSORTED)

    if reasons:
        relpath = posixpath.join(rules.unsorted_folder, filename)
        rule_name = UNSORTED
    else:
        assert rule is not None and message.date is not None
        relpath = _render_path(rules, message, rule, filename)
        rule_name = rule.name

    final, existing = destinations.claim(relpath, attachment.digest)

    # Status and note come from *where it ended up*, not from what this run
    # had to do. Same mailbox, same cabinet, same row — which is what lets the
    # second run's index sheet be byte-identical to the first's.
    if final == relpath:
        status = FILED
    else:
        status = FILED_RENAMED
        reasons.append(
            f"{posixpath.basename(relpath)} was taken by a different file, "
            f"so this one is {posixpath.basename(final)}"
        )

    return Action(
        message=message,
        attachment=attachment,
        rule=rule_name,
        relpath=final,
        status=status,
        note="; ".join(reasons),
        existing=existing,
    )


def _render_filename(rules: RuleSet, message: Message, split, rule_name: str) -> str:
    rendered = rules.filename_template.format(
        date=message.date.strftime("%Y-%m-%d") if message.date else UNDATED,
        slug=split.stem,
        ext=split.extension,
        sender_slug=slugify(message.sender_email) or "unknown-sender",
        sender_domain=slugify(message.sender_domain) or "unknown-domain",
        rule=slugify(rule_name),
    )
    # A template is data, and data can contain a slash. One component means one
    # component: the folder is the rule's business, not the filename's.
    return rendered.replace("/", "-").replace("\\", "-").strip() or "attachment"


def _render_path(rules: RuleSet, message: Message, rule, filename: str) -> str:
    assert message.date is not None
    folder = rule.folder.format(
        sender_slug=slugify(message.sender_email) or "unknown-sender",
        sender_domain=slugify(message.sender_domain) or "unknown-domain",
        sender_local=slugify(message.sender_local) or "unknown-sender",
        rule=slugify(rule.name),
    )
    rendered = rules.path_template.format(
        year=message.date.strftime("%Y"),
        month=message.date.strftime("%m"),
        folder=folder.strip("/"),
        filename=filename,
    )
    # Collapse the empty components a template with an unused placeholder
    # leaves behind, so `a//b` never reaches the filesystem.
    return posixpath.join(*[part for part in rendered.split("/") if part])
