"""Slugs, extensions, and the line between "awkward" and "unusable"."""

from __future__ import annotations

import pytest

from inbox_filer.naming import (
    UnusableName,
    basename,
    extension_for_type,
    fallback_name,
    slugify,
    split_name,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Invoice 10482", "invoice-10482"),
        ("  Spaces  Everywhere  ", "spaces-everywhere"),
        ("UPPER_case-mixed", "upper-case-mixed"),
        ("Rechnung März", "rechnung-marz"),
        ("Jürgen", "jurgen"),
        ("...", ""),
        ("…", ""),
        ("", ""),
        ("a---b", "a-b"),
        ("-leading-and-trailing-", "leading-and-trailing"),
    ],
)
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_slugify_folds_accents_rather_than_dropping_letters():
    """Dropping the accented letter makes two different names collide, and a
    collision is the thing the naming scheme exists to avoid inventing."""
    assert slugify("Müller") != slugify("Mller")
    assert slugify("Müller") == "muller"


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("invoice.pdf", "invoice.pdf"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\Windows\\notes.txt", "notes.txt"),
        ("/absolute/path/report.pdf", "report.pdf"),
        ("  padded.pdf  ", "padded.pdf"),
    ],
)
def test_basename_keeps_only_the_last_component(declared, expected):
    assert basename(declared) == expected


def test_split_name_takes_the_extension_and_slugs_the_rest():
    split = split_name("Invoice 10482 (final).PDF", "application/pdf")

    assert split.stem == "invoice-10482-final"
    assert split.extension == ".pdf"


def test_the_extension_is_the_last_short_dotted_run():
    """`report.final.v2` files as a `.v2`, the same answer every other tool
    gives. Predictable beats clever: a whitelist of "real" extensions is a
    list a client cannot check, and this rule fits in one sentence."""
    split = split_name("report.final.v2", "application/octet-stream")

    assert split.stem == "report-final"
    assert split.extension == ".v2"


def test_a_long_dotted_suffix_is_not_an_extension():
    """Eight characters is the cutoff, so a sentence ending in a full stop
    does not turn into a file type."""
    split = split_name("report.finalversion", "application/octet-stream")

    assert split.stem == "report-finalversion"
    assert split.extension == ".bin"


def test_split_name_falls_back_to_the_content_type():
    split = split_name("scan", "application/pdf")

    assert split == split_name("scan", "application/pdf")
    assert split.extension == ".pdf"


def test_split_name_rejects_a_declaration_of_nothing():
    with pytest.raises(UnusableName, match="declared no filename"):
        split_name("", "application/pdf")


def test_split_name_rejects_a_name_with_nothing_to_file_under():
    with pytest.raises(UnusableName, match="no letters or digits"):
        split_name("….pdf", "application/pdf")


def test_a_traversing_name_is_neutralised_not_rejected():
    """It is still a perfectly good filename once the path is thrown away."""
    split = split_name("../../../etc/passwd-notes.txt", "text/plain")

    assert split.stem == "passwd-notes"
    assert split.extension == ".txt"


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("application/pdf", ".pdf"),
        ("image/png", ".png"),
        ("image/jpeg", ".jpg"),
        ("text/plain; charset=utf-8", ".txt"),
        ("text/html", ".html"),
        ("application/x-nonsense", ".bin"),
    ],
)
def test_extension_for_type(content_type, expected):
    assert extension_for_type(content_type) == expected


def test_fallback_names_are_stable_and_distinct():
    first = fallback_name("<fixture-025@x.example>", "025.eml", 1, "application/pdf")
    again = fallback_name("<fixture-025@x.example>", "025.eml", 1, "application/pdf")
    second_part = fallback_name("<fixture-025@x.example>", "025.eml", 2, "application/pdf")
    other = fallback_name("<fixture-026@x.example>", "026.eml", 1, "application/pdf")

    assert first == again, "a re-run must produce the same name or nothing is idempotent"
    assert first != second_part
    assert first != other
    assert first.stem == "fixture-025-part1"


def test_fallback_falls_back_to_the_source_filename_when_there_is_no_message_id():
    split = fallback_name("", "042-strange.eml", 1, "image/png")

    assert split.stem == "042-strange-eml-part1"
    assert split.extension == ".png"
