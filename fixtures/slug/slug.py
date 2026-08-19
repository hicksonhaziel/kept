import re

_PUNCTUATION = re.compile(r"[^\w\s-]")
_SPACES = re.compile(r"[\s_]+")


def slugify(title):
    cleaned = _PUNCTUATION.sub("", title.lower())
    hyphenated = _SPACES.sub("-", cleaned)
    return hyphenated.strip("-")
