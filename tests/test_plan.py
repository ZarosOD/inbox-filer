"""Destinations, collisions, and the reasons something reaches unsorted/.

These run against the real fixture mailbox where they can, because the whole
point of the fixture is that the awkward cases are in it. Where a case needs a
shape the fixture does not have, it is built by hand from `Attachment` and
`Message` — the planner never touches a mailbox, which is what makes that
possible.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from inbox_filer.models import FILED, FILED_RENAMED, NO_ATTACHMENT, UNREADABLE, UNSORTED, Attachment, Message
from inbox_filer.plan import Destinations, PlanError, build_plan


def message(**overrides) -> Message:
    fields = {
        "source": Path("x.eml"),
        "message_id": "<x@b.example>",
        "subject": "Invoice 1",
        "sender_name": "A",
        "sender_email": "a@b.example",
        "date": datetime(2026, 3, 4, 9, 0, tzinfo=timezone.utc),
        "raw_date": "",
    }
    fields.update(overrides)
    return Message(**fields)


def attachment(content=b"one", filename="invoice.pdf") -> Attachment:
    return Attachment(1, filename, "application/pdf", content)


def by_path(plan) -> dict[str, object]:
    return {a.relpath: a for a in plan.actions if a.relpath}


# --- Destinations ------------------------------------------------------------


def test_a_free_path_is_taken_as_is(tmp_path):
    destinations = Destinations(tmp_path)

    assert destinations.claim("a/b.pdf", "digest") == ("a/b.pdf", False)


def test_the_same_bytes_twice_in_one_run_is_not_a_collision(tmp_path):
    """Two messages carrying the identical file is a forward, not a conflict."""
    destinations = Destinations(tmp_path)

    first = destinations.claim("a/b.pdf", "same")
    second = destinations.claim("a/b.pdf", "same")

    assert first == ("a/b.pdf", False)
    assert second == ("a/b.pdf", True)


def test_different_bytes_wanting_one_name_get_a_suffix(tmp_path):
    destinations = Destinations(tmp_path)

    destinations.claim("a/b.pdf", "one")
    assert destinations.claim("a/b.pdf", "two") == ("a/b-2.pdf", False)
    assert destinations.claim("a/b.pdf", "three") == ("a/b-3.pdf", False)


def test_a_file_already_on_disk_is_recognised_as_itself(tmp_path):
    """This is idempotency: the same attachment, filed again, is already filed."""
    import hashlib

    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.pdf").write_bytes(b"one")
    digest = hashlib.sha256(b"one").hexdigest()

    assert Destinations(tmp_path).claim("a/b.pdf", digest) == ("a/b.pdf", True)


def test_a_different_file_already_on_disk_is_stepped_around(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.pdf").write_bytes(b"something else")

    assert Destinations(tmp_path).claim("a/b.pdf", "mine") == ("a/b-2.pdf", False)


def test_a_directory_in_the_way_is_never_mistaken_for_the_file(tmp_path):
    (tmp_path / "a" / "b.pdf").mkdir(parents=True)

    assert Destinations(tmp_path).claim("a/b.pdf", "mine") == ("a/b-2.pdf", False)


def test_running_out_of_suffixes_fails_loudly_and_says_why(tmp_path):
    destinations = Destinations(tmp_path, limit=3)
    for index in range(4):
        destinations.claim("a/b.pdf", f"digest-{index}")

    with pytest.raises(PlanError, match="not distinguishing them"):
        destinations.claim("a/b.pdf", "one-too-many")


# --- the plan over the real fixture -----------------------------------------


def test_every_message_produces_at_least_one_action(messages, rules, tmp_path):
    plan = build_plan(messages, rules, tmp_path)

    assert {a.message.source.name for a in plan.actions} == {m.source.name for m in messages}


def test_no_destination_escapes_the_output_directory(messages, rules, tmp_path):
    """The traversal fixture is `../../../etc/passwd-notes.txt`."""
    plan = build_plan(messages, rules, tmp_path)

    for action in plan.actions:
        if not action.relpath:
            continue
        resolved = (tmp_path / action.relpath).resolve()
        assert resolved.is_relative_to(tmp_path.resolve()), action.relpath
        assert ".." not in action.relpath


def test_the_collision_fixture_produces_exactly_one_suffix(messages, rules, tmp_path):
    plan = build_plan(messages, rules, tmp_path)
    renamed = [a for a in plan.actions if a.status == FILED_RENAMED]

    assert len(renamed) == 1
    assert renamed[0].relpath.endswith("-2.pdf")
    assert "was taken by a different file" in renamed[0].note
    # And the file it collided with is also in the plan, unsuffixed.
    original = renamed[0].relpath.replace("-2.pdf", ".pdf")
    assert original in by_path(plan)


def test_an_unusable_filename_goes_to_unsorted_with_the_original_recorded(
    messages, rules, tmp_path
):
    plan = build_plan(messages, rules, tmp_path)
    actions = {a.message.source.name: a for a in plan.actions}

    nameless = actions["025-no-filename.eml"]
    assert nameless.rule == UNSORTED
    assert nameless.relpath.startswith("unsorted/")
    assert "declared no filename" in nameless.note
    # Never guessed: the generated name is traceable to the message.
    assert "fixture-025" in nameless.relpath

    punctuation = actions["026-punctuation-filename.eml"]
    assert punctuation.rule == UNSORTED
    assert "no letters or digits" in punctuation.note


def test_a_message_with_no_usable_date_goes_to_unsorted(messages, rules, tmp_path):
    """There is no year/month to file it under, and inventing one puts the
    document somewhere the client will never look for it."""
    plan = build_plan(messages, rules, tmp_path)
    actions = {a.message.source.name: a for a in plan.actions}

    for name in ("029-no-date.eml", "030-bad-date.eml"):
        action = actions[name]
        assert action.rule == UNSORTED, name
        assert action.relpath.startswith("unsorted/undated-"), name
        assert "no usable Date header" in action.note, name


def test_an_unmatched_attachment_says_which_rule_file_did_not_match(
    messages, rules, tmp_path
):
    plan = build_plan(messages, rules, tmp_path)
    actions = {a.message.source.name: a for a in plan.actions}

    action = actions["032-unmatched-0.eml"]
    assert action.rule == UNSORTED
    assert "no rule in office.json matched" in action.note


def test_a_message_with_no_attachment_is_a_row_and_nothing_else(messages, rules, tmp_path):
    plan = build_plan(messages, rules, tmp_path)
    actions = {a.message.source.name: a for a in plan.actions}

    action = actions["028-no-attachment.eml"]
    assert action.status == NO_ATTACHMENT
    assert action.relpath == ""
    assert not action.writes


def test_an_undecodable_attachment_is_a_row_and_nothing_else(messages, rules, tmp_path):
    plan = build_plan(messages, rules, tmp_path)
    actions = {a.message.source.name: a for a in plan.actions}

    action = actions["031-broken-charset.eml"]
    assert action.status == UNREADABLE
    assert action.relpath == "", "an attachment we cannot decode must not be written as empty"
    assert "x-unknown-9000" in action.note


def test_the_folders_come_out_where_the_rules_say(messages, rules, tmp_path):
    plan = build_plan(messages, rules, tmp_path)
    paths = set(by_path(plan))

    assert "2026/02/bank-statements/2026-02-01-statement-2026-01.pdf" in paths
    assert "2026/03/contracts/2026-03-24-bellweather-nda-signed.pdf" in paths
    # {sender_local} in the folder template.
    assert "2026/03/photos/crew/2026-03-13-job-4400-front.png" in paths
    # {sender_domain}, and the last rule catching what the others left.
    assert (
        "2026/03/suppliers/northgate-supplies-example/2026-03-30-price-list-april.xlsx" in paths
    )


def test_the_accented_filename_folds_rather_than_losing_a_letter(messages, rules, tmp_path):
    plan = build_plan(messages, rules, tmp_path)

    assert "2026/03/invoices/2026-03-18-rechnung-marz-9931.pdf" in by_path(plan)


def test_planning_twice_over_the_same_inputs_gives_the_same_answer(messages, rules, tmp_path):
    first = build_plan(messages, rules, tmp_path)
    second = build_plan(messages, rules, tmp_path)

    assert [a.relpath for a in first.actions] == [a.relpath for a in second.actions]
    assert [a.status for a in first.actions] == [a.status for a in second.actions]


# --- constructed shapes the fixture does not have ---------------------------


def test_two_attachments_on_one_message_both_get_planned(rules, tmp_path):
    sender = message(subject="Invoice 1")
    sender.attachments = [
        Attachment(1, "a.pdf", "application/pdf", b"one"),
        Attachment(2, "b.pdf", "application/pdf", b"two"),
    ]

    plan = build_plan([sender], rules, tmp_path)

    assert len(plan.actions) == 2
    assert all(a.status == FILED for a in plan.actions)


def test_the_status_describes_the_destination_not_the_run(rules, tmp_path):
    """The property the index sheet's reproducibility rests on."""
    first = message(source=Path("1.eml"))
    first.attachments = [attachment(b"one")]
    second = message(source=Path("2.eml"))
    second.attachments = [attachment(b"two")]

    before = build_plan([first, second], rules, tmp_path)
    statuses = [a.status for a in before.actions]
    assert statuses == [FILED, FILED_RENAMED]

    # Pretend the first run happened, then plan again.
    from inbox_filer.apply import apply_plan

    apply_plan(before)
    after = build_plan([first, second], rules, tmp_path)

    assert [a.status for a in after.actions] == statuses
    assert [a.relpath for a in after.actions] == [a.relpath for a in before.actions]
    assert all(a.existing for a in after.actions), "the run changed; the status did not"
