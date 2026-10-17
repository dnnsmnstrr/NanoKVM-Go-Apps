"""Read Dashy `conf.yml` files without PyYAML (it is not on the device).

`parse_yaml()` handles the block-style YAML that Dashy writes: nested
mappings and sequences, quoted and plain scalars, comments, small flow
collections and `|`/`>` block scalars. Anchors, tags and multi-document
streams are not supported.
"""

from __future__ import annotations

import re


class YamlError(ValueError):
    pass


def _strip_comment(line):
    """Drop a trailing `# comment` that is not inside quotes."""
    quote = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            if index == 0 or line[index - 1] in " \t:-[{,":
                quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index].rstrip()
    return line.rstrip()


def _split_flow(text):
    """Split the inside of a flow collection on top-level commas."""
    parts, depth, quote, current = [], 0, None, ""
    for char in text:
        if quote:
            current += char
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def _find_colon(text):
    """Return the index of the mapping `:` in text, or -1."""
    quote = None
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"" and index == 0:
            quote = char
        elif char == ":" and (index + 1 == len(text) or text[index + 1] in " \t"):
            return index
    return -1


def parse_scalar(text):
    text = text.strip()
    if not text:
        return None
    if text[0] == "'" and text.endswith("'") and len(text) > 1:
        return text[1:-1].replace("''", "'")
    if text[0] == '"' and text.endswith('"') and len(text) > 1:
        body = text[1:-1]
        return re.sub(r'\\(["\\/nt])', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)
    if text[0] == "[" and text.endswith("]"):
        return [parse_scalar(part) for part in _split_flow(text[1:-1])]
    if text[0] == "{" and text.endswith("}"):
        result = {}
        for part in _split_flow(text[1:-1]):
            colon = _find_colon(part)
            if colon < 0:
                result[parse_scalar(part)] = None
            else:
                result[parse_scalar(part[:colon])] = parse_scalar(part[colon + 1:])
        return result
    lowered = text.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~"):
        return None
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?\d+\.\d*", text):
        return float(text)
    return text


class _Parser:
    def __init__(self, text):
        self.lines = []
        raw_lines = text.replace("\t", "  ").splitlines()
        for number, raw in enumerate(raw_lines, 1):
            if raw.strip() in ("---", "..."):
                continue
            # Keep raw text so block scalars can preserve their content.
            stripped = _strip_comment(raw)
            indent = len(raw) - len(raw.lstrip(" "))
            self.lines.append((number, indent, stripped.strip(), raw))
        self.pos = 0

    def _skip_blank(self):
        while self.pos < len(self.lines) and not self.lines[self.pos][2]:
            self.pos += 1

    def _peek(self):
        self._skip_blank()
        if self.pos < len(self.lines):
            return self.lines[self.pos]
        return None

    def parse(self):
        line = self._peek()
        if line is None:
            return None
        value = self._block(line[1])
        if self._peek() is not None:
            raise YamlError("line %d: unexpected indentation" % self._peek()[0])
        return value

    def _block(self, indent):
        line = self._peek()
        if line[2] == "-" or line[2].startswith("- "):
            return self._sequence(indent)
        return self._mapping(indent)

    def _block_scalar(self, parent_indent, style):
        collected = []
        block_indent = None
        while self.pos < len(self.lines):
            _, indent, content, raw = self.lines[self.pos]
            if raw.strip() and indent <= parent_indent:
                break
            if raw.strip():
                if block_indent is None:
                    block_indent = indent
                collected.append(raw[block_indent:])
            else:
                collected.append("")
            self.pos += 1
        while collected and not collected[-1]:
            collected.pop()
        if style.startswith(">"):
            return " ".join(part for part in collected if part)
        return "\n".join(collected)

    def _value_after_key(self, rest, key_indent, number):
        """Parse the value that follows `key:` (inline or as a child block)."""
        if rest in ("|", ">", "|-", ">-", "|+", ">+"):
            return self._block_scalar(key_indent, rest)
        if rest:
            return parse_scalar(rest)
        child = self._peek()
        if child is None:
            return None
        if child[1] > key_indent:
            return self._block(child[1])
        # YAML allows a sequence at the same indent as its parent key.
        if child[1] == key_indent and (child[2] == "-" or child[2].startswith("- ")):
            return self._sequence(key_indent)
        return None

    def _mapping(self, indent, first=None):
        result = {}
        while True:
            if first is not None:
                number, content = first
                first = None
            else:
                line = self._peek()
                if line is None or line[1] < indent:
                    break
                number, line_indent, content, _ = line
                if line_indent > indent:
                    raise YamlError("line %d: unexpected indentation" % number)
                if content == "-" or content.startswith("- "):
                    break
                self.pos += 1
            colon = _find_colon(content)
            if colon < 0:
                raise YamlError("line %d: expected 'key: value'" % number)
            key = parse_scalar(content[:colon])
            result[key] = self._value_after_key(content[colon + 1:].strip(), indent, number)
        return result

    def _sequence(self, indent):
        result = []
        while True:
            line = self._peek()
            if line is None or line[1] != indent:
                break
            number, _, content, _ = line
            if not (content == "-" or content.startswith("- ")):
                break
            self.pos += 1
            rest = content[1:].strip()
            if not rest:
                child = self._peek()
                result.append(self._block(child[1]) if child and child[1] > indent else None)
                continue
            # `- key: value` opens a mapping whose keys align after the dash.
            item_indent = indent + len(content) - len(rest)
            if rest[0] not in "[{" and _find_colon(rest) > 0:
                result.append(self._mapping(item_indent, first=(number, rest)))
            else:
                result.append(parse_scalar(rest))
        return result


def parse_yaml(text):
    return _Parser(text).parse()


def _truthy(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("false", "no", "off", "0", "")


def _codes(value):
    if value is None:
        return frozenset()
    if isinstance(value, int):
        return frozenset([value])
    if isinstance(value, list):
        values = value
    else:
        values = str(value).split(",")
    codes = set()
    for part in values:
        try:
            codes.add(int(str(part).strip()))
        except ValueError:
            pass
    return frozenset(codes)


def extract_services(config):
    """Return (title, sections, page_paths) from a parsed Dashy config.

    Each section is {"name": str, "items": [service, ...]}. A service holds
    the fields the checker needs. Sections that only hold widgets are dropped.
    """
    if not isinstance(config, dict):
        raise YamlError("config is not a mapping")
    page_info = config.get("pageInfo") or {}
    title = page_info.get("title") if isinstance(page_info, dict) else None
    sections = []
    for section in config.get("sections") or []:
        if not isinstance(section, dict):
            continue
        items = []
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            check_url = item.get("statusCheckUrl") or url
            items.append({
                "title": str(item.get("title") or url or "?"),
                "url": str(url) if url else "",
                "check_url": str(check_url) if check_url else "",
                "enabled": bool(check_url) and _truthy(item.get("statusCheck")),
                "accept_codes": _codes(item.get("statusCheckAcceptCodes")),
                "max_redirects": item.get("statusCheckMaxRedirects"),
            })
        if items:
            sections.append({"name": str(section.get("name") or "Section"), "items": items})
    pages = []
    for page in config.get("pages") or []:
        if isinstance(page, dict) and page.get("path"):
            pages.append(str(page["path"]))
    return (str(title) if title else None), sections, pages
