"""Reader-mode HTML rendering for the 8x8 font: parse, then lay out lines.

parse_html() turns a page into blocks (headings, paragraphs, list items,
preformatted text, rules) made of styled spans. layout() wraps those blocks
into screen lines, and paginate() groups lines into screen-sized pages.
There is no CSS or JavaScript: this shows what the HTML itself contains.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from html.parser import HTMLParser

from kvmkit.text import text as _text


def font_text(value):
    """Font-safe text that keeps the punctuation kvmkit can draw."""
    return _text(value, extra=True)

# Elements whose content is hidden. All have end tags; void elements such as
# <input> must not be listed, or everything after them would be skipped.
SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "canvas", "select",
        "button", "textarea", "head", "object", "audio", "video", "map"}
BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "aside", "nav", "ul", "ol",
         "table", "thead", "tbody", "tfoot", "form", "figure", "figcaption", "dl", "dt", "dd", "address",
         "details", "summary", "fieldset", "center", "body", "html", "menu"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
BOLD = {"b", "strong", "th"}
CODE = {"code", "kbd", "samp", "tt"}
SPACE = re.compile(r"\s+")


class Block:
    def __init__(self, kind, level=0, indent=0, prefix=""):
        self.kind = kind          # "para", "heading", "item", "pre", "rule"
        self.level = level        # heading level
        self.indent = indent      # list and quote nesting
        self.prefix = prefix      # "- " or "3. " for list items
        self.spans = []           # (text, style, href)

    def text(self):
        return "".join(span[0] for span in self.spans)


class _Parser(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.blocks = []
        self.block = None
        self.skip = []            # open SKIP elements, innermost last
        self.in_title = False
        self.pre = 0
        self.styles = []
        self.links = []
        self.lists = []           # stack of [kind, counter]
        self.quote = 0
        self.cell = 0

    # -- block management --
    def new_block(self, kind="para", **kwargs):
        self.end_block()
        indent = kwargs.pop("indent", len(self.lists) + self.quote)
        self.block = Block(kind, indent=indent, **kwargs)

    def end_block(self):
        block = self.block
        if block is not None and (block.kind in ("rule",) or block.text().strip()):
            if block.kind != "pre":
                # Collapse whitespace across span boundaries and trim the ends.
                spans, previous_space = [], True
                for text, style, href in block.spans:
                    text = SPACE.sub(" ", text)
                    if previous_space:
                        text = text.lstrip(" ")
                    if text:
                        spans.append((text, style, href))
                        previous_space = text.endswith(" ")
                if spans:
                    last = spans[-1]
                    spans[-1] = (last[0].rstrip(" "), last[1], last[2])
                block.spans = [span for span in spans if span[0]]
            if block.spans or block.kind == "rule":
                self.blocks.append(block)
        self.block = None

    def style(self):
        if self.links:
            return "link"
        return self.styles[-1] if self.styles else "normal"

    # -- parser callbacks --
    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
            return
        if tag in SKIP:
            self.skip.append(tag)
            return
        if self.skip:
            return
        attrs = dict(attrs)
        if tag in HEADINGS:
            self.new_block("heading", level=HEADINGS[tag], indent=0)
        elif tag == "li":
            kind = self.lists[-1] if self.lists else ["ul", 0]
            kind[1] += 1
            self.new_block("item", prefix=("%d. " % kind[1]) if kind[0] == "ol" else "- ",
                           indent=max(0, len(self.lists) - 1) + self.quote)
        elif tag in ("ul", "ol"):
            self.end_block()
            self.lists.append([tag, 0])
        elif tag == "pre":
            self.new_block("pre")
            self.pre += 1
        elif tag == "blockquote":
            self.end_block()
            self.quote += 1
        elif tag == "hr":
            self.new_block("rule")
            self.end_block()
        elif tag == "br":
            if self.pre:
                self.add("\n")
            else:
                kind = self.block.kind if self.block else "para"
                level = self.block.level if self.block else 0
                self.new_block(kind if kind != "item" else "para", level=level)
        elif tag == "tr":
            self.new_block("para")
            self.cell = 0
        elif tag in ("td", "th"):
            if self.cell:
                self.add("  |  ", "dim")
            self.cell += 1
            if tag == "th":
                self.styles.append("bold")
        elif tag in BLOCK:
            self.new_block("para")
        elif tag in BOLD:
            self.styles.append("bold")
        elif tag in CODE:
            self.styles.append("code")
        elif tag == "a":
            href = attrs.get("href") or ""
            self.links.append(urllib.parse.urljoin(self.base_url, href) if href else None)
        elif tag == "img":
            alt = (attrs.get("alt") or "").strip()
            if alt:
                self.add("[%s] " % alt, "dim")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
            return
        if tag in SKIP:
            # Close up to the matching element, tolerating sloppy nesting.
            if tag in self.skip:
                while self.skip and self.skip.pop() != tag:
                    pass
            return
        if self.skip:
            return
        if tag in HEADINGS or tag == "li" or tag == "tr" or tag in BLOCK:
            self.end_block()
            if tag in ("ul", "ol") and self.lists:
                self.lists.pop()
        elif tag == "pre":
            self.end_block()
            self.pre = max(0, self.pre - 1)
        elif tag == "blockquote":
            self.end_block()
            self.quote = max(0, self.quote - 1)
        elif tag in BOLD or tag in CODE:
            if self.styles:
                self.styles.pop()
        elif tag == "a" and self.links:
            self.links.pop()

    def handle_data(self, data):
        if self.in_title:
            self.title += data
            return
        if self.skip:
            return
        self.add(data)

    def add(self, data, style=None):
        if self.block is None:
            if not data.strip():
                return
            self.new_block("para")
        href = self.links[-1] if self.links else None
        self.block.spans.append((data, style or self.style(), href))

    def close(self):
        super().close()
        self.end_block()


def parse_html(html, base_url=""):
    """Return (title, blocks)."""
    parser = _Parser(base_url)
    parser.feed(html)
    parser.close()
    return SPACE.sub(" ", parser.title).strip(), parser.blocks


def parse_plain(body, content_type):
    """Plain text (and pretty-printed JSON) as one preformatted block."""
    if "json" in content_type:
        try:
            body = json.dumps(json.loads(body), indent=2)
        except ValueError:
            pass
    block = Block("pre")
    block.spans = [(body, "code", None)]
    return "", [block]


# -- layout -------------------------------------------------------------------

class Line:
    def __init__(self, height, gap=0):
        self.height = height
        self.gap = gap        # extra space above (paragraph spacing)
        self.segments = []    # (x, text, style, scale, href)
        self.rule = False


def _words(spans):
    """Split spans into (word, style, href, space_before) tokens."""
    tokens = []
    pending_space = False
    for raw, style, href in spans:
        parts = re.split(r"(\s+)", raw)
        for part in parts:
            if not part:
                continue
            if part.isspace():
                pending_space = True
                continue
            tokens.append((font_text(part), style, href, pending_space))
            pending_space = False
    return tokens


def layout(blocks, width, body_scale=1):
    """Wrap blocks into Lines that fit `width` pixels."""
    lines = []
    for index, block in enumerate(blocks):
        gap = 0 if index == 0 else (3 if block.kind == "item" else 6)
        indent = block.indent * 8 * body_scale
        if block.kind == "rule":
            line = Line(6, gap)
            line.rule = True
            lines.append(line)
            continue
        if block.kind == "heading":
            scale = 2 if block.level <= 2 else body_scale
            style = "heading"
        else:
            scale, style = body_scale, None
        char_w = 8 * scale
        line_h = 8 * scale + (2 if scale == 1 else 4)
        if block.kind == "pre":
            # Keep line breaks; hard-wrap long lines.
            limit = max(1, (width - indent) // char_w)
            first = True
            for raw_line in block.text().expandtabs(4).split("\n"):
                raw_line = font_text(raw_line.rstrip())
                chunks = [raw_line[i:i + limit] for i in range(0, len(raw_line), limit)] or [""]
                for chunk in chunks:
                    line = Line(line_h, gap if first else 0)
                    line.segments.append((indent, chunk, "code", scale, None))
                    lines.append(line)
                    first = False
            continue
        line = Line(line_h, gap)
        x = indent
        if block.prefix:
            line.segments.append((x, font_text(block.prefix), "dim", scale, None))
            x += len(block.prefix) * char_w
        wrap_x = x  # continuation lines align with the text after the bullet
        for word, word_style, href, space in _words(block.spans):
            word_style = style or word_style
            if space and x > wrap_x:
                word = " " + word
            while word:
                room = (width - x) // char_w
                if len(word) <= room:
                    line.segments.append((x, word, word_style, scale, href))
                    x += len(word) * char_w
                    break
                if x > wrap_x and len(word.strip()) <= (width - wrap_x) // char_w:
                    lines.append(line)
                    line, x = Line(line_h), wrap_x
                    word = word.lstrip(" ")
                    continue
                # A word longer than a whole line: split it.
                room = max(1, room)
                line.segments.append((x, word[:room], word_style, scale, href))
                lines.append(line)
                line, x = Line(line_h), wrap_x
                word = word[room:]
        if line.segments:
            lines.append(line)
    return lines


def paginate(lines, height):
    """Group lines into pages of at most `height` pixels: [(start, end), ...]."""
    pages, start, used = [], 0, 0
    for index, line in enumerate(lines):
        need = line.height + (line.gap if index > start else 0)
        if index > start and used + need > height:
            pages.append((start, index))
            start, used = index, line.height
        else:
            used += need
    pages.append((start, len(lines)))
    return pages


def decode(body, content_type):
    """Bytes to text using the HTTP charset, a <meta charset>, or UTF-8."""
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if not match:
        match = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:2048], re.I)
    charset = match.group(1) if match else "utf-8"
    if isinstance(charset, bytes):
        charset = charset.decode("ascii", "ignore")
    try:
        return body.decode(charset, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")
