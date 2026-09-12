"""The shapes everything else passes around.

Deliberately dumb containers. Reading a mailbox, matching a rule, planning a
move and writing the index are four separate jobs, and they only agree on
these types — which is what keeps the planner testable without a mailbox and
the matcher testable without a disk.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Statuses. They are the `status` column of the index sheet, so they are part
# of the deliverable's vocabulary and the README explains each one.
#
# Every one of them describes where an attachment ended up, never what this
# particular run had to do to get it there. That distinction is what makes the
# index sheet reproducible: running twice over an unchanged mailbox produces a
# byte-identical sheet, because the second run is describing the same cabinet.
# "Did this run write it or was it already there" is a fact about the run, so
# it lives on `Action.existing` and is reported on stdout, not in the sheet.
FILED = "filed"
FILED_RENAMED = "filed-renamed"
NO_ATTACHMENT = "no-attachment"
UNREADABLE = "unreadable-attachment"
"""A part the message declared and we could not decode. Nothing is written —
a zero-byte PDF in the client's folder is worse than a row saying why there is
no PDF — but it is still a row, because it still arrived."""

#: Not a status: a label the summary uses for actions whose bytes were already
#: at their destination.
ALREADY_FILED = "already-filed"

#: The rule name recorded when nothing matched. Not a real rule: it is the
#: absence of one, spelled out so it cannot be mistaken for a silent default.
UNSORTED = "unsorted"


@dataclass
class Attachment:
    """One attachment part, already decoded."""

    part_index: int
    """1-based position among the message's attachments. Part of the fallback
    name when the declared filename is unusable, so it has to be stable."""

    raw_filename: str
    """Exactly what the message claimed, after RFC 2047/2231 decoding, or ""
    when it declared nothing. Recorded verbatim in the index even when it is
    not what the file ends up being called."""

    content_type: str
    content: bytes

    @property
    def size(self) -> int:
        return len(self.content)

    @property
    def digest(self) -> str:
        """sha256 of the bytes. The whole idempotency story rests on this: a
        destination holding these exact bytes is this attachment, already
        filed, and not something to write again or rename around."""
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class UnreadablePart:
    """A part the message declared and we could not decode.

    Keeps the declared filename apart from the explanation rather than folding
    both into one sentence. The index sheet has a column for what the message
    called the file, and "we could not read it" is not a reason to leave that
    column empty when the message told us.
    """

    part_index: int
    raw_filename: str
    reason: str


@dataclass
class Message:
    """One message, with whatever we could and could not read from it."""

    source: Path
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    date: datetime | None
    """None when the Date header was missing or unparseable. Not defaulted to
    "now" and not guessed from the file's mtime: the year/month folders are
    the client's filing cabinet, and a message filed under the wrong month is
    worse than one sitting in unsorted/ with a reason next to it."""

    raw_date: str
    attachments: list[Attachment] = field(default_factory=list)
    defects: list[str] = field(default_factory=list)
    """Anything the parser noticed and could not fix, in plain words. These
    reach the index, so they are written for the person doing the filing."""

    unreadable_parts: list[UnreadablePart] = field(default_factory=list)
    """One entry per attachment part that would not decode. Kept apart from
    `defects` because each of these earns its own row in the index, whereas a
    broken Subject header does not."""

    @property
    def sender(self) -> str:
        """`Name <addr>` when there is a name, otherwise the bare address."""
        if self.sender_name and self.sender_email:
            return f"{self.sender_name} <{self.sender_email}>"
        return self.sender_email or self.sender_name

    @property
    def sender_domain(self) -> str:
        _, _, domain = self.sender_email.partition("@")
        return domain.lower()

    @property
    def sender_local(self) -> str:
        local, _, _ = self.sender_email.partition("@")
        return local.lower()


@dataclass(frozen=True)
class Action:
    """What the tool intends to do about one attachment, decided before any
    of it happens. A dry run is nothing more than the list of these, printed.
    """

    message: Message
    attachment: Attachment | None
    rule: str
    """The name of the rule that matched, or UNSORTED."""

    relpath: str
    """Destination relative to the output directory, POSIX-style. Empty for a
    message with no attachment, which still gets an Action so that the index
    accounts for every message in the mailbox."""

    status: str
    note: str
    """Why this is not the boring case, in a sentence a client can read. Empty
    only for a plain `filed`. Derived from the message and the destination, so
    it says the same thing on every run."""

    declared_filename: str = ""
    """What the message called the file, for rows that have no `attachment` to
    ask. Only ever set for an undecodable part."""

    existing: bool = False
    """These exact bytes were already at `relpath` when the plan was built, so
    this run has nothing to write. A fact about the run, deliberately kept out
    of the index sheet."""

    @property
    def writes(self) -> bool:
        return self.status in (FILED, FILED_RENAMED) and not self.existing

    @property
    def size(self) -> int:
        return self.attachment.size if self.attachment else 0


@dataclass
class Plan:
    """Every action, plus the mailbox it came from."""

    actions: list[Action]
    message_count: int
    out_dir: Path

    def counts(self) -> dict[str, int]:
        counts = {FILED: 0, FILED_RENAMED: 0, ALREADY_FILED: 0, NO_ATTACHMENT: 0, UNREADABLE: 0}
        for action in self.actions:
            counts[action.status] = counts.get(action.status, 0) + 1
            if action.existing:
                counts[ALREADY_FILED] += 1
        return counts

    @property
    def unsorted(self) -> list[Action]:
        return [a for a in self.actions if a.rule == UNSORTED and a.attachment]

    @property
    def attachment_count(self) -> int:
        return sum(1 for a in self.actions if a.attachment)
