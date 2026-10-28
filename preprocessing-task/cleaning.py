"""Pure text-cleaning functions (no database). Each one is easy to test."""
import hashlib
import re
import unicodedata

import ftfy

# Invisible characters that only break matching and counting
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿\x00"), None)

# Typical "mojibake": UTF-8 text that was read with the wrong encoding.
# Examples: "Ã©", "â€™", "Â ", or the replacement character.
MOJIBAKE_RE = re.compile(
    "Ã[\u0080-¿‘-›ŒœŠšŸŽž"
    "ƒˆ˜]|â€|Â[ -¿]|�")


# A lone "Â" before a space or line break is a broken non-breaking space.
_STRAY_A_RE = re.compile("Â(?=[\\s\u00a0]|$)")


def fix_encoding(value):
    """Repair text that was decoded with the wrong encoding.

    Only texts that show a typical wrong-encoding pattern are touched, so normal text is
    never changed. Returns (text, changed). A replacement character (U+FFFD) means the
    original text is already lost; it cannot be repaired and stays flagged.
    """
    if not value or not MOJIBAKE_RE.search(value):
        return value, False
    fixed = ftfy.fix_encoding(value)
    fixed = _STRAY_A_RE.sub("", fixed)
    return fixed, fixed != value


def _base(value):
    value = unicodedata.normalize("NFC", value)
    value = value.translate(_INVISIBLE)
    return value.replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n")


def clean_line(value):
    """For one-line fields (title, author, source...): one clean line of text."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", _base(value)).strip()


def clean_body(value):
    """For article text: tidy spaces but KEEP the paragraph breaks (one per line)."""
    if value is None:
        return None
    lines = (re.sub(r"[ \t\f\v]+", " ", line).strip() for line in _base(value).split("\n"))
    return "\n".join(line for line in lines if line)


def body_fingerprint(text):
    """MD5 of the text in lower case with all whitespace collapsed (duplicate detection)."""
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text.casefold()).strip()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def has_suspicious_encoding(*texts):
    """True if any text contains typical wrong-encoding patterns."""
    return any(t and MOJIBAKE_RE.search(t) for t in texts)


def count_words(text):
    return len(text.split()) if text else 0
