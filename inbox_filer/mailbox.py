"""Reading messages off disk.

The mailbox this ships with is a directory of `.eml` files under `fixtures/`,
so the demo needs no account and no credentials. A Maildir (`cur/`, `new/`) is
read the same way. Swapping either for IMAP is a change to this module and
nothing else: everything downstream takes `Message` objects.
"""

from __future__ import annotations

import email
import email.policy
from datetime import datetime
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from .models import Attachment, Message, UnreadablePart


class MailboxError(Exception):
    """The mailbox itself is unreadable — not one message in it."""


def find_messages(mailbox: Path) -> list[Path]:
    """Every message file in `mailbox`, in a stable order.

    The order matters more than it looks: when two attachments want the same
    destination, which one gets the plain name and which gets `-2` is decided
    by the order they are planned in. Sorting by path makes that deterministic
    rather than dependent on the filesystem's mood.
    """
    if not mailbox.exists():
        raise MailboxError(f"no such mailbox: {mailbox}")
    if not mailbox.is_dir():
        raise MailboxError(f"not a directory: {mailbox}")

    # Maildir keeps delivered mail in cur/ and new/; a flat directory of .eml
    # files is what most people hand you when you ask for "some emails".
    maildir_parts = [mailbox / name for name in ("cur", "new") if (mailbox / name).is_dir()]
    if maildir_parts:
        paths = [p for part in maildir_parts for p in part.iterdir() if p.is_file()]
    else:
        paths = [p for p in mailbox.iterdir() if p.is_file() and p.suffix.lower() == ".eml"]

    if not paths:
        raise MailboxError(
            f"{mailbox} holds no messages "
            "(expected *.eml files, or a Maildir with cur/ and new/)"
        )
    return sorted(paths)


def read_message(path: Path) -> Message:
    """Parse one message file. Never raises for a malformed message.

    A message we cannot fully read is still a message the client received, so
    every failure here becomes a note on the `Message` and, eventually, a row
    in the index. The only thing that is not allowed is for it to disappear.
    """
    defects: list[str] = []
    try:
        raw = path.read_bytes()
    except OSError as exc:  # pragma: no cover - depends on the filesystem
        raise MailboxError(f"cannot read {path}: {exc}") from exc

    parsed = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(parsed, EmailMessage)

    subject = _header(parsed, "Subject", defects)
    sender_name, sender_email = parseaddr(_header(parsed, "From", defects))
    if not sender_email:
        defects.append("the From header has no address in it")

    date, raw_date = _date(parsed, raw, defects)

    message = Message(
        source=path,
        message_id=_header(parsed, "Message-ID", defects),
        subject=subject.strip(),
        sender_name=sender_name.strip(),
        sender_email=sender_email.strip().lower(),
        date=date,
        raw_date=raw_date,
        defects=defects,
    )
    message.attachments, message.unreadable_parts = _attachments(parsed)
    return message


def read_mailbox(mailbox: Path) -> list[Message]:
    """Every message, sorted the way the planner will process them.

    Sorted by path rather than by date on purpose: the date is exactly the
    thing that can be missing or unreadable, and an ordering that changes when
    a header is malformed is an ordering that makes collisions non-repeatable.
    """
    return [read_message(path) for path in find_messages(mailbox)]


def _header(parsed: EmailMessage, name: str, defects: list[str]) -> str:
    """A header as a plain string, with encoded words already decoded.

    `email.policy.default` does the RFC 2047 work, but it raises rather than
    returning nonsense when a header is badly enough broken. That is a defect
    to record, not a reason to drop the message.
    """
    try:
        value = parsed.get(name)
    except Exception as exc:  # noqa: BLE001 - the policy raises several types
        defects.append(f"the {name} header could not be decoded ({exc})")
        return ""
    if value is None:
        return ""
    return str(value)


def _date(parsed: EmailMessage, raw: bytes, defects: list[str]) -> tuple[datetime | None, str]:
    """The message's date, and the string it was written as.

    Two failures that look alike and are not. "No Date header" is a mail client
    problem; "a Date header that is not a date" is a specific sender producing
    specific rubbish, and the client can only chase the second one if we hand
    back what was actually in the header.

    That means going around `email.policy.default`, which renders an
    unparseable Date as the empty string — faithful to the standard, and
    indistinguishable from an absent header by the time it reaches us. The
    unparsed value comes from a headers-only re-read under compat32, which does
    no interpreting at all.
    """
    try:
        header = parsed.get("Date")
    except Exception as exc:  # noqa: BLE001 - the policy raises several types
        defects.append(f"the Date header could not be decoded ({exc})")
        header = None

    if header is not None:
        moment = getattr(header, "datetime", None)
        if moment is not None:
            return moment, str(header)
        # The policy parsed it and got nothing. Fall through to the raw value.

    declared = _unparsed_header(raw, "Date")
    if not declared:
        defects.append("the message has no Date header")
        return None, ""

    # Worth one more attempt: compat32 hands back values the default policy
    # declines to render, and some of them are perfectly good dates.
    try:
        return parsedate_to_datetime(declared), declared
    except (TypeError, ValueError):
        defects.append(f"the Date header {declared!r} is not a date")
        return None, declared


def _unparsed_header(raw: bytes, name: str) -> str:
    """One header exactly as it was written. Headers only: no body is read."""
    headers = BytesHeaderParser(policy=email.policy.compat32).parsebytes(raw)
    value = headers.get(name)
    return "" if value is None else str(value).strip()


def _attachments(parsed: EmailMessage) -> tuple[list[Attachment], list[UnreadablePart]]:
    """Every attachment part, decoded, in the order the message carries them.

    `iter_attachments()` is the stdlib's own answer to "what is an attachment
    here", which means inline images and multipart/alternative bodies are
    already excluded. Anything it hands us that will not decode comes back in
    the second list instead of the first: not filed, because a zero-byte PDF
    in the client's folder is a worse outcome than a row saying why there is
    no PDF, and not dropped either.
    """
    attachments: list[Attachment] = []
    unreadable: list[UnreadablePart] = []
    index = 0
    for part in parsed.iter_attachments():
        index += 1
        try:
            raw_filename = part.get_filename() or ""
        except Exception as exc:  # noqa: BLE001 - a broken 2231 parameter
            unreadable.append(
                UnreadablePart(index, "", f"attachment {index} has an undecodable filename ({exc})")
            )
            continue

        described = f"attachment {index} ({raw_filename})" if raw_filename else f"attachment {index}"
        try:
            payload = part.get_content()
        except Exception as exc:  # noqa: BLE001 - malformed encodings vary
            unreadable.append(
                UnreadablePart(index, raw_filename, f"{described} could not be decoded: {exc}")
            )
            continue
        if isinstance(payload, str):
            payload = payload.encode("utf-8", "replace")
        elif not isinstance(payload, bytes):  # pragma: no cover - defensive
            unreadable.append(
                UnreadablePart(
                    index, raw_filename, f"{described} is not a file ({type(payload).__name__})"
                )
            )
            continue

        attachments.append(
            Attachment(
                part_index=index,
                raw_filename=raw_filename,
                content_type=part.get_content_type(),
                content=payload,
            )
        )
    return attachments, unreadable
