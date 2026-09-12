"""The rule file: what it accepts, what it refuses, and in what order.

The refusals matter as much as the matches. The pitch is that a client can read
`rules/office.json` and predict the outcome, and that only holds if a rule file
that cannot be predicted from is rejected at load time rather than half-applied
at run time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inbox_filer.models import Attachment, Message
from inbox_filer.rules import RuleError, load_rules


def write_rules(tmp_path: Path, data: dict, name: str = "r.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def minimal(**overrides) -> dict:
    data = {
        "name": "test",
        "rules": [{"name": "pdfs", "folder": "pdfs", "when": {"extension_is": [".pdf"]}}],
    }
    data.update(overrides)
    return data


def message(sender="a@b.example", subject="hello", date=None) -> Message:
    return Message(
        source=Path("x.eml"),
        message_id="<x@b.example>",
        subject=subject,
        sender_name="",
        sender_email=sender,
        date=date,
        raw_date="",
    )


def attachment(filename="a.pdf", content_type="application/pdf") -> Attachment:
    return Attachment(1, filename, content_type, b"x")


# --- the shipped rule file --------------------------------------------------


def test_the_shipped_rules_load(rules):
    assert rules.rules
    assert rules.unsorted_folder == "unsorted"


def test_every_shipped_rule_explains_itself(rules):
    """A rule file is documentation as much as configuration."""
    for rule in rules.rules:
        assert rule.description, rule.name


def test_first_match_wins_and_the_order_is_the_file_order(rules):
    """An invoice from the bank is an invoice: `invoices` sits above
    `bank-statements`, and this is the test that keeps it there."""
    bank_invoice = message(sender="statements@northbank.example", subject="Invoice 4471 — fees")
    bank_other = message(sender="statements@northbank.example", subject="Your statement is ready")

    assert rules.match(bank_invoice, attachment()).name == "invoices"
    assert rules.match(bank_other, attachment()).name == "bank-statements"


def test_a_supplier_invoice_still_files_as_an_invoice(rules):
    """The catch-for-one-sender rule is last, so it cannot swallow them."""
    supplier = message(sender="accounts@northgate-supplies.example", subject="Invoice 10042")

    assert rules.match(supplier, attachment()).name == "invoices"


def test_nothing_matches_everything(rules):
    """There is no catch-all. Something has to be able to reach unsorted/, or
    the failure discipline the README describes never fires."""
    stranger = message(sender="someone@unknown.example", subject="Lunch on Thursday?")

    assert rules.match(stranger, attachment("menu.csv", "text/csv")) is None


def test_the_filename_rule_reads_the_attachment_not_the_subject(rules):
    covering_email = message(sender="jo@bellweather-signs.example", subject="As discussed")

    matched = rules.match(covering_email, attachment("Bellweather-NDA-signed.pdf"))

    assert matched.name == "contracts"


# --- validation -------------------------------------------------------------


def test_a_missing_file_says_which(tmp_path):
    with pytest.raises(RuleError, match="no such rule file"):
        load_rules(tmp_path / "absent.json")


def test_broken_json_says_so(tmp_path):
    path = tmp_path / "r.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(RuleError, match="not valid JSON"):
        load_rules(path)


def test_an_unknown_top_level_key_is_refused_and_the_known_ones_listed(tmp_path):
    path = write_rules(tmp_path, minimal(unsorted_dir="elsewhere"))

    with pytest.raises(RuleError, match="unsorted_folder"):
        load_rules(path)


def test_an_unknown_condition_is_refused(tmp_path):
    """The dangerous typo: a condition nobody checks is a rule that matches
    everything the other conditions allow."""
    path = write_rules(
        tmp_path,
        minimal(rules=[{"name": "x", "folder": "x", "when": {"sender_contains": "bank"}}]),
    )

    with pytest.raises(RuleError, match="sender_contains"):
        load_rules(path)


def test_a_rule_with_no_conditions_is_refused(tmp_path):
    path = write_rules(tmp_path, minimal(rules=[{"name": "x", "folder": "x", "when": {}}]))

    with pytest.raises(RuleError, match="shadow everything below it"):
        load_rules(path)


def test_a_bad_regex_is_refused_at_load_time(tmp_path):
    path = write_rules(
        tmp_path,
        minimal(rules=[{"name": "x", "folder": "x", "when": {"subject_matches": "([unclosed"}}]),
    )

    with pytest.raises(RuleError, match="not a valid regex"):
        load_rules(path)


def test_an_extension_without_a_dot_is_refused(tmp_path):
    path = write_rules(
        tmp_path, minimal(rules=[{"name": "x", "folder": "x", "when": {"extension_is": ["doc"]}}])
    )

    with pytest.raises(RuleError, match="should start with a dot"):
        load_rules(path)


def test_duplicate_rule_names_are_refused(tmp_path):
    rule = {"name": "x", "folder": "x", "when": {"extension_is": [".pdf"]}}
    path = write_rules(tmp_path, minimal(rules=[rule, dict(rule, folder="y")]))

    with pytest.raises(RuleError, match="reuses the name"):
        load_rules(path)


@pytest.mark.parametrize("folder", ["../escape", "/etc", "a/../../b"])
def test_a_folder_that_leaves_the_output_directory_is_refused(tmp_path, folder):
    path = write_rules(
        tmp_path, minimal(rules=[{"name": "x", "folder": folder, "when": {"extension_is": [".pdf"]}}])
    )

    with pytest.raises(RuleError, match="points outside"):
        load_rules(path)


def test_an_unknown_placeholder_is_refused_and_the_real_ones_named(tmp_path):
    path = write_rules(tmp_path, minimal(filename_template="{date}-{slug}-{sender}{ext}"))

    with pytest.raises(RuleError) as caught:
        load_rules(path)

    assert "{sender}" in str(caught.value)
    assert "{sender_slug}" in str(caught.value)


def test_a_filename_template_without_a_slug_is_refused(tmp_path):
    """Without it every attachment from one sender on one day is a collision,
    and the tool would spend its life appending suffixes."""
    path = write_rules(tmp_path, minimal(filename_template="{date}{ext}"))

    with pytest.raises(RuleError, match=r"must contain \{slug\}"):
        load_rules(path)


def test_a_path_template_without_a_filename_is_refused(tmp_path):
    path = write_rules(tmp_path, minimal(path_template="{year}/{month}/{folder}"))

    with pytest.raises(RuleError, match=r"must contain \{filename\}"):
        load_rules(path)


def test_an_empty_rule_list_is_refused(tmp_path):
    path = write_rules(tmp_path, minimal(rules=[]))

    with pytest.raises(RuleError, match="non-empty list"):
        load_rules(path)
