#!/usr/bin/env python3
"""Print a directory tree that fits on a screen.

Generic demo helper, like lib/preview.py next to it — nothing here knows what
this project does. It exists because `find | sort` wraps at GIF width and
`tree` is not installed on a clean machine, and the "after" half of a filing
demo is precisely a directory tree.

    python demo/lib/tree.py DIR [--depth N] [--per-dir N] [--max-lines N]

The caps are the point. A capped tree that says `… and 6 more` reads as a
sample; an uncapped one that happens to be cut off by the terminal reads as
the whole thing, which is a lie that costs you the next question. Directories
are always shown even when their contents are capped, so the shape of the
cabinet survives the truncation.

`--per-dir 0` is the one worth knowing about: no filenames at all, and each
folder carries the count of what is in it instead. On a tree wide enough to
matter that is the difference between fourteen lines and thirty, and the
shape is what the viewer is reading anyway — the filenames are a separate
beat.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ELBOW, TEE, PIPE, SPACE = "└── ", "├── ", "│   ", "    "


def count_label(directory: Path) -> str:
    """` — 3 files`, or nothing when the folder holds no files directly."""
    count = sum(1 for p in directory.iterdir() if p.is_file())
    if not count:
        return ""
    return f" — {count} file{'s' if count != 1 else ''}"


def walk(directory: Path, depth: int, per_dir: int | None, prefix: str = "") -> list[str]:
    entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
    directories = [p for p in entries if p.is_dir()]
    files = [p for p in entries if not p.is_dir()]

    # Cap files, never directories: losing a file to the cap costs one example,
    # losing a directory costs the structure, which is what the tree is for.
    # `per_dir == 0` goes further and drops the filenames entirely; the count
    # moves onto the folder's own line, which is where it reads better anyway.
    counts_only = per_dir == 0
    shown_files = [] if counts_only else (files if per_dir is None else files[:per_dir])
    hidden = 0 if counts_only else len(files) - len(shown_files)

    shown: list[Path] = [*directories, *shown_files]
    lines: list[str] = []
    for index, entry in enumerate(shown):
        last = index == len(shown) - 1 and hidden == 0
        connector = ELBOW if last else TEE
        if entry.is_dir():
            suffix = count_label(entry) if counts_only else ""
            lines.append(f"{prefix}{connector}{entry.name}/{suffix}")
            if depth == 1:
                inner = sum(1 for _ in entry.rglob("*"))
                if counts_only:
                    # The folder's own label already accounted for the files
                    # directly inside it; only what is deeper is still unsaid.
                    inner -= sum(1 for p in entry.iterdir() if p.is_file())
                if inner:
                    lines.append(f"{prefix}{SPACE if last else PIPE}{ELBOW}… {inner} more")
                continue
            lines.extend(
                walk(entry, depth - 1, per_dir, prefix + (SPACE if last else PIPE))
            )
        else:
            lines.append(f"{prefix}{connector}{entry.name}")
    if hidden:
        lines.append(f"{prefix}{ELBOW}… and {hidden} more file{'s' if hidden > 1 else ''}")
    return lines


def render(root: Path, depth: int, per_dir: int | None, max_lines: int) -> list[str]:
    header = f"{root.name or root}/" + (count_label(root) if per_dir == 0 else "")
    lines = [header, *walk(root, depth, per_dir)]
    if 0 < max_lines < len(lines):
        dropped = len(lines) - max_lines
        lines = [*lines[:max_lines], f"… {dropped} more lines"]

    files = sum(1 for p in root.rglob("*") if p.is_file())
    directories = sum(1 for p in root.rglob("*") if p.is_dir())
    total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    lines.append("")
    lines.append(
        f"{files} file{'s' if files != 1 else ''} in "
        f"{directories} folder{'s' if directories != 1 else ''}, {_size(total)}"
    )
    return lines


def _size(size: int) -> str:
    if size < 1000:
        return f"{size} B"
    if size < 1_000_000:
        return f"{size / 1000:.1f} kB"
    return f"{size / 1_000_000:.1f} MB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tree.py", description=__doc__.splitlines()[0])
    parser.add_argument("directory")
    parser.add_argument("--depth", type=int, default=4, help="levels to descend (default: 4)")
    parser.add_argument(
        "--per-dir",
        type=int,
        default=None,
        help="files to show per directory; 0 for none, with a count on each "
        "folder instead. Omit for all of them.",
    )
    parser.add_argument("--max-lines", type=int, default=0, help="overall cap, 0 for none")
    args = parser.parse_args(argv)

    root = Path(args.directory)
    if not root.exists():
        # Named, not a traceback: on camera this is the difference between "the
        # previous command did not run" and "something went wrong somewhere".
        print(f"tree.py: no such directory: {root}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"tree.py: not a directory: {root}", file=sys.stderr)
        return 2

    print("\n".join(render(root, args.depth, args.per_dir, args.max_lines)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
