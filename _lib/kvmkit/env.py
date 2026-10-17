"""Parsing for App env values (all strings, edited in single-line fields)."""

from __future__ import annotations


def number(env, name, default, minimum=None):
    """A float setting; invalid or empty values give `default`."""
    try:
        value = float((env.get(name) or "").strip() or default)
    except ValueError:
        value = float(default)
    return value if minimum is None else max(minimum, value)


def flag(env, name, default=False):
    """on/off style setting: empty means `default`; 0/off/no/false are off."""
    value = (env.get(name) or "").strip().lower()
    if not value:
        return default
    return value not in ("0", "off", "no", "false")


def sections(value, default_name=None):
    """Split `Name: a, b; Other: c` into [(name, [entry, ...]), ...].

    Sections are separated by `;` or newlines and entries by `,`. A section
    without a `Name:` prefix gets `default_name`. A prefix counts only when
    it holds no `=`, `/` or `.` and the colon is not followed by `/`, so
    `http://host` and `light.sofa=Sofa` are never mistaken for names.
    """
    result = []
    for chunk in (value or "").replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name = default_name
        colon = chunk.find(":")
        head = chunk[:colon]
        if colon > 0 and not any(c in head for c in "=/.") and chunk[colon + 1:colon + 2] != "/":
            name, chunk = head.strip(), chunk[colon + 1:]
        entries = [entry.strip() for entry in chunk.split(",") if entry.strip()]
        if entries:
            result.append((name, entries))
    return result


def pair(entry):
    """Split `left=right` once; returns (left, right) or (entry, None)."""
    left, separator, right = entry.partition("=")
    if not separator:
        return entry.strip(), None
    return left.strip(), right.strip()
