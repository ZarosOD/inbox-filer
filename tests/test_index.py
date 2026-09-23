"""The index sheet: what is in it, and that it comes out the same every time."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

import pytest

from inbox_filer import index
from inbox_filer.apply import apply_plan
from inbox_filer.plan import build_plan


@pytest.fixture
def plan(messages, rules, tmp_path):
    return build_plan(messages, rules, tmp_path / "filed")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_the_columns_are_the_ones_the_brief_asked_for(plan, tmp_path):
    path = tmp_path / "index.csv"
    index.write_csv(path, plan)

    header = read_csv(path)[0].keys()
    for column in ("date", "sender", "subject", "original_filename", "new_path", "size_bytes", "rule"):
        assert column in header


def test_every_message_in_the_mailbox_reaches_the_index(plan, tmp_path, messages):
    path = tmp_path / "index.csv"
    index.write_csv(path, plan)

    sources = {row["source_message"] for row in read_csv(path)}
    assert sources == {m.source.name for m in messages}


def test_the_unsorted_rows_carry_their_reason(plan, tmp_path):
    index.write_csv(tmp_path / "index.csv", plan)
    rows = read_csv(tmp_path / "index.csv")

    unsorted = [row for row in rows if row["rule"] == "unsorted"]
    assert unsorted
    for row in unsorted:
        assert row["note"], row["new_path"]


def test_the_collision_row_records_the_suffix_and_the_original_name(plan, tmp_path):
    index.write_csv(tmp_path / "index.csv", plan)
    rows = read_csv(tmp_path / "index.csv")

    renamed = [row for row in rows if row["status"] == "filed-renamed"]
    assert len(renamed) == 1
    assert renamed[0]["original_filename"] == "invoice.pdf"
    assert renamed[0]["new_path"].endswith("-2.pdf")
    assert "was taken by a different file" in renamed[0]["note"]


def test_the_undecodable_row_has_no_path_and_a_reason(plan, tmp_path):
    index.write_csv(tmp_path / "index.csv", plan)
    rows = read_csv(tmp_path / "index.csv")

    row = next(r for r in rows if r["status"] == "unreadable-attachment")
    assert row["new_path"] == ""
    assert row["original_filename"] == "meeting-notes.txt"
    assert "x-unknown-9000" in row["note"]


def test_sizes_are_the_attachment_sizes(plan, tmp_path):
    index.write_csv(tmp_path / "index.csv", plan)
    rows = read_csv(tmp_path / "index.csv")

    by_path = {a.relpath: a for a in plan.actions if a.attachment}
    for row in rows:
        if row["new_path"]:
            assert int(row["size_bytes"]) == by_path[row["new_path"]].size


# --- reproducibility --------------------------------------------------------


def test_the_csv_is_identical_when_written_twice(plan, tmp_path):
    index.write_csv(tmp_path / "one.csv", plan)
    index.write_csv(tmp_path / "two.csv", plan)

    assert (tmp_path / "one.csv").read_bytes() == (tmp_path / "two.csv").read_bytes()


def with_a_moved_clock(data: bytes) -> bytes:
    """The same workbook as a machine whose clock reads differently wrote it.

    Both clocks move: the zip member stamps and the Office document's own
    `dcterms` timestamps. This exists because writing the file twice inside one
    test proves nothing — both saves land in the same second, so the check
    passes whether or not anything was flattened. Moving the clock by hand is
    what makes the assertion load-bearing.
    """
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            body = source.read(item.filename)
            if item.filename == "docProps/core.xml":
                body = index._TIMESTAMP.sub(rb"\g<1>2031-07-04T11:22:33Z\g<2>", body)
            info = zipfile.ZipInfo(item.filename, date_time=(2031, 7, 4, 11, 22, 32))
            info.compress_type = item.compress_type
            info.external_attr = item.external_attr
            info.create_system = 0
            target.writestr(info, body)
    return out.getvalue()


def test_a_run_on_a_different_clock_produces_the_same_xlsx_bytes(plan, tmp_path):
    """The test that keeps `index._repack` honest.

    Not free: openpyxl stamps the save time into docProps/core.xml and the zip
    stamps it into every member. Writing the file twice in a row cannot show
    that — both saves land in the same second, so the bytes match with or
    without the flattening. Moving the clock by hand is the assertion that
    goes red when `_repack` stops being called."""
    path = tmp_path / "one.xlsx"
    index.write_xlsx(path, plan)
    written = path.read_bytes()

    assert index._repack(with_a_moved_clock(written)) == written


def test_the_xlsx_is_identical_when_written_twice(plan, tmp_path):
    """The weaker sibling of the test above, kept for what it does cover: two
    writes of one plan produce one file, clock aside."""
    index.write_xlsx(tmp_path / "one.xlsx", plan)
    index.write_xlsx(tmp_path / "two.xlsx", plan)

    assert (tmp_path / "one.xlsx").read_bytes() == (tmp_path / "two.xlsx").read_bytes()


def test_the_document_clock_is_flattened_not_just_the_zip(plan, tmp_path):
    """Two clocks, two fixes. Rewriting only the zip member timestamps would
    leave docProps/core.xml differing every run, and the file would still fail
    `cmp` while looking like it had been handled. Both are checked by name:
    openpyxl refreshes `modified` at save time whatever the properties said,
    so an epoch found *somewhere* in core.xml is not enough."""
    path = tmp_path / "index.xlsx"
    index.write_xlsx(path, plan)

    with zipfile.ZipFile(path) as book:
        core = book.read("docProps/core.xml").decode("utf-8")
        stamps = dict(re.findall(r"<dcterms:(created|modified)[^>]*>([^<]*)<", core))
        assert stamps == {
            "created": "1980-01-01T00:00:00Z",
            "modified": "1980-01-01T00:00:00Z",
        }
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in book.infolist())


def test_the_xlsx_is_identical_after_the_files_have_been_written(plan, tmp_path):
    """The acceptance criterion, at this level: the sheet describes the filing
    cabinet, so applying the plan must not change what it says."""
    index.write_xlsx(tmp_path / "before.xlsx", plan)

    apply_plan(plan)
    index.write_xlsx(tmp_path / "after.xlsx", plan)

    assert (tmp_path / "before.xlsx").read_bytes() == (tmp_path / "after.xlsx").read_bytes()


def test_the_xlsx_is_a_workbook_a_client_can_open(plan, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "index.xlsx"
    index.write_xlsx(path, plan)

    workbook = openpyxl.load_workbook(path)

    assert workbook.sheetnames == ["Index", "Summary"]
    sheet = workbook["Index"]
    assert sheet.max_row == len(plan.actions) + 1
    assert sheet.freeze_panes == "A2"
    # Sizes are numbers in the sheet even though they are text in the CSV, so
    # that sorting by size in a spreadsheet does what a client expects.
    size_column = index.COLUMNS.index("size_bytes") + 1
    values = [sheet.cell(row=r, column=size_column).value for r in range(2, sheet.max_row + 1)]
    assert any(isinstance(value, int) for value in values)


def test_the_summary_sheet_holds_no_per_run_numbers(plan, tmp_path):
    """A count of "files written this time" would make the sheet differ on
    every run while nothing about the filing had changed."""
    labels = [label for label, _ in index.summary_rows(plan)]

    assert not any("written" in label or "already" in label for label in labels)
    assert dict(index.summary_rows(plan))["attachments seen"] == plan.attachment_count


def test_the_xlsx_carries_no_wall_clock(plan, tmp_path):
    path = tmp_path / "index.xlsx"
    index.write_xlsx(path, plan)

    with zipfile.ZipFile(path) as archive:
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
        core = archive.read("docProps/core.xml").decode("utf-8")
    assert "1980-01-01T00:00:00Z" in core
    assert core.count("1980-01-01T00:00:00Z") == 2
