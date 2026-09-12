"""The tool as a client runs it, including the acceptance criteria verbatim.

Four of the criteria on the brief are about behaviour nobody can see by reading
the code — the dry run writing nothing, the second run being a no-op, the
collision and the unparseable name coming out handled. They are tests here so
that "verified" means something more than "I ran it once and it looked right".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from inbox_filer.cli import BUG, NEEDS_ATTENTION, OK, USAGE, UNREADABLE_INPUT, main

REPO = Path(__file__).resolve().parent.parent


def run(*args: str) -> int:
    return main([str(a) for a in args])


def fingerprint(root: Path) -> dict[str, str]:
    """Path -> sha256 for every file under `root`. Stronger than a listing:
    "the tree is unchanged" has to mean the bytes too."""
    if not root.exists():
        return {}
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "filed"


# --- criterion 3: a dry run writes nothing ----------------------------------


def test_a_dry_run_on_an_empty_cabinet_writes_nothing(mailbox_path, out, capsys):
    code = run(mailbox_path, "--out", out, "--dry-run", "--quiet")

    assert code == OK
    assert not out.exists()
    assert "Nothing was written" in capsys.readouterr().out


def test_a_dry_run_over_an_existing_cabinet_changes_not_one_byte(mailbox_path, out, capsys):
    """The harder half: planning *reads* the output directory, because that is
    how it recognises what it has already filed."""
    assert run(mailbox_path, "--out", out, "--quiet") == OK
    before = fingerprint(out)
    assert before

    code = run(mailbox_path, "--out", out, "--dry-run", "--quiet")

    assert code == OK
    assert fingerprint(out) == before
    assert "still holds the same" in capsys.readouterr().out


def test_the_dry_run_prints_the_whole_plan(mailbox_path, out, capsys, messages):
    run(mailbox_path, "--out", out, "--dry-run", "--quiet")
    printed = capsys.readouterr().out

    # One line per attachment, plus one per message with nothing to file.
    attachments = sum(len(m.attachments) for m in messages)
    extra = sum(1 for m in messages if not m.attachments and not m.unreadable_parts)
    unreadable = sum(len(m.unreadable_parts) for m in messages)
    verbs = ("would file", "already filed", "nothing to file", "cannot read")
    planned = sum(1 for line in printed.splitlines() if line.strip().startswith(verbs))
    assert planned == attachments + extra + unreadable


def test_a_dry_run_that_wrote_something_would_report_itself(mailbox_path, out, monkeypatch, capsys):
    """The proof line is only worth printing if it can fail. Forcing a write
    mid-plan is the only way to see the failure branch."""
    from inbox_filer import plan as plan_module

    real = plan_module.build_plan

    def sneaky(messages, rules, out_dir):
        result = real(messages, rules, out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "oops.txt").write_text("written during a dry run", encoding="utf-8")
        return result

    monkeypatch.setattr("inbox_filer.cli.build_plan", sneaky)

    code = run(mailbox_path, "--out", out, "--dry-run", "--quiet")

    assert code == BUG
    assert "SOMETHING WAS WRITTEN DURING A DRY RUN" in capsys.readouterr().out


# --- criterion 4: the second run is a no-op ---------------------------------


def test_a_second_run_changes_nothing_at_all(mailbox_path, out):
    assert run(mailbox_path, "--out", out, "--quiet") == OK
    before = fingerprint(out)

    assert run(mailbox_path, "--out", out, "--quiet") == OK

    assert fingerprint(out) == before, "a second run must not duplicate, rename or rewrite"


def test_the_index_is_byte_identical_on_the_second_run(mailbox_path, out):
    run(mailbox_path, "--out", out, "--quiet")
    csv_bytes = (out / "index.csv").read_bytes()
    xlsx_bytes = (out / "index.xlsx").read_bytes()

    run(mailbox_path, "--out", out, "--quiet")

    assert (out / "index.csv").read_bytes() == csv_bytes
    assert (out / "index.xlsx").read_bytes() == xlsx_bytes


def test_a_third_run_is_still_a_no_op(mailbox_path, out):
    """Suffixed files are the ones at risk: `invoice-2.pdf` has to be
    recognised as itself, not stepped around into `invoice-3.pdf`."""
    run(mailbox_path, "--out", out, "--quiet")
    run(mailbox_path, "--out", out, "--quiet")
    before = fingerprint(out)

    run(mailbox_path, "--out", out, "--quiet")

    assert fingerprint(out) == before
    assert not any("-3." in name for name in fingerprint(out))


def test_a_deleted_file_is_restored_by_the_next_run(mailbox_path, out):
    """The useful corollary. Filing again repairs the cabinet rather than
    noticing nothing, and the index still says the same thing."""
    run(mailbox_path, "--out", out, "--quiet")
    before = fingerprint(out)
    victim = next(name for name in before if name.endswith(".pdf"))
    (out / victim).unlink()

    assert run(mailbox_path, "--out", out, "--quiet") == OK

    assert fingerprint(out) == before


# --- criterion 5: the collision and the unparseable name --------------------


def test_the_collision_lands_and_is_logged(mailbox_path, out):
    run(mailbox_path, "--out", out, "--quiet")

    invoices = sorted(p.name for p in (out / "2026" / "03" / "invoices").iterdir())
    assert "2026-03-25-invoice.pdf" in invoices
    assert "2026-03-25-invoice-2.pdf" in invoices
    # Different documents, not a duplicate.
    first = (out / "2026/03/invoices/2026-03-25-invoice.pdf").read_bytes()
    second = (out / "2026/03/invoices/2026-03-25-invoice-2.pdf").read_bytes()
    assert first != second
    assert "was taken by a different file" in (out / "index.csv").read_text(encoding="utf-8")


def test_the_unparseable_names_land_in_unsorted_and_are_logged(mailbox_path, out):
    run(mailbox_path, "--out", out, "--quiet")

    unsorted = sorted(p.name for p in (out / "unsorted").iterdir())
    assert any("fixture-025" in name for name in unsorted)
    assert any("fixture-026" in name for name in unsorted)
    text = (out / "index.csv").read_text(encoding="utf-8")
    assert "declared no filename" in text
    assert "no letters or digits" in text


def test_nothing_is_written_outside_the_output_directory(mailbox_path, tmp_path):
    """The mailbox holds `../../../etc/passwd-notes.txt`."""
    out = tmp_path / "filed"
    run(mailbox_path, "--out", out, "--quiet")

    strays = [p for p in tmp_path.iterdir() if p != out]
    assert strays == []
    assert (out / "2026/03/invoices/2026-03-27-passwd-notes.txt").is_file()


# --- exit codes and argument handling ---------------------------------------


def test_a_clean_run_exits_zero(mailbox_path, out):
    assert run(mailbox_path, "--out", out, "--quiet") == OK


def test_fail_on_unsorted_exits_one_when_something_needs_a_look(mailbox_path, out):
    assert run(mailbox_path, "--out", out, "--quiet", "--fail-on-unsorted") == NEEDS_ATTENTION


def test_fail_on_unsorted_exits_zero_when_everything_matched(tmp_path, mailbox_path):
    """A mailbox with only tidy messages in it — what a client's own mailbox
    looks like once the rules are right."""
    tidy = tmp_path / "tidy"
    tidy.mkdir()
    for name in ("001-invoice-northgate-supplies-10042.eml", "010-receipt-0.eml"):
        (tidy / name).write_bytes((mailbox_path / name).read_bytes())

    assert run(tidy, "--out", tmp_path / "filed", "--quiet", "--fail-on-unsorted") == OK


def test_a_missing_mailbox_exits_four_and_says_so(tmp_path, capsys):
    code = run(tmp_path / "absent", "--out", tmp_path / "filed", "--quiet")

    assert code == UNREADABLE_INPUT
    assert "no such mailbox" in capsys.readouterr().err


def test_a_broken_rule_file_exits_three_before_reading_any_mail(tmp_path, mailbox_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"rules": [{"name": "x", "folder": "x", "when": {"nope": "1"}}]}', "utf-8")
    out = tmp_path / "filed"

    code = run(mailbox_path, "--out", out, "--rules", bad, "--quiet")

    assert code == USAGE
    assert not out.exists(), "a bad rule file must not produce a half-filed cabinet"
    assert "nope" in capsys.readouterr().err


def test_brief_output_is_five_lines(mailbox_path, out, capsys):
    run(mailbox_path, "--out", out, "--quiet", "--brief")

    assert len(capsys.readouterr().out.strip().splitlines()) == 5


def test_the_report_names_everything_that_needs_a_look(mailbox_path, out, capsys):
    run(mailbox_path, "--out", out, "--quiet", "--report")
    printed = capsys.readouterr().out

    assert "needs a look" in printed
    # A message with nothing attached is not a problem and is not on that list.
    attention = printed.split("needs a look")[1]
    assert "carried no attachments" not in attention
