"""Turning what a message called a file into what it gets filed as.

Two jobs, and the difference between them is the whole point:

* `slugify` produces a predictable, boring token from arbitrary text. A client
  reading the rule file has to be able to predict the output, which rules out
  anything clever.
* `split_name` decides whether a declared filename is usable at all. When it
  is not, it says so instead of inventing something — the caller then files
  the attachment in unsorted/ with the reason attached, which is the failure
  discipline this tool is supposed to demonstrate.
"""

from __future__ import annotations

import mimetypes
import re
import unicodedata
from dataclasses import dataclass

#: Extensions we will take from a declared filename as-is. Anything longer or
#: stranger is treated as part of the stem, so `report.final.v2` does not get
#: filed with a `.v2` extension.
_EXTENSION = re.compile(r"\.([A-Za-z0-9]{1,8})$")

_NON_SLUG = re.compile(r"[^a-z0-9]+")

#: What a part gets called when the message declared no usable name. The
#: message slug plus the part number is stable across runs, which is what
#: keeps a re-run idempotent for these too.
FALLBACK_STEM = "{message}-part{index}"

#: Last resort when neither the filename nor the content type says anything.
DEFAULT_EXTENSION = ".bin"


class UnusableName(Exception):
    """The declared filename cannot be turned into one. Carries the reason."""


@dataclass(frozen=True)
class SplitName:
    stem: str
    """Slugified, never empty."""

    extension: str
    """Lowercase, with the dot, or "" when nothing declared one."""


def slugify(text: str) -> str:
    """Lowercase ASCII words joined by hyphens. Empty if there was nothing.

    Accents are folded rather than dropped (`Jürgen` -> `jurgen`) because a
    dropped letter makes two different senders collide, and a collision is the
    one thing the naming scheme is supposed to avoid making up.
    """
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return _NON_SLUG.sub("-", ascii_only.lower()).strip("-")


def basename(raw: str) -> str:
    """The filename a message declared, with any path it smuggled in removed.

    A `filename="../../.ssh/authorized_keys"` in a Content-Disposition header
    is either a broken mail client or somebody trying it on. Either way the
    only safe reading is "this message declared a name, not a location".
    """
    # Both separators, regardless of platform: the mail was not necessarily
    # written on the machine doing the filing.
    tail = re.split(r"[\\/]", raw)[-1]
    return tail.strip()


def split_name(raw_filename: str, content_type: str) -> SplitName:
    """Split a declared filename into a slugified stem and an extension.

    Raises `UnusableName` when there is no stem left to file under. The
    extension falls back to the content type, because "we know it is a PDF but
    not what to call it" is a different and more recoverable problem than "we
    know nothing".
    """
    name = basename(raw_filename)
    if not name:
        raise UnusableName("the message declared no filename for this attachment")

    match = _EXTENSION.search(name)
    if match:
        extension = "." + match.group(1).lower()
        stem_source = name[: match.start()]
    else:
        extension = extension_for_type(content_type)
        stem_source = name

    stem = slugify(stem_source)
    if not stem:
        raise UnusableName(
            f"the declared filename {name!r} has no letters or digits to file under"
        )
    return SplitName(stem=stem, extension=extension)


def extension_for_type(content_type: str) -> str:
    """`.pdf` for application/pdf, and `.bin` when even that is unknown."""
    guess = mimetypes.guess_extension(content_type.split(";")[0].strip().lower())
    if not guess:
        return DEFAULT_EXTENSION
    # mimetypes is entitled to its opinions; these two are not what an office
    # expects to see in a folder.
    return {".jpe": ".jpg", ".htm": ".html"}.get(guess, guess)


def fallback_name(message_id: str, source_name: str, part_index: int, content_type: str) -> SplitName:
    """A deterministic name for an attachment that declared no usable one.

    Keyed on the Message-ID when there is one and on the source filename when
    there is not, so two nameless attachments in one mailbox cannot become the
    same file, and the same one keeps its name on the next run.
    """
    key = slugify(message_id.strip("<>").partition("@")[0]) or slugify(source_name)
    return SplitName(
        stem=FALLBACK_STEM.format(message=key or "message", index=part_index),
        extension=extension_for_type(content_type),
    )
