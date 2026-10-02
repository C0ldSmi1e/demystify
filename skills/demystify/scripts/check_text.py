#!/usr/bin/env python3
"""Check text against the sentence rules in references/text.md.

It measures what a reader sees: words in each sentence, sentences in each
paragraph, and semicolons. It also gives advice on passive verbs and ornate
words. It cannot check meaning.

Usage:
    check_text.py FILE [FILE ...]        Markdown, plain text, HTML, or a storyboard.json
    check_text.py -                      read Markdown from standard input
    check_text.py --level 100 FILE       strict: no sentence over the limit
    check_text.py --steps FILE           the text is a procedure: each sentence has 20 words or fewer
    check_text.py --json FILE            machine-readable report

The limit is 25 words for each sentence. The script cannot tell an instruction
from a description, so it uses the limit of 20 words only with --steps and for
the narration of a storyboard.

Levels:
    80  (default)  at most 1 sentence in 5 is over the limit, and none by more than 10 words
    100            every sentence is inside the limit

Exit status: 0 pass, 1 fail, 2 cannot read the input.

Standard library only. Python 3.8 or later.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

DESCRIPTION_LIMIT = 25  # words in a descriptive sentence
STEP_LIMIT = 20  # words in an instruction (with --steps) or a narration sentence
PARAGRAPH_LIMIT = 6  # sentences in a paragraph
OVER_MARGIN = 10  # level 80: no sentence is more than this many words over its limit
OVER_SHARE = 0.20  # level 80: at most this share of sentences is over the limit

ABBREVIATIONS = {
    "e.g.", "i.e.", "etc.", "vs.", "cf.", "approx.", "fig.", "no.", "inc.", "ltd.",
    "mr.", "mrs.", "ms.", "dr.", "st.", "al.",
}

# Plain replacements for ornate words. This is common plain-English advice.
# It is not the ASD-STE100 dictionary, which this project does not contain.
ORNATE = {
    "utilize": "use", "utilise": "use", "utilizes": "uses", "utilized": "used", "utilizing": "using",
    "leverage": "use", "leverages": "uses", "leveraging": "using",
    "in order to": "to", "prior to": "before", "subsequent to": "after",
    "commence": "start", "commences": "starts", "terminate": "stop", "terminates": "stops",
    "approximately": "about", "facilitate": "help", "facilitates": "helps",
    "in the event that": "if", "due to the fact that": "because", "a number of": "some",
    "at this point in time": "now", "is able to": "can", "are able to": "can",
    "with regard to": "about", "in the process of": "(delete)", "it is important to note that": "(delete)",
    "spin up": "start", "spins up": "starts", "kick off": "start", "kicks off": "starts",
    "dive into": "read", "reach out": "contact", "circle back": "return",
    "seamless": "(delete, or give the measurement)", "seamlessly": "(delete, or give the measurement)",
    "robust": "(delete, or give the measurement)", "cutting-edge": "(delete)",
    "blazing-fast": "(give the number)", "powerful": "(say what it does)",
}
ORNATE_RE = re.compile(
    r"(?<![\w-])(" + "|".join(sorted((re.escape(k) for k in ORNATE), key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)
PASSIVE_RE = re.compile(
    r"\b(is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?"
    r"(\w{3,}ed|built|done|found|given|kept|known|made|run|seen|sent|set|shown|taken|written|held|read)\b",
    re.IGNORECASE,
)
NOT_PASSIVE = {"need", "speed", "feed", "seed", "indeed", "shed", "embed", "exceed", "proceed", "succeed", "bed", "red"}
SPOKEN_SYMBOLS_RE = re.compile(r"[_/\\<>{}\[\]|=`#@^~]|->|=>")
CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")

FENCE_RE = re.compile(r"^\s*(```|~~~)")
ITEM_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(\s|$)")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
QUOTE_RE = re.compile(r"^\s*>")
RULE_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
INDENT_RE = re.compile(r"^(?: {4}|\t)")
SENTENCE_END_RE = re.compile(r"[.!?:]+[\"'”’)\]]*(?=\s|$)")
SENTENCE_START_RE = re.compile(r"[A-Z0-9\"'“‘(\[]")


class Unit:
    """A paragraph, a list item, or a narration beat."""

    def __init__(self, kind, text, line, limit, source):
        self.kind = kind  # "paragraph" | "item" | "narration"
        self.text = text
        self.line = line
        self.limit = limit
        self.source = source


def clean_inline(text: str) -> str:
    """Reduce Markdown inline syntax to the words that a reader sees."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links
    text = re.sub(r"``[^`]+``|`[^`]+`", " CODE ", text)  # inline code is one word
    text = re.sub(r"https?://\S+", " URL ", text)
    text = re.sub(r"<[^>\s][^>]*>", " ", text)  # inline HTML tags
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list:
    text = re.sub(r"\s+", " ", text).strip()
    sentences, start = [], 0
    for match in SENTENCE_END_RE.finditer(text):
        end = match.end()
        chunk = text[start:end]
        if not chunk.strip():
            continue
        last_word = chunk.split()[-1].lower()
        if match.group(0)[0] == ":" and end != len(text):
            continue  # a colon ends a sentence only when it introduces a list
        if last_word in ABBREVIATIONS:
            continue
        following = text[end:].lstrip()
        if following and not SENTENCE_START_RE.match(following):
            continue
        sentences.append(chunk.strip())
        start = end
    rest = text[start:].strip()
    if rest:
        sentences.append(rest)
    return sentences


def count_words(sentence: str) -> int:
    return sum(1 for word in sentence.split() if re.search(r"[^\W_]", word))


def is_cjk(text: str) -> bool:
    letters = re.findall(r"[^\W\d_]", text)
    return bool(letters) and len(CJK_RE.findall(text)) / len(letters) > 0.3


# --------------------------------------------------------------------------- readers


def units_from_markdown(text: str, source: str, limit: int) -> list:
    units = []
    paragraph, paragraph_line = [], 0
    item, item_line = [], 0
    in_fence = False

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            body = clean_inline(" ".join(paragraph))
            if body:
                units.append(Unit("paragraph", body, paragraph_line, limit, source))
        paragraph = []

    def flush_item():
        nonlocal item
        if item:
            body = clean_inline(" ".join(item))
            if body:
                units.append(Unit("item", body, item_line, limit, source))
        item = []

    lines = text.splitlines()
    front_matter_end = 0
    if lines and lines[0].strip() == "---":  # YAML front matter is data, not prose
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                front_matter_end = index + 1
                break

    for number, raw in enumerate(lines, 1):
        if number <= front_matter_end:
            continue
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            flush_paragraph()
            flush_item()
            continue
        if in_fence:
            continue
        if not raw.strip():
            flush_paragraph()
            flush_item()
            continue
        if HEADING_RE.match(raw) or TABLE_RE.match(raw) or QUOTE_RE.match(raw) or RULE_RE.match(raw):
            flush_paragraph()
            flush_item()
            continue
        if raw.lstrip().startswith("<!--"):
            continue
        match = ITEM_RE.match(raw)
        if match:
            flush_paragraph()
            flush_item()
            item, item_line = [match.group(2)], number
            continue
        if INDENT_RE.match(raw) and not item and not paragraph:
            continue  # indented code block
        if item:
            item.append(raw.strip())
        else:
            if not paragraph:
                paragraph_line = number
            paragraph.append(raw.strip())
    flush_paragraph()
    flush_item()
    return units


class _HTMLUnits(HTMLParser):
    SKIP = {"script", "style", "pre", "svg", "template", "noscript", "math", "blockquote", "head", "textarea"}
    HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    BLOCK = {
        "p", "div", "section", "article", "main", "header", "footer", "aside", "nav", "figure", "figcaption",
        "td", "th", "tr", "table", "dd", "dt", "summary", "details", "label", "button", "ul", "ol", "br", "hr",
        "form", "fieldset", "legend", "select", "option",
    }

    CODE = {"code", "kbd", "samp"}

    def __init__(self, source, limit):
        super().__init__(convert_charrefs=True)
        self.source, self.limit = source, limit
        self.units = []
        self.skip = []  # stack of open tags whose text is not prose
        self.heading_depth = 0
        self.buffer = []
        self.kind, self.line = "paragraph", 1

    def _flush(self):
        body = re.sub(r"\s+", " ", " ".join(self.buffer)).strip()
        if body and not self.heading_depth:
            self.units.append(Unit(self.kind, body, self.line, self.limit, self.source))
        self.buffer = []
        self.kind = "paragraph"

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP or tag in self.CODE:
            if not self.skip and tag in self.CODE:
                self.buffer.append("CODE")  # inline code counts as one word
            self.skip.append(tag)
            return
        if self.skip:
            return
        if tag in self.HEADINGS:
            self._flush()
            self.heading_depth += 1
        elif tag == "li":
            self._flush()
            self.kind = "item"
            self.line = self.getpos()[0]
        elif tag in self.BLOCK:
            self._flush()
            self.line = self.getpos()[0]

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag in self.HEADINGS:
            self.buffer = []
            self.heading_depth = max(0, self.heading_depth - 1)
        elif tag == "li" or tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if self.skip or not data.strip():
            return
        if not self.buffer:
            self.line = self.getpos()[0]
        self.buffer.append(data)


def units_from_html(text: str, source: str, limit: int) -> list:
    parser = _HTMLUnits(source, limit)
    parser.feed(text)
    parser.close()
    parser._flush()
    # A fragment of interface text (a button label, a table cell) is not a sentence.
    return [u for u in parser.units if count_words(u.text) >= 4]


def units_from_storyboard(data: dict, source: str, limit: int = STEP_LIMIT) -> list:
    units = []
    for index, beat in enumerate(data.get("beats", []), 1):
        text = beat.get("narration") or beat.get("text") or ""
        if text.strip():
            units.append(Unit("narration", text.strip(), index, limit, "%s beat %s" % (source, beat.get("id", index))))
    return units


def read_units(path: str, limit: int = DESCRIPTION_LIMIT, narration_limit: int = STEP_LIMIT) -> list:
    if path == "-":
        return units_from_markdown(sys.stdin.read(), "<stdin>", limit)
    file = Path(path)
    text = file.read_text(encoding="utf-8", errors="replace")
    suffix = file.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
        if not isinstance(data, dict) or "beats" not in data:
            raise ValueError("%s: a JSON input must be a storyboard with a 'beats' list" % path)
        return units_from_storyboard(data, path, narration_limit)
    head = text.lstrip()[:200].lower()
    if suffix in (".html", ".htm") or head.startswith("<!doctype html") or head.startswith("<html"):
        return units_from_html(text, path, limit)
    return units_from_markdown(text, path, limit)


# --------------------------------------------------------------------------- checks


def excerpt(text: str, width: int = 78) -> str:
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def check(units: list, level: int) -> dict:
    sentences, findings, advice = [], [], []
    skipped_languages = 0
    for unit in units:
        parts = split_sentences(unit.text)
        # A lead-in such as "Example." is a label, not a sentence of the paragraph.
        counted = len(parts) - (1 if len(parts) > 1 and count_words(parts[0]) <= 2 else 0)
        if unit.kind == "paragraph" and counted > PARAGRAPH_LIMIT:
            findings.append({
                "rule": "paragraph", "source": unit.source, "line": unit.line, "error": True,
                "message": "%d sentences in one paragraph (limit %d): divide it into two paragraphs"
                           % (counted, PARAGRAPH_LIMIT),
                "text": excerpt(unit.text),
            })
        for part in parts:
            if ";" in part:
                findings.append({
                    "rule": "semicolon", "source": unit.source, "line": unit.line, "error": True,
                    "message": "semicolon: write two sentences", "text": excerpt(part),
                })
            if is_cjk(part):
                skipped_languages += 1
                continue
            sentences.append({"words": count_words(part), "limit": unit.limit, "unit": unit, "text": part})
            for match in ORNATE_RE.finditer(part):
                advice.append({
                    "rule": "plain-word", "source": unit.source, "line": unit.line,
                    "message": '"%s" -> %s' % (match.group(1), ORNATE[match.group(1).lower()]),
                })
            for match in PASSIVE_RE.finditer(part):
                if match.group(2).lower() in NOT_PASSIVE:
                    continue
                advice.append({
                    "rule": "passive", "source": unit.source, "line": unit.line,
                    "message": 'possible passive "%s": name who or what does the action' % match.group(0),
                })
            if unit.kind == "narration" and SPOKEN_SYMBOLS_RE.search(part):
                advice.append({
                    "rule": "spoken", "source": unit.source, "line": unit.line,
                    "message": "symbols in narration: write the words as a person says them",
                })

    over = sorted((s for s in sentences if s["words"] > s["limit"]), key=lambda s: s["limit"] - s["words"])
    allowed = 0 if level >= 100 else int(OVER_SHARE * len(sentences))
    for rank, sentence in enumerate(over):  # worst offender first
        extreme = level < 100 and sentence["words"] > sentence["limit"] + OVER_MARGIN
        # At level 80 the mildest offenders fill the allowance, so the longest ones are the errors.
        is_error = level >= 100 or extreme or rank < len(over) - allowed
        note = "limit %d" % sentence["limit"]
        if not is_error:
            note += ", and level 80 permits this one"
        elif extreme:
            note += ", and no sentence can have more than %d" % (sentence["limit"] + OVER_MARGIN)
        elif level < 100:
            note += ", and level 80 permits only %d long sentence%s in this text" % (allowed, "" if allowed == 1 else "s")
        findings.append({
            "rule": "too-long" if is_error else "long",
            "source": sentence["unit"].source, "line": sentence["unit"].line, "error": is_error,
            "message": "%d words (%s)" % (sentence["words"], note), "text": excerpt(sentence["text"]),
        })

    errors = [f for f in findings if f["error"]]
    stats = {
        "level": level,
        "sentences": len(sentences),
        "over_limit": len(over),
        "over_share": round(len(over) / len(sentences), 3) if sentences else 0.0,
        "allowed_over": allowed,
        "longest": max((s["words"] for s in sentences), default=0),
        "words": sum(s["words"] for s in sentences),
        "long_paragraphs": sum(1 for f in findings if f["rule"] == "paragraph"),
        "semicolons": sum(1 for f in findings if f["rule"] == "semicolon"),
        "length_not_checked": skipped_languages,
    }
    return {"ok": not errors, "stats": stats, "findings": findings, "advice": advice}


def render(report: dict) -> str:
    stats = report["stats"]
    lines = ["check_text: %s (level %d)" % ("PASS" if report["ok"] else "FAIL", stats["level"])]
    limits = sorted(set(report.get("limits") or [DESCRIPTION_LIMIT]))
    lines.append("  %d words in %d sentence%s \u00b7 longest sentence %d words \u00b7 limit %s words for each sentence" % (
        stats["words"], stats["sentences"], "" if stats["sentences"] == 1 else "s", stats["longest"],
        " or ".join(str(limit) for limit in limits)))
    long_line = "  sentences over the limit: %d" % stats["over_limit"]
    if stats["level"] < 100:
        long_line += " \u00b7 level 80 permits %d in this text, and none that is more than %d words over" % (
            stats["allowed_over"], OVER_MARGIN)
    lines.append(long_line)
    lines.append("  paragraphs over %d sentences: %d \u00b7 semicolons: %d" % (
        PARAGRAPH_LIMIT, stats["long_paragraphs"], stats["semicolons"]))
    lines.append("  Inline code, a file name in code format, and a link each count as one word.")
    if report.get("narration"):
        lines.append("  This is narration: each sentence has %d words or fewer, with no exceptions." % STEP_LIMIT)
    elif STEP_LIMIT not in limits:
        lines.append("  The script does not know which sentences are instructions. An instruction has %d words or fewer:"
                     % STEP_LIMIT)
        lines.append("  count those yourself, or add --steps if all the text is a procedure.")
    if report.get("html"):
        lines.append("  From the page, the script read the text that is in the HTML: paragraphs, list items, captions.")
        lines.append("  It did not read text that a script makes, text in a picture (svg), code, or headings.")
    if stats["length_not_checked"]:
        lines.append("  %d sentences are in a language without spaces between words: length not checked"
                     % stats["length_not_checked"])
    if stats["sentences"] == 0 and not stats["length_not_checked"]:
        lines.append("  no prose found: nothing to check")
    for finding in sorted(report["findings"], key=lambda f: (not f["error"], f["source"], f["line"])):
        mark = "ERROR" if finding["error"] else "note "
        lines.append("  %s %s:%s [%s] %s: \"%s\"" % (
            mark, finding["source"], finding["line"], finding["rule"], finding["message"], finding["text"]))
    if not report["ok"]:
        lines.append("  Fix each ERROR line, then run the check again. Shorten the longest sentences first.")
    if report["advice"]:
        lines.append("Advice (does not change the result):")
        seen = set()
        for item in report["advice"]:
            key = (item["source"], item["line"], item["message"])
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > 12:
                lines.append("  ... %d more" % (len(report["advice"]) - 12))
                break
            lines.append("  %s:%s %s" % (item["source"], item["line"], item["message"]))
    else:
        lines.append("Advice: none (no passive verbs or ornate words found).")
    lines.append("This script checks form only: sentence length, paragraph length, semicolons. It does not check")
    lines.append("meaning, and it does not check the extra rules of the strict level. Those checks are yours.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check text against the sentence rules in references/text.md.")
    parser.add_argument("files", nargs="+", help="Markdown, text, HTML, or storyboard.json files. Use - for standard input.")
    parser.add_argument("--level", type=int, choices=(80, 100), default=None,
                        help="80 (default) or 100 (strict). A storyboard is always checked at 100")
    parser.add_argument("--max-words", type=int, default=None,
                        help="word limit for every sentence (default 25, and 20 for narration)")
    parser.add_argument("--steps", action="store_true", help="the text is a procedure: limit 20 words for every sentence")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    limit = args.max_words or (STEP_LIMIT if args.steps else DESCRIPTION_LIMIT)
    units = []
    try:
        for name in args.files:
            units.extend(read_units(name, limit, args.max_words or STEP_LIMIT))
    except (OSError, ValueError) as exc:
        print("check_text: cannot read input: %s" % exc, file=sys.stderr)
        return 2

    narration = bool(units) and all(unit.kind == "narration" for unit in units)
    level = args.level or (100 if narration else 80)
    report = check(units, level)
    report["html"] = any(str(name).lower().endswith((".html", ".htm")) for name in args.files)
    report["narration"] = narration
    report["limits"] = sorted(set(unit.limit for unit in units)) or [limit]
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
