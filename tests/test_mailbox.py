"""Does the reader read the mailbox, or does it just agree with itself?

Every assertion here is against `tests/expected.json`, which
`fixtures/generate_mailbox.py` writes from the same values it builds the
messages from. So a bug in the reader shows up as a disagreement with what was
sent, not as a passing test that merely records current behaviour.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from inbox_filer.mailbox import MailboxError, find_messages, read_mailbox, read_message
from inbox_filer.models import Message


def test_every_generated_message_is_found(messages, expected):
    assert [m.source.name for m in messages] == [m["file"] for m in expected["messages"]]


def test_senders_and_subjects_match_what_was_sent(by_file, expected):
    for entry in expected["messages"]:
        message = by_file[entry["file"]]
        assert message.sender_email == entry["sender_email"], entry["file"]
        assert message.sender_name == entry["sender_name"], entry["file"]
        assert message.subject == entry["subject"], entry["file"]


def test_attachment_bytes_survive_the_round_trip(by_file, expected):
    """The strongest statement available: same sha256 in and out."""
    for entry in expected["messages"]:
        readable = [a for a in entry["attachments"] if a["decodable"]]
        message = by_file[entry["file"]]
        assert len(message.attachments) == len(readable), entry["file"]
        for attachment, truth in zip(message.attachments, readable):
            assert hashlib.sha256(attachment.content).hexdigest() == truth["sha256"]
            assert attachment.size == truth["size"]


def test_declared_filenames_are_reported_verbatim(by_file, expected):
    """Including the awkward ones. The index shows what the message claimed,
    which is only useful if it is not quietly cleaned up first."""
    for entry in expected["messages"]:
        readable = [a for a in entry["attachments"] if a["decodable"]]
        for attachment, truth in zip(by_file[entry["file"]].attachments, readable):
            assert attachment.raw_filename == (truth["declared_filename"] or "")


def test_dates_parse_where_there_is_a_date(by_file, expected):
    for entry in expected["messages"]:
        message = by_file[entry["file"]]
        if entry["date"] is None:
            assert message.date is None
        elif entry["file"].endswith("bad-date.eml"):
            assert message.date is None
        else:
            assert message.date is not None, entry["file"]
            assert message.date.strftime("%d %b %Y") in entry["date"]


# --- the awkward messages, named -------------------------------------------


def test_a_missing_date_header_is_recorded_not_guessed(by_file):
    message = by_file["029-no-date.eml"]

    assert message.date is None
    assert any("no Date header" in defect for defect in message.defects)


def test_an_unparseable_date_header_is_recorded_not_guessed(by_file):
    message = by_file["030-bad-date.eml"]

    assert message.date is None
    assert any("not a date" in defect for defect in message.defects)
    # The raw value is kept: it is the only thing that tells the client which
    # sender's mail system is producing them.
    assert message.raw_date == "Sometime last Tuesday"


def test_a_message_with_no_attachments_reads_as_a_message(by_file):
    message = by_file["028-no-attachment.eml"]

    assert message.attachments == []
    assert message.unreadable_parts == []
    assert message.subject == "Re: the March schedule"


def test_an_undecodable_attachment_is_listed_not_dropped(by_file):
    message = by_file["031-broken-charset.eml"]

    assert message.attachments == []
    assert len(message.unreadable_parts) == 1
    part = message.unreadable_parts[0]
    assert part.raw_filename == "meeting-notes.txt"
    assert "x-unknown-9000" in part.reason


def test_an_attachment_with_no_filename_still_arrives(by_file):
    message = by_file["025-no-filename.eml"]

    assert len(message.attachments) == 1
    assert message.attachments[0].raw_filename == ""
    assert message.attachments[0].content.startswith(b"%PDF")


def test_encoded_words_are_decoded(by_file):
    """The message carries `=?utf-8?...?=`; the reader should not."""
    message = by_file["022-umlaut.eml"]

    assert "März" in message.subject
    assert message.sender_name == "Jürgen Falk"
    assert message.attachments[0].raw_filename == "Rechnung-März-9931.pdf"
    assert "=?" not in message.subject


def test_two_attachments_on_one_message_keep_their_order(by_file):
    message = by_file["016-site-photo-0.eml"]

    assert [a.raw_filename for a in message.attachments] == [
        "job-4400-front.png",
        "job-4400-rear.png",
    ]
    assert [a.part_index for a in message.attachments] == [1, 2]


# --- the mailbox itself -----------------------------------------------------


def test_messages_come_back_in_a_stable_order(mailbox_path):
    """Collision suffixes depend on this, so it is not a cosmetic property."""
    assert find_messages(mailbox_path) == sorted(find_messages(mailbox_path))


def test_a_maildir_is_read_too(tmp_path, mailbox_path):
    maildir = tmp_path / "Maildir"
    (maildir / "cur").mkdir(parents=True)
    (maildir / "new").mkdir()
    sources = sorted(mailbox_path.glob("*.eml"))[:4]
    for index, source in enumerate(sources):
        target = maildir / ("cur" if index % 2 else "new") / source.name
        target.write_bytes(source.read_bytes())

    assert len(read_mailbox(maildir)) == 4


def test_a_missing_mailbox_says_so(tmp_path):
    with pytest.raises(MailboxError, match="no such mailbox"):
        read_mailbox(tmp_path / "nope")


def test_an_empty_mailbox_says_what_it_expected(tmp_path):
    (tmp_path / "empty").mkdir()

    with pytest.raises(MailboxError, match=r"\*\.eml"):
        read_mailbox(tmp_path / "empty")


def test_a_file_that_is_not_a_message_does_not_crash_the_run(tmp_path):
    """A stray file in the mail directory should cost one row, not the run."""
    (tmp_path / "junk.eml").write_bytes(b"this is not an email at all\n")

    message = read_message(tmp_path / "junk.eml")

    assert isinstance(message, Message)
    assert message.attachments == []
    assert message.date is None
