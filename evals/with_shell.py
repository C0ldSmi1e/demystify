#!/usr/bin/env python3
"""Run the diagram and page cases through the real CLI, with a shell, and measure what comes out.

`claude plugin eval` gives its runs no shell on some machines, and then the skill cannot render and
inspect its own work. This script runs the same prompts with `claude -p`, so the agent has a shell.
Each case runs with the plugin loaded and with no plugin. `look.py` then measures every file, the
same way for both.

Usage:
    python3 evals/with_shell.py --runs 3 --model claude-sonnet-5-5 --out evals/results/with-shell.json

Each run is one headless Claude Code session in an empty temporary folder. It may write files and run
shell commands there. The script sets a spending limit for each run (--budget, in dollars).
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent
sys.path.insert(0, str(EVALS))
sys.dont_write_bytecode = True

from measure import mean, measure_file  # noqa: E402

CASES = {"diagram-from-code": "rate-limiter.svg", "page-from-code": "rate-limiter.html"}
TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Skill"]


def prompt_of(case: str) -> str:
    """The prompt of an eval case, without its front matter."""
    text = (EVALS / case / "prompt.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def read_trace(trace: Path) -> dict:
    """What one session did: its cost, and whether it loaded the skill and ran the render check."""
    info = {"skill_loaded": False, "ran_look": 0, "cost_usd": None, "turns": None, "seconds": None}
    for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                given = json.dumps(block.get("input", {}))
                if block.get("name") == "Skill" and "demystify" in given:
                    info["skill_loaded"] = True
                if block.get("name") == "Bash" and "look.py" in given:
                    info["ran_look"] += 1
        elif event.get("type") == "result":
            info["cost_usd"] = round(event.get("total_cost_usd") or 0, 3)
            info["turns"] = event.get("num_turns")
            info["seconds"] = round((event.get("duration_ms") or 0) / 1000)
    return info


def one_run(case: str, arm: str, index: int, model: str, budget: float, keep: Path, reuse: bool = False) -> dict:
    work = Path(tempfile.mkdtemp(prefix="demystify-shell-"))
    trace = keep / ("%s.%s.%d.jsonl" % (case, arm, index))
    command = ["claude", "-p", prompt_of(case), "--model", model, "--setting-sources", "project",
               "--permission-mode", "acceptEdits", "--max-budget-usd", str(budget),
               "--allowedTools"] + TOOLS + ["--disallowedTools", "Bash(open:*)",
               "--output-format", "stream-json", "--verbose"]
    if arm == "with":
        command += ["--plugin-dir", str(REPO)]
    started = time.time()
    row = {"case": case, "arm": arm, "run": index}
    kept = keep / ("%s.%s.%d%s" % (case, arm, index, Path(CASES[case]).suffix))
    try:
        if not reuse or not trace.exists():
            with open(str(trace), "wb") as out:
                subprocess.run(command, cwd=str(work), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.DEVNULL,
                               timeout=2400)
            found = sorted(work.rglob(CASES[case]))
            if found:
                shutil.copyfile(str(found[0]), str(kept))
            row["seconds"] = round(time.time() - started)
        row.update(read_trace(trace))
        if kept.exists():
            row.update(measure_file(kept, mobile=case.startswith("page")))
        else:
            row["missing"] = "no file"
    except subprocess.TimeoutExpired:
        row["missing"] = "the run did not finish in 40 minutes"
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the diagram and page cases with a shell, and measure the files.")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default="claude-sonnet-5-5")
    parser.add_argument("--budget", type=float, default=3.0, help="spending limit for one run, in dollars")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--keep", default=str(EVALS / "results" / "with-shell"), help="folder for traces and files")
    parser.add_argument("--out", help="write the summary as JSON")
    parser.add_argument("--reuse", action="store_true",
                        help="do not run a case again if its trace is in the --keep folder: only measure the files")
    args = parser.parse_args(argv)

    if not shutil.which("claude"):
        print("with_shell: the `claude` command is not installed", file=sys.stderr)
        return 2
    keep = Path(args.keep)
    keep.mkdir(parents=True, exist_ok=True)
    jobs = [(case, arm, index) for case in CASES for arm in ("with", "without") for index in range(1, args.runs + 1)]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(lambda job: one_run(job[0], job[1], job[2], args.model, args.budget, keep, args.reuse), jobs))

    version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    summary = {"claude_version": version, "model": args.model, "runs": args.runs,
               "cost_usd": round(sum(row.get("cost_usd") or 0 for row in rows), 2), "cases": {}}
    for case in CASES:
        print("\n%s" % case)
        summary["cases"][case] = {}
        for arm in ("with", "without"):
            group = [row for row in rows if row["case"] == case and row["arm"] == arm]
            summary["cases"][case][arm] = group
            keys = ("errors", "warnings", "cost_usd", "seconds", "turns")
            print("  %-8s" % arm + "  ".join("%s %s" % (key, mean([row.get(key) for row in group])) for key in keys))
            for row in group:
                notes = []
                if row.get("missing"):
                    notes.append(row["missing"])
                if arm == "with":
                    notes.append("skill loaded" if row.get("skill_loaded") else "SKILL NOT LOADED")
                    notes.append("ran look.py %d times" % row.get("ran_look", 0))
                if row.get("error_rules"):
                    notes.append("errors: " + ", ".join("%s x%d" % item for item in sorted(row["error_rules"].items())))
                if row.get("warning_rules"):
                    notes.append("warnings: " + ", ".join(row["warning_rules"]))
                if "worked_example" in row:
                    notes.append("worked example: %s" % ("yes" if row["worked_example"] else "no"))
                if "says_what_was_checked" in row:
                    notes.append("says what was checked: %s" % ("yes" if row["says_what_was_checked"] else "no"))
                print("           run %d: %s" % (row["run"], "; ".join(notes) if notes else "clean"))
    print("\ntotal cost: $%.2f" % summary["cost_usd"])
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
