from __future__ import annotations

import json
from pathlib import Path

import pytest

from inbox_filer.mailbox import read_mailbox
from inbox_filer.models import Message
from inbox_filer.rules import RuleSet, load_rules

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO


@pytest.fixture(scope="session")
def mailbox_path() -> Path:
    return REPO / "fixtures" / "mailbox"


@pytest.fixture(scope="session")
def rules() -> RuleSet:
    return load_rules(REPO / "rules" / "office.json")


@pytest.fixture(scope="session")
def expected() -> dict:
    """The ground truth fixtures/generate_mailbox.py wrote alongside the mailbox."""
    return json.loads((REPO / "tests" / "expected.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def messages(mailbox_path: Path) -> list[Message]:
    return read_mailbox(mailbox_path)


@pytest.fixture(scope="session")
def by_file(messages: list[Message]) -> dict[str, Message]:
    """Messages keyed by their fixture filename, which is how the ground truth
    and the tests below refer to the interesting ones."""
    return {message.source.name: message for message in messages}
