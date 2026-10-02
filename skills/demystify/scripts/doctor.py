#!/usr/bin/env python3
"""Say what this computer can do, what is missing, and the exact fix for each missing thing.

Text, diagram, and page need no tools. The screenshot check needs a Chrome-family browser.
Video needs `uv` and, on macOS and Linux, the cairo library. Voices are optional.

Usage:
    doctor.py            a report for a person
    doctor.py --json     the same as JSON

This script only reads. It does not install or download anything. Show a fix to the user and let
them decide: do not run an install command for them unless they say yes.

Exit status: 0 the video step is ready, 1 it is not.

Standard library only. Python 3.8 or later.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys


sys.dont_write_bytecode = True  # do not leave __pycache__ in the skill folder

from _common import (  # noqa: E402
    CAIRO_INSTALL_HINT,
    UV_INSTALL_HINT,
    cache_dir,
    find_browser,
    find_python,
    find_uv,
    kokoro_cached,
    pkg_config,
    system,
    uv_version,
)


def examine() -> dict:
    which = system()
    items = []

    def item(group, name, ok, detail, fix="", needed=True):
        items.append({"group": group, "name": name, "ok": bool(ok), "detail": detail, "fix": fix, "needed": needed})

    browser = find_browser()
    item("check", "browser", browser, browser or "no Chrome, Chromium, Edge, or Brave found",
         "" if browser else "install one of them, or set DEMYSTIFY_BROWSER to its program. Without it, "
         "diagrams and pages still work, but nobody looks at the rendered result", needed=False)

    uv = find_uv()
    item("video", "uv", uv, ("version " + uv_version(uv)) if uv else "not installed", "" if uv else UV_INSTALL_HINT[which])

    if uv:
        version, found = find_python(uv)
        item("video", "python", True,
             "Python %s is on this computer" % version if found
             else "uv will download Python %s the first time (about 25 MB)" % version)
    else:
        item("video", "python", False, "not known until uv is installed", "", needed=False)

    if which == "windows":
        item("video", "cairo", True, "not needed on Windows")
    else:
        cairo_ok, cairo_detail = pkg_config("cairo")
        item("video", "cairo", cairo_ok, ("version " + cairo_detail) if cairo_ok else cairo_detail,
             "" if cairo_ok else CAIRO_INSTALL_HINT[which])
        if which == "linux":
            pango_ok, pango_detail = pkg_config("pangocairo")
            item("video", "pango", pango_ok, ("version " + pango_detail) if pango_ok else pango_detail,
                 "" if pango_ok else CAIRO_INSTALL_HINT[which])

    ffmpeg = shutil.which("ffmpeg")
    item("video", "ffmpeg", ffmpeg, ffmpeg or "not installed", "not needed: Manim encodes the video itself", needed=False)

    has_key = bool(os.environ.get("ELEVENLABS_API_KEY"))
    item("voice", "elevenlabs", has_key,
         "ELEVENLABS_API_KEY is set (a paid service: ask the user before you use it)" if has_key
         else "ELEVENLABS_API_KEY is not set", needed=False)
    cached = kokoro_cached()
    item("voice", "kokoro", cached and uv,
         "voice model is in %s" % (cache_dir() / "kokoro") if cached
         else "voice model not downloaded: 354 MB, one time, to %s" % (cache_dir() / "kokoro"),
         "" if cached else "ask the user, then run narrate.py with --download", needed=False)
    has_say = which == "macos" and bool(shutil.which("say"))
    item("voice", "say", has_say, "macOS system voice" if has_say else "only on macOS", needed=False)

    video_ready = all(i["ok"] for i in items if i["group"] == "video" and i["needed"])
    voices = [i["name"] for i in items if i["group"] == "voice" and i["ok"]]
    return {
        "system": which,
        "items": items,
        "ready": {"text": True, "diagram": True, "page": True, "look": bool(browser), "video": video_ready},
        "voices": voices,
    }


def render(report: dict) -> str:
    ready = report["ready"]
    lines = ["demystify doctor (%s)" % report["system"], "",
             "  text, diagram, page   ready: they need no tools",
             "  screenshot check      %s" % ("ready" if ready["look"] else "NOT READY (optional)"),
             "  video                 %s" % ("ready" if ready["video"] else "NOT READY"),
             "  voices                %s" % (", ".join(report["voices"]) if report["voices"]
                                              else "none: the video will be silent with subtitles"),
             ""]
    for entry in report["items"]:
        mark = "ok     " if entry["ok"] else ("MISSING" if entry["needed"] else "-      ")
        lines.append("  %s %-11s %s" % (mark, entry["name"], entry["detail"]))
        if entry["fix"] and not entry["ok"]:
            lines.append("          %-11s fix: %s" % ("", entry["fix"]))
    lines.append("")
    if ready["video"]:
        lines.append("The first video render downloads about 120 MB of Python packages into the uv cache and takes about a minute.")
    else:
        lines.append("Show each fix to the user and wait for their answer. Do not run an install command yourself.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Say what this computer can do and what is missing.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = examine()
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0 if report["ready"]["video"] else 1


if __name__ == "__main__":
    sys.exit(main())
