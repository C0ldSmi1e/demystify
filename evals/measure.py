#!/usr/bin/env python3
"""Measure what `claude plugin eval` produced, with the skill's own check scripts.

The graders in this folder are pass/fail, and a capable model passes them with or without the
skill. This script looks closer. It takes the results of one eval run and measures every output,
from the runs with the plugin and from the runs without it:

    text      words in each sentence, sentences in each paragraph, headings     (check_text.py)
    diagram   text that overlaps, leaves its box, or leaves the drawing         (look.py)
    page      script errors, sideways scroll on a phone, faint or tiny text     (look.py)

For a diagram and a page it also looks for two things in the words: a worked example (a wait time
that someone calculated, such as 0.2 s), and a mark that says what was tested, inferred, or not verified.

Usage:
    claude plugin eval . --keep-temp --json results.json --allow-tools Write Edit ...
    python3 evals/measure.py results.json [--out summary.json]

Run it soon after the eval: it reads the folders that `--keep-temp` leaves in the temp directory.
Standard library only.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "demystify" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True  # do not leave __pycache__ in the skill folder

import check_text  # noqa: E402
import look  # noqa: E402

FILES = {"diagram-from-code": "rate-limiter.svg", "page-from-code": "rate-limiter.html"}


def final_reply(trace: Path) -> str:
    reply = ""
    for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            reply = event["result"]
    return reply


def produced_file(trace: Path, name: str):
    kept = trace.parent.parent
    for folder in (kept, kept / "sealed"):
        try:
            os.chmod(str(folder), stat.S_IRWXU)  # the eval seals what the run wrote; these are our own temp files
        except OSError:
            pass
    found = sorted(kept.rglob(name))
    return found[0] if found else None


def measure_text(reply: str) -> dict:
    units = check_text.units_from_markdown(reply, "reply", 25)
    report = check_text.check(units, 80)
    stats = report["stats"]
    lengths = [check_text.count_words(s) for u in units for s in check_text.split_sentences(u.text)]
    return {
        "passes_check": report["ok"],
        "sentences": stats["sentences"],
        "mean_words": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "longest_sentence": stats["longest"],
        "over_limit": stats["over_limit"],
        "words": sum(lengths),
        "headings": len(re.findall(r"^#{1,6} ", reply, re.MULTILINE)),
        "answer_in_first_line": not reply.lstrip().startswith("#"),
    }


def measure_words(path: Path) -> dict:
    """What the words of a diagram or a page tell the reader about this rate limiter."""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    words = html.unescape(re.sub(r"<[^>]+>", " ", text))
    result = {
        "words": len(words.split()),
        "says_what_was_checked": bool(re.search(r"(?i)\b(tested|inferred|not verified)\b", words)),
    }
    if path.suffix.lower() == ".svg":  # a page writes its example with a script, so its words do not show it
        # A wait that someone calculated: "Retry-After: 0.2", "0.2 s", "= 0.1".
        result["worked_example"] = bool(
            re.search(r"(?i)retry-after\W{0,4}0\.\d|\b0\.\d+\s*(s|sec|seconds)\b|=\s*0\.\d", words))
    return result


def measure_file(path: Path, mobile: bool) -> dict:
    work = Path(tempfile.mkdtemp(prefix="demystify-measure-"))
    try:
        copy = work / path.name
        shutil.copyfile(str(path), str(copy))
        report = look.look(copy, work / "review", mobile, look.DESKTOP_WIDTH)
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    rules = {}
    for item in report["errors"]:
        rules[item["rule"]] = rules.get(item["rule"], 0) + 1
    result = {
        "rendered": report["rendered"],
        "errors": len(report["errors"]),
        "warnings": len(report["warnings"]),
        "error_rules": rules,
        "warning_rules": sorted({w["rule"] for w in report["warnings"]}),
        "bytes": path.stat().st_size,
    }
    result.update(measure_words(path))
    return result


def mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure the outputs of one `claude plugin eval` run.")
    parser.add_argument("results", help="the file that `claude plugin eval --json FILE` wrote")
    parser.add_argument("--out", help="write the summary as JSON")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.results).read_text(encoding="utf-8"))
    summary = {"claude_version": data.get("claudeVersion"), "started": data.get("startedAt"),
               "cost_usd": data.get("costUsd"), "cases": {}}
    for case in data["cases"]:
        name = case["name"]
        entry = {}
        for arm, runs in case["arms"].items():
            rows = []
            for run in runs:
                trace = Path(run["tracePath"])
                row = {"score": run["score"], "turns": run.get("turns"), "cost_usd": round(run.get("costUsd") or 0, 3),
                       "skill_loaded": any(g["name"] == "skill-fired" and g["passed"] for g in run["graders"])}
                if not trace.exists():
                    row["missing"] = "the kept folder is gone"
                elif name == "text-explains-code":
                    row.update(measure_text(final_reply(trace)))
                elif name in FILES:
                    path = produced_file(trace, FILES[name])
                    row.update(measure_file(path, mobile=name.startswith("page")) if path else {"missing": "no file"})
                rows.append(row)
            entry[arm] = rows
        summary["cases"][name] = entry

    for name, entry in summary["cases"].items():
        print("\n%s" % name)
        for arm in ("with", "without"):
            rows = entry.get(arm, [])
            if not rows:
                continue
            keys = [k for k in ("score", "turns", "cost_usd", "sentences", "mean_words", "longest_sentence", "over_limit",
                                "headings", "errors", "warnings") if any(k in r for r in rows)]
            line = "  %-8s" % arm + "  ".join("%s %s" % (k, mean([r.get(k) for r in rows])) for k in keys)
            print(line)
            for row in rows:
                detail = row.get("error_rules") or {}
                extra = []
                if "passes_check" in row:
                    extra.append("check %s" % ("pass" if row["passes_check"] else "FAIL"))
                    extra.append("answer first: %s" % ("yes" if row["answer_in_first_line"] else "no"))
                if detail:
                    extra.append("errors: " + ", ".join("%s x%d" % kv for kv in sorted(detail.items())))
                if row.get("warning_rules"):
                    extra.append("warnings: " + ", ".join(row["warning_rules"]))
                if "worked_example" in row:
                    extra.append("worked example: %s" % ("yes" if row["worked_example"] else "no"))
                if "says_what_was_checked" in row:
                    extra.append("says what was checked: %s" % ("yes" if row["says_what_was_checked"] else "no"))
                if row.get("missing"):
                    extra.append(row["missing"])
                print("           run: %s" % "; ".join(extra))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print("\nwrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
