# The story: a pile of email arrives, one command turns it into a filed tree
# and a sheet, and before any of that the dry run shows exactly what it will do
# and proves it wrote nothing.
# EDIT THIS FILE for a new piece that records a terminal.
#
#   make demo        (or: ./demo/record.sh)
#
# There is no `Output` line on purpose: demo/record.sh passes `vhs -o` so the
# clip lands in whichever output directory it was asked for.
#
# Five beats, in the order a nervous client asks for them:
#   1. what arrived       — a flat pile of .eml, nothing sorted
#   2. what it would do   — the dry run's tail: the plan, the counts, and the
#                           line saying filed/ does not exist, which the tool
#                           re-reads after planning rather than asserting.
#                           This is the beat that sells it.
#   3. the real run
#   4. the filed tree
#   5. the index sheet
#
# Beat 2 is piped through `tail` because the plan is one line per attachment
# and there are 36 of them. The tail is the right end to show: the exceptions
# sort last (report._plan_order), so what is on screen is the unsorted files
# with their reasons, the counts, and the proof.
#
# Beat 4 uses `--per-dir 0`, which shows folders with a count instead of
# filenames: seventeen lines rather than fifty-four, and the shape of the
# cabinet is what this beat is about. The filenames get beat 5 to themselves.
#
# Beat 5 uses `--tail` for the same reason the dry run does. The index is in
# mailbox order, so its head is thirty identical-looking invoice rows and its
# tail is every case the tool refused to guess about.
#
# Conventions that make a tape read well: set Height to the tallest *single*
# screen rather than the tallest total, clear between beats inside Hide blocks,
# hide the venv wiring, and sleep long enough after each Enter to read the
# output. The tallest screen here is beat 2: twenty lines of output plus a
# comment and a command. `tail -20` rather than -16 because the counts block
# and the by-rule table take fourteen lines on their own, and a tail that
# tight showed a lone `why:` continuation line with nothing above it — a
# fragment, not a plan.

Set Shell bash
Set FontSize 15
Set Width 1500
Set Height 500
Set Padding 20
Set TypingSpeed 12ms
Set Theme "Catppuccin Mocha"

Hide
Type "export PS1='$ ' PATH=$PWD/.venv/bin:$PATH" Enter
Type "rm -rf filed" Enter
Type "clear" Enter
Show

Type "# 33 emails, nothing sorted" Enter
Sleep 500ms
Type "ls fixtures/mailbox | head -7 && ls fixtures/mailbox | wc -l" Enter
Sleep 3s

Hide
Type "clear" Enter
Show

Type "# dry run: the plan, and proof it wrote nothing" Enter
Sleep 500ms
Type "python file_mail.py fixtures/mailbox --dry-run --quiet | tail -20" Enter
Sleep 5s

Hide
Type "clear" Enter
Show

Type "# now for real" Enter
Sleep 500ms
Type "python file_mail.py fixtures/mailbox --brief --quiet" Enter
Sleep 3s

Hide
Type "clear" Enter
Show

Type "# filed by year, month and rule" Enter
Sleep 500ms
Type "python demo/lib/tree.py filed --per-dir 0 --depth 5" Enter
Sleep 4s

Hide
Type "clear" Enter
Show

Type "# the index sheet: one row per attachment" Enter
Sleep 500ms
Type `python demo/lib/preview.py filed/index.csv original_filename new_path rule note --rows 3 --cell 42 --wrap note --tail` Enter
Sleep 4s
