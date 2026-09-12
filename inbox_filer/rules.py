"""The rule file: loading it, checking it, and matching against it.

The promise this module has to keep is in the README's first paragraph — a
client can open `rules/office.json`, read it, and predict where a given email
will end up. That rules out anything the rule file cannot express, and it puts
the weight on validation: every mistake it is possible to make in the file has
to be reported at load time, naming the rule, rather than discovered on
message 400 of a run.

There is no catch-all rule and there is no fuzzy fallback. A message that
matches nothing goes to unsorted/ and says so.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Attachment, Message

#: Conditions a rule may test. Closed on purpose: a typo'd condition name is a
#: rule that silently matches everything or nothing, which is precisely the
#: class of surprise this file exists to prevent.
CONDITIONS = (
    "sender_is",
    "sender_domain",
    "sender_matches",
    "subject_matches",
    "filename_matches",
    "extension_is",
)

TOP_LEVEL = ("name", "description", "path_template", "filename_template", "unsorted_folder", "rules")
RULE_KEYS = ("name", "folder", "when", "description")

PATH_PLACEHOLDERS = ("year", "month", "folder", "filename")
FILENAME_PLACEHOLDERS = ("date", "slug", "ext", "sender_slug", "sender_domain", "rule")
FOLDER_PLACEHOLDERS = ("sender_slug", "sender_domain", "sender_local", "rule")

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


class RuleError(Exception):
    """The rule file is wrong. The message says which rule and how."""


@dataclass(frozen=True)
class Rule:
    name: str
    folder: str
    description: str
    conditions: dict[str, Any]

    def matches(self, message: Message, attachment: Attachment) -> bool:
        """Every condition has to hold. An empty `when` is rejected at load."""
        return all(
            _CHECKS[key](value, message, attachment) for key, value in self.conditions.items()
        )


@dataclass(frozen=True)
class RuleSet:
    name: str
    description: str
    path_template: str
    filename_template: str
    unsorted_folder: str
    rules: tuple[Rule, ...]
    source: Path

    def match(self, message: Message, attachment: Attachment) -> Rule | None:
        """First rule that matches wins. Order in the file is the priority."""
        for rule in self.rules:
            if rule.matches(message, attachment):
                return rule
        return None


# --- conditions -------------------------------------------------------------
#
# Each takes (configured value, message, attachment). Kept as one-liners so the
# README can state exactly what each condition does without hedging.


def _sender_is(value: str, message: Message, _: Attachment) -> bool:
    return message.sender_email == value.lower()


def _sender_domain(value: str, message: Message, _: Attachment) -> bool:
    return message.sender_domain == value.lower()


def _sender_matches(value: re.Pattern[str], message: Message, _: Attachment) -> bool:
    return bool(value.search(message.sender_email))


def _subject_matches(value: re.Pattern[str], message: Message, _: Attachment) -> bool:
    return bool(value.search(message.subject))


def _filename_matches(value: re.Pattern[str], _: Message, attachment: Attachment) -> bool:
    return bool(value.search(attachment.raw_filename))


def _extension_is(value: tuple[str, ...], _: Message, attachment: Attachment) -> bool:
    name = attachment.raw_filename.lower()
    return any(name.endswith(extension) for extension in value)


_CHECKS = {
    "sender_is": _sender_is,
    "sender_domain": _sender_domain,
    "sender_matches": _sender_matches,
    "subject_matches": _subject_matches,
    "filename_matches": _filename_matches,
    "extension_is": _extension_is,
}


# --- loading ----------------------------------------------------------------


def load_rules(path: str | Path) -> RuleSet:
    """Read and fully validate a rule file.

    Everything that can be wrong is wrong *here*, with the rule named. The
    alternative — a regex that only fails to compile when a message happens to
    reach it — turns a typo into a partial run, and a partial run into a half
    filed cabinet.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuleError(f"no such rule file: {path}") from exc
    except OSError as exc:  # pragma: no cover - depends on the filesystem
        raise RuleError(f"cannot read {path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuleError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuleError(f"{path} should hold an object, not a {type(data).__name__}")

    _reject_unknown(data, TOP_LEVEL, f"{path}: top level")

    path_template = _template(
        data.get("path_template", "{year}/{month}/{folder}/{filename}"),
        PATH_PLACEHOLDERS,
        "path_template",
    )
    for required in ("{folder}", "{filename}"):
        if required not in path_template:
            raise RuleError(f"path_template must contain {required}: {path_template!r}")

    filename_template = _template(
        data.get("filename_template", "{date}-{slug}{ext}"),
        FILENAME_PLACEHOLDERS,
        "filename_template",
    )
    if "{slug}" not in filename_template:
        raise RuleError(
            "filename_template must contain {slug}, or two different attachments "
            f"would always claim the same name: {filename_template!r}"
        )

    unsorted_folder = str(data.get("unsorted_folder", "unsorted"))
    _reject_traversal(unsorted_folder, "unsorted_folder")

    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise RuleError(f"{path}: `rules` should be a non-empty list")

    rules: list[Rule] = []
    seen: set[str] = set()
    for position, raw in enumerate(raw_rules, start=1):
        rule = _rule(raw, position)
        if rule.name in seen:
            raise RuleError(
                f"rule {position} reuses the name {rule.name!r}; names appear in the "
                "index sheet, so two rules cannot share one"
            )
        seen.add(rule.name)
        rules.append(rule)

    return RuleSet(
        name=str(data.get("name", path.stem)),
        description=str(data.get("description", "")),
        path_template=path_template,
        filename_template=filename_template,
        unsorted_folder=unsorted_folder,
        rules=tuple(rules),
        source=path,
    )


def _rule(raw: Any, position: int) -> Rule:
    where = f"rule {position}"
    if not isinstance(raw, dict):
        raise RuleError(f"{where} should be an object, not a {type(raw).__name__}")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RuleError(f"{where} has no `name`")
    where = f"rule {position} ({name})"

    _reject_unknown(raw, RULE_KEYS, where)

    folder = raw.get("folder")
    if not isinstance(folder, str) or not folder.strip():
        raise RuleError(f"{where} has no `folder`")
    folder = _template(folder, FOLDER_PLACEHOLDERS, f"{where}: folder")
    _reject_traversal(folder, f"{where}: folder")

    when = raw.get("when")
    if not isinstance(when, dict) or not when:
        raise RuleError(
            f"{where} has no `when` conditions; a rule that tests nothing would "
            "match every attachment and shadow everything below it"
        )
    _reject_unknown(when, CONDITIONS, f"{where}: when")

    conditions: dict[str, Any] = {}
    for key, value in when.items():
        conditions[key] = _condition(key, value, where)

    return Rule(
        name=name.strip(),
        folder=folder,
        description=str(raw.get("description", "")),
        conditions=conditions,
    )


def _condition(key: str, value: Any, where: str) -> Any:
    if key.endswith("_matches"):
        if not isinstance(value, str):
            raise RuleError(f"{where}: {key} should be a regex string")
        try:
            return re.compile(value)
        except re.error as exc:
            raise RuleError(f"{where}: {key} is not a valid regex ({exc}): {value!r}") from exc
    if key == "extension_is":
        if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
            raise RuleError(f"{where}: extension_is should be a non-empty list of strings")
        cleaned = []
        for extension in value:
            extension = extension.lower().strip()
            if not extension.startswith("."):
                raise RuleError(
                    f"{where}: extension {extension!r} should start with a dot, so that "
                    "`.doc` cannot quietly match `report.mydoc`"
                )
            cleaned.append(extension)
        return tuple(cleaned)
    if not isinstance(value, str) or not value.strip():
        raise RuleError(f"{where}: {key} should be a non-empty string")
    return value.strip()


def _reject_unknown(data: dict, allowed: tuple[str, ...], where: str) -> None:
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise RuleError(
            f"{where}: unknown key{'s' if len(unknown) > 1 else ''} "
            f"{', '.join(repr(k) for k in unknown)}. Known: {', '.join(allowed)}"
        )


def _template(value: Any, allowed: tuple[str, ...], where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuleError(f"{where} should be a non-empty string")
    unknown = sorted({name for name in _PLACEHOLDER.findall(value)} - set(allowed))
    if unknown:
        raise RuleError(
            f"{where}: unknown placeholder{'s' if len(unknown) > 1 else ''} "
            f"{', '.join('{' + k + '}' for k in unknown)}. "
            f"Known: {', '.join('{' + k + '}' for k in allowed)}"
        )
    return value.strip()


def _reject_traversal(value: str, where: str) -> None:
    parts = [p for p in value.replace("\\", "/").split("/") if p]
    if any(part == ".." for part in parts) or value.startswith("/"):
        raise RuleError(
            f"{where}: {value!r} points outside the output directory. Folders are "
            "relative to --out and stay there."
        )
