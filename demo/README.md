# demo/ — the recording pipeline

One command regenerates a clip from scratch, headless, from a clean checkout:

```bash
./demo/record.sh              # this piece: VHS, a terminal session
./demo/record.sh --clean      # throw the toolchain away and re-fetch it first
```

No screen capture, no window manager, no display server, no root. Everything
the recording needs is fetched into `demo/.toolchain/` and nothing is installed
system-wide. `record.sh` fails loudly if the clip is missing, empty, or longer
than 35 seconds.

This is the **fourth** piece to use this pipeline. It wrote the three files a
piece is supposed to write — `recipe`, `setup.sh`, `demo.tape` — and it added
two things to the shared half. Neither was forked into this piece: the rule is
that editing `lib/` to make your own piece work means the split is wrong, so
you fix the split and say so.

- **`lib/tree.py` is new.** This piece's fourth beat is the shape of the filing
  cabinet, and there is no `tree` binary on a stock box. `find | sort` wraps at
  GIF width, which is the same unreadable-at-thumbnail-size problem
  `lib/preview.py` exists to solve, one directory over. Nothing about printing a
  directory tree is specific to filing email, so it went into `lib/` with
  `tests/test_demo_tree.py` beside it.
- **`lib/preview.py` gained `--tail`.** Documented under *Writing a tape* below.
  Every report this pipeline has filmed so far has a boring head and an
  interesting tail, so this is a shared-half gap rather than a quirk of this
  piece.

`lib/fetch.sh`, `lib/python-venv.sh`, `lib/playwright.sh`,
`lib/chromium-libs.sh` and `record.sh` are byte-identical to the previous
piece's copies, including the `setup.sh --fresh` call it introduced.

The history explains why the files are shaped the way they are:

- **Piece #1** (`pdf-to-csv`) had one recipe, VHS, wired straight into the
  orchestrator.
- **Piece #2** (`catalog-watch`) added the browser recipe, so the orchestrator
  now **picks** a recipe instead of being one. Two things moved *into* `lib/` at
  the same time, because they were about to be copy-pasted into a third piece:
  the venv/uv/ensurepip ladder (`lib/python-venv.sh`) and the CSV table renderer
  (`lib/preview.py`).
- **Piece #3** (`feed-clean`) added the download retry helper (`lib/fetch.sh`),
  `--wrap` on the table renderer, and moved the output wipe behind
  `setup.sh --fresh` after shipping a `setup.sh` that deleted `out/` on every
  `make` target.
- **Piece #4** — this one — needed a directory tree and the end of a long
  report, and got both by adding to `lib/` rather than writing them here. That
  is the split working: the pressure lands on the shared half, which is where it
  belongs. `tests/test_make_targets.py` in the repo root holds the `--fresh`
  line inherited from piece #3.

## Which recipe

| | **VHS** (`lib/vhs.sh`) | **Playwright** (`lib/playwright.sh`) |
| --- | --- | --- |
| Records | A terminal session | A real browser page |
| You write | `demo.tape` — a script of keystrokes and pauses | `scene.py` — Playwright code |
| Good at | Crisp text at small sizes; small files (this repo: 439 KB) | Anything with a UI, a page, or a before/after to point at |
| Bad at | Anything that is not text in a terminal | Files are several times bigger |
| Timing | Declarative `Sleep 4s` | `page.wait_for_timeout(4000)` — same idea, in Python |
| Output | GIF **and** MP4, from one recording | GIF **and** MP4, from one recording |

Both recipes write both formats because the two are for different places. The
**GIF** is the README thumbnail: it animates inline on GitHub and needs no
player. The **MP4** is the portfolio cover, because Upwork's gallery renders an
uploaded GIF as a single static first frame — a GIF there is a screenshot with
extra bytes. Neither is generated from the other; they are two encodes of the
same captured frames, so they cannot drift apart.

**Pick VHS when the deliverable is a command.** This piece qualifies: what the
client cares about is a plan, a tree of filed attachments and an index sheet,
all of which are text, and VHS renders text natively rather than photographing
it. Both recipes are live in the repo so the next piece can choose rather than
reinvent — this one simply has no `scene.py`, which is why `demo/recipe` says
`vhs`.

## Copying this into another piece

Copy the whole `demo/` folder. Then change **these files and nothing else**:

| File | What to change |
| --- | --- |
| `recipe` | One word: `playwright` or `vhs`. |
| `setup.sh` | Two lines in practice: the import names you pass `ensure_venv`, and whatever the piece needs regenerated before recording. A non-Python piece replaces the `ensure_venv` call with its own build. Anything it deletes belongs under `--fresh` unless the piece itself owns it — every `make` target runs this file, so a wipe outside that flag is a wipe of the user's work. |
| `demo.tape` | The VHS recipe's tape. Delete it if you chose Playwright. |
| `scene.py` | The Playwright recipe's script. Not present in this piece; copy it from `catalog-watch` if you want the browser recipe. |

Leave `record.sh` and everything in `lib/` alone. If you find yourself editing
one of those to make your piece work, the split is wrong — fix the split, do
not fork the file.

## Adding a recipe

A recipe is `demo/lib/<name>.sh` defining exactly two functions:

```bash
recipe_bootstrap          # fetch what it needs: no root, inside the repo
recipe_record OUT_DIR     # leave a clip in OUT_DIR; set RECIPE_CLIP to it
```

`record.sh` handles the rest: reading `demo/recipe`, running `setup.sh --fresh`,
wiping the clip directory it is about to write, and checking the clip exists, is
non-empty and is inside the time budget. `DEMO_RECIPE=<name> ./demo/record.sh`
overrides the choice for one run; `DEMO_OUT_DIR=...` sends the clip somewhere
else.

## Writing a tape (VHS)

`demo.tape` is [VHS tape syntax](https://github.com/charmbracelet/vhs#vhs-command-reference).
Five beats here, in the order a nervous client asks for them: what arrived, what
the tool *would* do, the real run, the filed tree, the index sheet.

- **Set the height to fit the tallest *single* screen, not the tallest total.**
  Use `Hide` / `Type "clear"` / `Enter` / `Show` between beats. The tallest
  screen here is the dry run — twenty lines of output plus a comment and a
  command — so `Height 500`. A short frame is far more readable in a proposal
  thumbnail than a tall one full of dead space.
- **Set the width so the longest command does not wrap.** A wrapped command line
  costs a row of the frame and reads as a mistake. `Width 1500` here, because
  the index-sheet beat names four columns and three options.
- **Hide the setup.** Activating a venv or exporting variables goes in a `Hide`
  block so it never appears in the clip.
- **`Sleep` after each `Enter`**, long enough to read the output. 3 to 4 seconds
  is about right for a table; 5 for the dry run, which is the beat that sells
  the piece.
- **No `Output` line.** `record.sh` passes `vhs -o` so the clip goes where it
  was asked to go.
- **Show a directory as a tree, not as `find` output: `lib/tree.py`.** A flat
  `find | sort` wraps at GIF width, and a wrapped path is unreadable. The
  helper draws the tree and can cap it three ways — depth, files per directory,
  and total lines:

  ```bash
  python demo/lib/tree.py filed --per-dir 0 --depth 5
  ```

  **`--per-dir 0` is the option that matters**: it prints folders with a file
  count on each line and no filenames at all, which takes this repo's output
  from fifty-four lines to seventeen. That is the right trade for this beat,
  because the beat is about the *shape* of the cabinet — year, month, rule —
  and the filenames get a beat of their own straight afterwards. Tested in
  `tests/test_demo_tree.py`.
- **Show a CSV with `lib/preview.py`, not `cat`.** Raw CSV wraps, and a wrapped
  line is unreadable at GIF sizes. The helper picks columns, caps rows,
  truncates cells with `…` and right-aligns numeric columns. Naming a column the
  file does not have is an error listing the ones it does, rather than a blank
  column that looks fine on camera. Tested in `tests/test_demo_preview.py`.
- **Show the *end* of a report, not the start: `--tail`.** The index is in
  mailbox order, so its head is thirty near-identical invoice rows and its tail
  is every case the tool refused to guess about. `--tail` shows the last N
  records and says `... after 34 earlier rows (37 total)`, so a capped table
  still cannot pass itself off as the whole file:

  ```bash
  python demo/lib/preview.py filed/index.csv original_filename new_path rule note \
      --rows 3 --cell 42 --wrap note --tail
  ```

  The same reasoning drives beat 2 through `tail -20`: the plan is one line per
  attachment and there are 36 of them, and `report._plan_order` sorts the
  exceptions last precisely so that the tail is the part worth filming. That is
  a property of the tool, not of the tape — a report whose interesting end is in
  the middle needs fixing in the report, not cropping in the recording.
- **`--wrap COL` for a prose column.** `note` is a sentence, not a field, and a
  fixed-width cell cuts it exactly where it stops being boilerplate and starts
  being the explanation. The wrapped column takes as many lines as it needs at
  `--cell` width, the other columns stay blank on the continuation lines, and
  `--rows` still counts *records* rather than screen lines. Budget roughly three
  screen lines per record when you set `Height`.
- **Check the frames, not just the duration.** `tail -16` on an early cut of
  beat 2 left a lone `why:` continuation line with nothing above it — a
  fragment that reads as a rendering bug, invisible in the duration check and
  in the tests. `tail -20` fixed it. Extract a few frames with `ffmpeg` and look
  at every beat before calling a clip done.
- **Synthetic data only.** Every sender in the clip is under `.example`, which
  RFC 2606 reserves and which can never be a live domain. Every message,
  attachment and filename is generated. Check every frame before shipping.

## Toolchain

Everything lands in `demo/.toolchain/` (gitignored). Nothing system-wide, no
root, versions pinned except where noted.

| File | Fetches | Pin | Why pinned |
| --- | --- | --- | --- |
| `lib/fetch.sh` | nothing itself | — | Every download below goes through it: a few attempts, a widening gap, and a message that separates "the host is having a moment" from "the URL is wrong". Failure is fatal for vhs (no recording without it) and a fallback for uv (there is still `python3 -m venv`). |
| `lib/uv.sh` | uv | 0.12.13 | Checksum-verified against the published `.sha256`. |
| `lib/python-venv.sh` | nothing directly | — | The venv ladder. Calls `lib/uv.sh` when the machine has no uv. |
| `lib/ffmpeg.sh` | ffmpeg, ffprobe | **current release, not pinned** | The static build publishes one URL for the newest version; there is no per-version URL to pin to. A system `ffmpeg` is used if present. |
| `lib/vhs.sh` | vhs, ttyd | 0.10.0, 1.7.7 | **vhs deliberately**: 0.12.x starts Chromium, captures every frame, then exits 0 having written no file at all on some Linux hosts. 0.10.0 encodes reliably. |
| `lib/playwright.sh` | the `playwright` wheel + Chromium | 1.47.0 | Unused by this piece; kept so the next one can choose it. |
| `lib/chromium-libs.sh` | the shared objects Chromium links against | — | See below. |

`lib/preview.py` and `lib/tree.py` fetch nothing — they are the two display
helpers, and they have tests in the repo root rather than a pin.

`lib/uv.sh` applies the pinning rule to the *project's* toolchain, because a
clean checkout is not a clean machine. Stock Ubuntu 24.04 has no `uv` and a
`python3` with no `ensurepip` (that lives in the separate `python3-venv`
package), so `setup.sh` would stop dead there and take `make test`, `make run`
and `make demo` with it. It fetches a pinned uv into `demo/.toolchain/bin`, and
uv then supplies the interpreter too, so the machine does not need a Python
3.12 of its own.

VHS drives a headless Chromium that it downloads itself into `~/.cache/rod`,
and on a server image that browser is missing the desktop libraries it links
against. `playwright install-deps` and `apt-get install` both want root, which
a demo script has no business asking for. So `lib/chromium-libs.sh` runs `ldd`,
works out exactly which `.so` files are missing, fetches those `.deb`s with
`apt-get download` (no root) and unpacks them into `demo/.toolchain/sysroot`.
It loops up to three times, because unpacking one library reveals the next one
down. On a non-Debian host it prints the library names and stops rather than
guessing.

## Known limits

- **x86_64 Linux.** The pinned ttyd and ffmpeg URLs are architecture-specific.
  macOS would need `brew install vhs ttyd ffmpeg` and a small edit.
- **The first run downloads a browser**, because that is how VHS renders a
  terminal. Measured numbers from a dead clone with an empty `HOME` and
  `PATH=/usr/bin:/bin` are in the top-level README.
