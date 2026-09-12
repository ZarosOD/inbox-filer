"""demo/lib/tree.py — the helper the tape uses to show the filed cabinet.

Same reasoning as test_demo_preview.py next door: the recording is part of the
deliverable, and a helper that only gets exercised by `make demo` is a helper
that breaks silently between recordings. What pytest cannot check is whether
the output fits the terminal width, so one beat of demo.tape uses it too.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TREE = REPO / "demo" / "lib" / "tree.py"


def load():
    spec = importlib.util.spec_from_file_location("demo_tree", TREE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_tree"] = module
    spec.loader.exec_module(module)
    return module


tree = load()


@pytest.fixture
def cabinet(tmp_path: Path) -> Path:
    """A small stand-in for filed/, with a directory deep enough to truncate."""
    root = tmp_path / "filed"
    for name in ("2026/03/invoices", "2026/03/photos/crew", "unsorted"):
        (root / name).mkdir(parents=True)
    for index in range(5):
        (root / "2026/03/invoices" / f"invoice-{index}.pdf").write_bytes(b"x" * 100)
    (root / "2026/03/photos/crew/job.png").write_bytes(b"y" * 50)
    (root / "unsorted/menu.csv").write_bytes(b"z" * 10)
    (root / "index.csv").write_bytes(b"header\n")
    return root


def render(root: Path, **kwargs) -> str:
    options = {"depth": 6, "per_dir": None, "max_lines": 0, **kwargs}
    return "\n".join(tree.render(root, **options))


def test_every_file_appears_when_nothing_is_capped(cabinet):
    printed = render(cabinet)

    for index in range(5):
        assert f"invoice-{index}.pdf" in printed
    assert "menu.csv" in printed


def test_the_footer_counts_what_is_there_not_what_is_shown(cabinet):
    printed = render(cabinet, per_dir=1)

    assert "8 files in 6 folders" in printed


def test_a_capped_directory_says_how_many_it_hid(cabinet):
    """The point of the cap. A tree that is merely cut off by the terminal
    reads as the whole thing, which is a lie the next question exposes."""
    printed = render(cabinet, per_dir=2)

    assert "invoice-0.pdf" in printed
    assert "invoice-4.pdf" not in printed
    assert "… and 3 more files" in printed


def test_directories_survive_a_cap_that_files_do_not(cabinet):
    """Losing a file costs one example; losing a folder costs the structure."""
    printed = render(cabinet, per_dir=1)

    for folder in ("2026/", "03/", "invoices/", "photos/", "crew/", "unsorted/"):
        assert folder in printed


def test_the_depth_limit_reports_what_is_below_it(cabinet):
    printed = render(cabinet, depth=3)

    assert "invoices/" in printed
    assert "invoice-0.pdf" not in printed
    assert "… 5 more" in printed


def test_the_line_cap_says_how_many_lines_it_dropped(cabinet):
    printed = render(cabinet, max_lines=5)

    assert "more lines" in printed
    # The footer is appended after the cap, so the totals always survive.
    assert "8 files in 6 folders" in printed


def test_entries_are_sorted_so_two_runs_look_the_same(cabinet):
    assert render(cabinet) == render(cabinet)


def test_a_missing_directory_is_named_not_a_traceback(tmp_path, capsys):
    """On camera this is the difference between "the previous command did not
    run" and "something went wrong somewhere"."""
    code = tree.main([str(tmp_path / "absent")])

    assert code == 2
    assert "no such directory" in capsys.readouterr().err


def test_a_file_where_a_directory_was_expected_says_so(tmp_path, capsys):
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")

    code = tree.main([str(target)])

    assert code == 2
    assert "not a directory" in capsys.readouterr().err


def test_it_runs_as_a_command(cabinet):
    assert tree.main([str(cabinet), "--per-dir", "1"]) == 0


# --- --per-dir 0: folders and counts, no filenames --------------------------


def test_counts_only_shows_no_filenames(cabinet):
    printed = render(cabinet, per_dir=0)

    assert "invoice-0.pdf" not in printed
    assert "menu.csv" not in printed
    assert "index.csv" not in printed


def test_counts_only_puts_the_count_on_the_folder(cabinet):
    printed = render(cabinet, per_dir=0)

    assert "invoices/ — 5 files" in printed
    assert "crew/ — 1 file" in printed, "singular, not '1 files'"
    assert "unsorted/ — 1 file" in printed


def test_counts_only_labels_the_root_too(cabinet):
    """index.csv sits at the top level and would otherwise vanish silently."""
    printed = render(cabinet, per_dir=0)

    assert printed.splitlines()[0] == "filed/ — 1 file"


def test_counts_only_omits_a_label_for_a_folder_holding_only_folders(cabinet):
    printed = render(cabinet, per_dir=0)

    assert "2026/\n" in printed + "\n"
    assert "2026/ —" not in printed


def test_counts_only_does_not_repeat_itself_at_the_depth_limit(cabinet):
    """The folder label already accounted for the files directly inside, so a
    `… N more` saying the same number again is noise that reads as a second
    pile of files."""
    printed = render(cabinet, per_dir=0, depth=4)

    assert "crew/ — 1 file" in printed
    assert "… 1 more" not in printed


def test_counts_only_still_reports_what_is_deeper_than_the_limit(cabinet):
    printed = render(cabinet, per_dir=0, depth=3)

    assert "photos/" in printed
    assert "crew/ — 1 file" not in printed
    assert "… 2 more" in printed
