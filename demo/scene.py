#!/usr/bin/env python3
"""The recorded scene. EDIT THIS FILE for a new piece — it is the Playwright
equivalent of a VHS tape. The rendering is not here: demo/lib/sheet.py is
shared by all four pieces and builds every frame.

Four beats, about 18 seconds, in the one shape all four clips use:

  1. BEFORE   fixtures/mailbox/ — a flat pile of .eml, nothing sorted, listed
              off disk rather than described.
  2. COMMAND  one line, and the real stdout it printed.
  3. AFTER    filed/index.xlsx, the Index sheet: one row per attachment, where
              it went and under which rule.
  4. AFTER    the same sheet, filtered to the rows carrying a note — the cases
              the tool refused to guess about. This is the beat that sells it.

Beats 3 and 4 open the file the run in beat 2 had just written, read off disk
at record time. Nothing in this file knows what is in that workbook; if
file_mail.py did not write it, `read_table` raises and there is no clip.

The mailbox is invented. No real sender, client or message appears here or in
the recording.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "demo" / "lib"))

import sheet  # noqa: E402

INDEX_COLUMNS = ["date", "original_filename", "new_path", "rule", "status", "note"]
WIDTHS = {"note": 3.4, "new_path": 2.3, "original_filename": 1.2,
          "date": 1.35, "rule": 0.85, "status": 0.65}


def record(video_dir: Path) -> Path:
    mailbox = REPO / "fixtures" / "mailbox"

    # Beat 1 is built before the tool runs, so the BEFORE frame cannot
    # accidentally be showing anything the run produced.
    before = sheet.view(sheet.read_dir(mailbox, "*.eml", base=REPO), limit=13)

    command = sheet.run_command(
        [sys.executable, "file_mail.py", "fixtures/mailbox", "--brief", "--quiet"],
        cwd=REPO,
    )

    index = sheet.read_table(REPO / "filed" / "index.xlsx", "Index", base=REPO)

    # The rows worth pointing at are found by reading the file's own note
    # column, not by hardcoding which rows they are.
    noted = sheet.rows_where(index, "note", bool)
    filed_view = sheet.view(index, INDEX_COLUMNS, widths=WIDTHS)
    noted_view = sheet.tint(
        sheet.view(index, INDEX_COLUMNS, rows=noted, widths=WIDTHS), noted, "flag"
    )

    with sheet.Scene(video_dir) as scene:
        scene.show(
            sheet.grid_html(
                before,
                step="BEFORE",
                said="the mailbox as it arrived — nothing sorted, nothing named",
                kind="before",
            ),
            sheet.HOLD_BEFORE,
        )
        scene.show(
            sheet.terminal_html(
                command,
                said="one command: file every attachment, write the index",
            ),
            sheet.HOLD_COMMAND,
        )
        scene.show(
            sheet.grid_html(
                filed_view,
                step="AFTER",
                said="one row per attachment: what it was, where it went, which rule sent it",
            ),
            sheet.HOLD_AFTER / 2,
        )
        scene.show(
            sheet.grid_html(
                noted_view,
                step="AFTER",
                said="and every case it would not guess about, with the reason",
                legend={"flag": f"{len(noted)} of {len(index.rows)} rows carry a note"},
            ),
            sheet.HOLD_AFTER / 2,
        )

    return scene.video_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    args.video_dir.mkdir(parents=True, exist_ok=True)
    print(record(args.video_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
