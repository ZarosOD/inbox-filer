"""What the `make` targets are allowed to do to `filed/`.

The bug this exists to prevent, found on the piece before this one: a
`demo/setup.sh` that ended with `rm -rf out`, and a Makefile that makes `setup`
a prerequisite of every target. So `make run` wrote the output and `make test`
silently deleted it — while the README printed those two commands on adjacent
lines.

It matters more here than it did there. This tool's entire pitch is that it
does not touch a client's files without saying so, and a wrapper that wipes the
filing cabinet as a side effect of running the tests would be the same bug one
level up.

Nothing in the unit suite can see it, because the deletion happens in the
prerequisite, before pytest starts. These tests drive `make` itself in a copy of
the repo, which is the only level the bug is ever visible from.

The copy is what makes them safe: `--fresh` really does `rm -rf filed`, so
pointing them at the developer's own checkout would destroy the output they were
looking at. It symlinks `.venv` back to the real one rather than building its
own, which keeps each test well under a second and needs no network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
OUTPUT_FILES = ("index.csv", "index.xlsx")

# Everything the copy either cannot use or should not inherit: the venv is
# symlinked in afterwards, and filed/ has to start absent so its reappearance
# means `make run` created it.
SKIP = shutil.ignore_patterns(
    ".venv", ".git", "filed", "__pycache__", ".pytest_cache", "*.egg-info", ".toolchain"
)

pytestmark = [
    pytest.mark.skipif(shutil.which("make") is None, reason="these tests drive make"),
    pytest.mark.skipif(
        not (REPO / ".venv" / "bin" / "python").exists(),
        reason="no .venv to lend the copy (setup.sh builds one before pytest runs)",
    ),
]


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A throwaway copy of the repo with no filed/ and a borrowed venv."""
    root = tmp_path / "inbox-filer"
    shutil.copytree(REPO, root, ignore=SKIP, symlinks=True)
    (root / ".venv").symlink_to(REPO / ".venv")
    assert not (root / "filed").exists()
    return root


def make(checkout: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # pytest may itself have been started by `make test`; handing its jobserver
    # down to a nested make produces warnings and a shared job slot.
    env.pop("MAKEFLAGS", None)
    env.pop("MAKELEVEL", None)
    # `make test` in the copy would otherwise re-run this file, which would copy
    # the repo again, and so on. Collection still loads conftest and every test
    # module, and still runs the `setup` prerequisite — which is where the bug
    # lived — so the target is exercised where it matters.
    env["PYTEST_ADDOPTS"] = "--collect-only -q"
    return subprocess.run(["make", *args], cwd=checkout, capture_output=True, text=True, env=env)


def setup_sh(checkout: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["./demo/setup.sh", *args], cwd=checkout, capture_output=True, text=True
    )


def out_files(checkout: Path) -> set[str]:
    filed = checkout / "filed"
    return {p.relative_to(filed).as_posix() for p in filed.rglob("*") if p.is_file()} if filed.is_dir() else set()


def test_run_writes_the_output_files(checkout: Path) -> None:
    result = make(checkout, "run")

    assert result.returncode == 0, result.stderr
    assert out_files(checkout) >= set(OUTPUT_FILES)


@pytest.mark.parametrize("target", ["test", "plan", "fixtures"])
def test_other_targets_leave_the_output_alone(checkout: Path, target: str) -> None:
    assert make(checkout, "run").returncode == 0
    before = out_files(checkout)
    assert before >= set(OUTPUT_FILES)
    # A file nothing regenerates: if filed/ is removed and rebuilt rather than
    # left alone, the real files come back and this one does not.
    (checkout / "filed" / "sentinel.txt").write_text("mine", encoding="utf-8")

    result = make(checkout, target)

    assert result.returncode == 0, result.stdout + result.stderr
    assert out_files(checkout) >= before | {"sentinel.txt"}
    assert (checkout / "filed" / "sentinel.txt").read_text(encoding="utf-8") == "mine"


def test_make_plan_writes_nothing_at_all(checkout: Path) -> None:
    """`make plan` on a fresh checkout is the README's first suggestion, so it
    had better not create the thing it is previewing."""
    result = make(checkout, "plan")

    assert result.returncode == 0, result.stderr
    assert not (checkout / "filed").exists()
    assert "Nothing was written" in result.stdout


def test_setup_run_directly_leaves_the_output_alone(checkout: Path) -> None:
    """The second way the bug reproduced: no make involved at all."""
    assert make(checkout, "run").returncode == 0
    before = out_files(checkout)

    result = setup_sh(checkout)

    assert result.returncode == 0, result.stderr
    assert out_files(checkout) == before


def test_setup_fresh_removes_the_output(checkout: Path) -> None:
    """The recording path still gets its empty cabinet — record.sh passes --fresh."""
    assert make(checkout, "run").returncode == 0
    assert (checkout / "filed").is_dir()

    result = setup_sh(checkout, "--fresh")

    assert result.returncode == 0, result.stderr
    assert not (checkout / "filed").exists()


def test_setup_clears_its_own_scratch_either_way(checkout: Path) -> None:
    """demo/.scratch is the demo's workspace, not output, so it always goes."""
    scratch = checkout / "demo" / ".scratch"
    # exist_ok because `checkout` copies the working tree rather than exporting
    # HEAD, and demo/.scratch is gitignored — so whatever is in yours comes
    # along, invisible to `git status`. Without it this test asserted "setup.sh
    # wipes the scratch" by dying on mkdir the moment anything had already left
    # one there: a failure about the developer's machine wearing the name of a
    # failure about setup.sh.
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "leftover").write_text("x", encoding="utf-8")

    assert setup_sh(checkout).returncode == 0

    assert not scratch.exists()


def test_setup_rejects_an_unknown_argument(checkout: Path) -> None:
    """A typo'd flag must not read as "no flag" and quietly skip the wipe."""
    result = setup_sh(checkout, "--clean")

    assert result.returncode == 2
    assert "--fresh" in result.stderr


def test_record_sh_asks_setup_for_a_fresh_start() -> None:
    """The wiring the two setup.sh tests above cannot reach.

    Running record.sh for real means downloading vhs, ttyd, ffmpeg and a
    headless Chromium, which is `make demo`'s job and not a unit test's. What is
    checkable here is that the one caller entitled to the wipe still asks for
    it, so the recording does not quietly start on a half-filled cabinet.
    """
    line = next(
        line
        for line in (REPO / "demo" / "record.sh").read_text(encoding="utf-8").splitlines()
        if "setup.sh" in line and not line.lstrip().startswith("#")
    )

    assert line.strip() == '"$DEMO_DIR/setup.sh" --fresh'
