PY := .venv/bin/python
MAILBOX := fixtures/mailbox

.PHONY: help setup run plan test fixtures demo clean

help:
	@echo "make plan      dry run: print the whole plan, write nothing"
	@echo "make run       file the bundled fixture mailbox and print the summary"
	@echo "make test      run the test suite"
	@echo "make fixtures  regenerate the synthetic mailbox and its ground truth"
	@echo "make demo      regenerate demo/out/demo.gif with VHS, headless"
	@echo "make clean     remove filed/, the demo toolchain and the caches"

setup:
	@./demo/setup.sh

# The flag that sells it: everything the real run would do, printed, followed
# by a re-read of the output directory to show it is untouched.
plan: setup
	@$(PY) file_mail.py $(MAILBOX) --dry-run --quiet

# The headline: a flat pile of email in, a filed tree and an index sheet out.
run: setup
	@$(PY) file_mail.py $(MAILBOX) --report --quiet

test: setup
	@$(PY) -m pytest -q

fixtures: setup
	@$(PY) fixtures/generate_mailbox.py

demo:
	@./demo/record.sh

clean:
	rm -rf filed demo/out demo/.toolchain demo/.scratch .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
