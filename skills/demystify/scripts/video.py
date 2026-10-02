#!/usr/bin/env python3
"""Make a narrated explainer video with Manim.

Usage:
    video.py init  PROJECT_DIR           create the project: storyboard.json, scenes.py, scene_kit.py
    video.py draft PROJECT_DIR           fast 720p render, frames to look at, and the faults it can measure
    video.py frame PROJECT_DIR T [T...]  save the frame at each of these seconds: of the last draft, or of the
                                         final video if there is no draft
    video.py final PROJECT_DIR           1080p render: video.mp4, video.srt, poster.png, and a check of the file

Options for draft and final:
    --math       add Typst, so that scenes can use MathTypst("...") for formulas
    --fps N      final only: frames in a second (default 30)
    --poster T   final only: the second of the video that poster.png shows (default: the last picture)

Order of work:
    1. video.py init DIR          2. edit DIR/storyboard.json     3. narrate.py DIR
    4. edit DIR/scenes.py         5. video.py draft DIR, look at DIR/review/, repeat
    6. video.py final DIR

Nothing is installed permanently. Manim runs in a temporary environment that `uv` makes.
Run doctor.py first to see if this computer is ready.

Exit status: 0 done, 1 the render failed or faults were found, 2 the project is not ready.

Standard library only. Python 3.8 or later.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True  # do not leave __pycache__ in the skill folder

from _common import ASSETS_DIR, MANIM, MANIM_MATH, find_python, find_uv, pkg_config, run, system, uv_run

SCRIPTS = Path(__file__).resolve().parent
SCENE = "Video"

STORYBOARD = """{
  "title": "EDIT: the takeaway of the video as one sentence",
  "beats": [
    {
      "id": "b01",
      "narration": "EDIT: the question or the surprise. One or two short sentences.",
      "visual": "EDIT: what appears, moves, or changes on the screen during this beat"
    },
    {
      "id": "b02",
      "narration": "EDIT: the next idea.",
      "visual": "EDIT"
    }
  ]
}
"""

SCENES = '''"""EDIT: one line that says what this video explains."""

from scene_kit import *


class Video(Explainer):
    def construct(self):
        self.scene_question()
        self.clear_scene()
        self.scene_answer()

    # One method for each scene. In it, one `with self.beat(...)` block for each beat.

    def scene_question(self):
        title = T("EDIT: the question", size=TITLE).to_edge(UP, buff=0.8)
        box = RoundedRectangle(width=4.0, height=2.0, corner_radius=0.2, color=BLUE)
        label = T("EDIT", size=BODY).move_to(box)

        with self.beat("b01") as dur:
            self.play(Write(title), run_time=min(1.2, dur * 0.4))
            self.wait_until(dur.starts[-1])  # the last sentence of the beat starts now
            self.play(Create(box), FadeIn(label), run_time=1.0)

    def scene_answer(self):
        takeaway = fit(T("EDIT: the takeaway in one sentence", size=HEAD))

        with self.beat("b02") as dur:
            self.play(FadeIn(takeaway, shift=UP * 0.3), run_time=min(1.0, dur * 0.5))

        self.wait(1.5)  # hold the last picture
'''

HINTS = (
    (r"No such file or directory: 'latex'|latex.*not found|FileNotFoundError.*latex",
     "This object needs LaTeX. Use T(\"...\") for text and build numbers from text. See \"No LaTeX\" in references/video.md."),
    (r"NameError: name '(ShowCreation|TexMobject|TextMobject|FRAME_WIDTH|FRAME_HEIGHT)'",
     "That name is from ManimGL. This is Manim Community 0.21: use Create, Text (or T), config.frame_width."),
    (r"ModuleNotFoundError: No module named 'manimlib'",
     "`manimlib` is ManimGL. Write `from scene_kit import *`."),
    (r"beats\.json is missing",
     "Record the narration first: narrate.py PROJECT_DIR."),
    (r"requires the 'typst' Python package|No module named 'typst'",
     "For formulas, run the command again with --math."),
    (r"Dependency lookup for cairo|pycairo",
     "The cairo library is missing. Run doctor.py and show its fix to the user."),
)


class NotReady(Exception):
    pass


def environment(math: bool):
    uv = find_uv()
    if not uv:
        raise NotReady("`uv` is not installed. Run doctor.py: it prints the command that installs it. Ask the user first.")
    if system() != "windows":
        present, detail = pkg_config("cairo")
        if not present:
            raise NotReady("Manim cannot be built: %s. Run doctor.py: it prints the fix. Ask the user first." % detail)
    python, _found = find_python(uv)
    return uv, python, [MANIM_MATH if math else MANIM, "av", "pillow"]


def init(project: Path) -> int:
    project.mkdir(parents=True, exist_ok=True)
    created = []
    for name, content in (("storyboard.json", STORYBOARD), ("scenes.py", SCENES)):
        target = project / name
        if not target.exists():
            target.write_text(content, encoding="utf-8")
            created.append(name)
    shutil.copyfile(str(ASSETS_DIR / "scene_kit.py"), str(project / "scene_kit.py"))
    created.append("scene_kit.py")
    parent = project.resolve().parent
    ignored = parent.name == "demystify-out" and not (parent / ".gitignore").exists()
    if ignored:
        (parent / ".gitignore").write_text("*\n", encoding="utf-8")
    print("video init: %s" % project)
    print("  wrote %s" % ", ".join(created))
    if ignored:
        print("  wrote %s, so that git ignores the output folder" % (parent / ".gitignore"))
    print("  Next: edit storyboard.json, then run narrate.py %s" % project)
    return 0


def check_project(project: Path) -> dict:
    """Make sure that the narration matches the storyboard, and that the scenes are not the template."""
    for name in ("storyboard.json", "scenes.py"):
        if not (project / name).is_file():
            raise NotReady("%s is missing. Make the project first: video.py init %s" % (project / name, project))
    if not (project / "beats.json").is_file():
        raise NotReady("beats.json is missing. Record the narration first: narrate.py %s" % project)
    try:
        board = json.loads((project / "storyboard.json").read_text(encoding="utf-8"))
        beats = json.loads((project / "beats.json").read_text(encoding="utf-8"))
    except ValueError as exc:
        raise NotReady("a JSON file in the project is not valid: %s" % exc) from exc
    wanted = [(str(b.get("id")), " ".join(str(b.get("narration") or b.get("text") or "").split()),
               " ".join(str(b.get("subtitle") or "").split())) for b in board.get("beats", [])]
    recorded = [(b["id"], b["text"], b.get("written", "")) for b in beats.get("beats", [])]
    if wanted != recorded:
        raise NotReady("storyboard.json changed after the narration was recorded. Run narrate.py %s again. "
                       "It records only the beats that changed." % project)
    source = (project / "scenes.py").read_text(encoding="utf-8")
    if re.search(r"[\"']EDIT\b", source):
        raise NotReady("scenes.py still has template text that starts with EDIT. Write the scenes first.")
    if not re.search(r"^class %s\(" % SCENE, source, re.MULTILINE):
        raise NotReady("scenes.py needs `class %s(Explainer)`." % SCENE)
    kit = project / "scene_kit.py"
    if not kit.exists() or kit.read_bytes() != (ASSETS_DIR / "scene_kit.py").read_bytes():
        shutil.copyfile(str(ASSETS_DIR / "scene_kit.py"), str(kit))
    return {"beats": beats}


def render(project: Path, quality: str, fps, math: bool):
    """Run Manim. Return (mp4 path or None, tail of the output)."""
    uv, python, packages = environment(math)
    media = project / "media"
    args = ["manim", "-q" + quality, "--disable_caching", "-v", "WARNING", "--progress_bar", "none",
            "--media_dir", media.resolve()]
    if fps:
        args += ["--fps", str(fps)]
    args += ["scenes.py", SCENE]
    timeline = project / "timeline.json"
    if timeline.exists():
        timeline.unlink()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    process = run(uv_run(uv, python, packages, args), timeout=3600, cwd=project, env=env)
    output = ((process.stdout or "") + "\n" + (process.stderr or "")).strip()
    for partial in (media / "videos" / "scenes").glob("*/partial_movie_files"):
        shutil.rmtree(str(partial), ignore_errors=True)
    videos = sorted((media / "videos" / "scenes").glob("*/%s.mp4" % SCENE), key=lambda p: p.stat().st_mtime)
    if process.returncode != 0 or not videos or not timeline.exists():
        return None, output
    return videos[-1], output


def explain_failure(output: str, project: Path) -> str:
    """Say what failed in a few lines: the error, the line of scenes.py, a hint, then the raw tail."""
    lines = [line for line in output.splitlines() if line.strip()]
    text = "  The render failed."
    error = next((line.strip() for line in reversed(lines)
                  if re.match(r"^\s*[\w.]*(Error|Exception|KeyboardInterrupt)\b", line)), "")
    if error:
        text += "\n  %s" % error[:300]
    places = re.findall(r"scenes\.py[:\"', ]+(?:line )?(\d+)", output)
    if places:
        number = int(places[-1])
        try:
            source = (project / "scenes.py").read_text(encoding="utf-8").splitlines()[number - 1].strip()
        except (OSError, IndexError):
            source = ""
        text += "\n  at scenes.py line %d%s" % (number, ": " + source if source else "")
    for hint in [hint for pattern, hint in HINTS if re.search(pattern, output)][:2]:
        text += "\n  Hint: %s" % hint
    tail = "\n".join("    " + line[:160] for line in lines[-12:])
    return text + "\n  The end of the Manim output:\n" + tail


def frames(project: Path, video: Path, math: bool, review: bool, poster=None, at=None, poster_at=None) -> dict:
    uv, python, packages = environment(math)
    args = ["python", SCRIPTS / "_frames_worker.py", "--video", video.resolve(),
            "--timeline", (project / "timeline.json").resolve()]
    if review or at:
        args += ["--out", (project / "review").resolve()]
    if at:
        args += ["--at", ",".join("%.3f" % moment for moment in at)]
    if poster:
        args += ["--poster", poster.resolve()]
    if poster_at is not None:
        args += ["--poster-at", "%.3f" % poster_at]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    process = run(uv_run(uv, python, packages, args), timeout=900, cwd=project, env=env)
    try:
        return json.loads((process.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"problem": "\n".join((process.stderr or "").strip().splitlines()[-5:])}


def faults(timeline: dict) -> list:
    found = []
    for item in timeline.get("overruns", []):
        found.append("%s: the animation is %.1f s longer than its narration. Make it shorter, or say more."
                     % (item["beat"], item["seconds"]))
    for item in timeline.get("layout", []):
        where = item["beat"] + (" at %.1f s" % item["at"] if "at" in item else "")
        if item["kind"] == "text-outside-frame":
            found.append("%s: text leaves the frame: \"%s\"" % (where, item["what"]))
        elif item["kind"] == "text-too-small":
            found.append("%s: text is too small to read: %s. Use fewer words or two lines." % (where, item["what"]))
        else:
            found.append("%s: text overlaps other text: %s" % (where, item["what"]))
    for beat_id in timeline.get("unused_beats", []):
        found.append("%s: the narration was recorded, but no scene plays it" % beat_id)
    return found


def draft(project: Path, math: bool) -> int:
    check_project(project)
    video, output = render(project, "m", None, math)
    print("video draft: %s" % project)
    if video is None:
        print(explain_failure(output, project))
        return 1
    timeline = json.loads((project / "timeline.json").read_text(encoding="utf-8"))
    measured = frames(project, video, math, review=True)
    problems = faults(timeline)
    print("  %d beats, %.1f s, %dx%d" % (
        len(timeline["beats"]), timeline["total"], timeline["size"][0], timeline["size"][1]))
    print("  beats: " + "  ".join("%s %.1f-%.1f" % (b["id"], b["start"], b["end"]) for b in timeline["beats"]))
    for problem in problems:
        print("  ERROR %s" % problem)
    if not problems:
        print("  Measured faults: none. The measurement is of the text at the end of each animation (%d moments):"
              % timeline.get("measured", len(timeline["beats"])))
        print("  text in the frame, no text on text, no text too small. And no animation is longer than its narration.")
        print("  It does not measure the picture while an animation runs.")
    else:
        print("  To see a fault, take the frame at its time: video.py frame %s SECONDS" % project)
    if measured.get("problem"):
        print("  The frames could not be taken out of the video: %s" % measured["problem"])
        return 1
    review = project / "review"
    print("  contact sheet: %s (two frames for each beat: the middle and the end)" % (review / "sheet.png"))
    print("  full-size frames: %s/<beat>.png and <beat>-mid.png" % review)
    print("  Now look at the contact sheet, then at the full-size frames. The measurements do not find these faults:")
    print("  a label under a line, an arrow that points at nothing, a crowded frame, an empty frame, a wrong fact.")
    print("  To see other moments: video.py frame %s SECONDS [SECONDS ...]" % project)
    print("  Use it for each moment where something appears, moves fast, or changes: two frames for each beat can miss it.")
    return 1 if problems else 0


def frame(project: Path, moments: list, math: bool) -> int:
    videos = sorted((project / "media" / "videos" / "scenes").glob("*/%s.mp4" % SCENE), key=lambda p: p.stat().st_mtime)
    if not videos and (project / "video.mp4").is_file():
        videos = [project / "video.mp4"]  # the final render deletes the draft
    if not videos or not (project / "timeline.json").is_file():
        raise NotReady("there is no video to take frames from. Run: video.py draft %s" % project)
    measured = frames(project, videos[-1], math, review=False, at=moments)
    if measured.get("problem"):
        print("video frame: %s" % measured["problem"])
        return 1
    print("video frame: from %s" % ("the final video" if videos[-1].name == "video.mp4" else "the last draft"))
    for path in measured.get("stills", []):
        print("  frame: %s" % path)
    return 0


def final(project: Path, math: bool, fps: int, poster_at=None) -> int:
    state = check_project(project)
    video, output = render(project, "h", fps, math)
    print("video final: %s" % project)
    if video is None:
        print(explain_failure(output, project))
        return 1
    timeline = json.loads((project / "timeline.json").read_text(encoding="utf-8"))
    target = project / "video.mp4"
    shutil.copyfile(str(video), str(target))
    subtitles = video.with_suffix(".srt")
    if subtitles.exists():
        shutil.copyfile(str(subtitles), str(project / "video.srt"))
    measured = frames(project, target, math, review=False, poster=project / "poster.png", poster_at=poster_at)

    problems = faults(timeline)
    engine = state["beats"].get("engine", "none")
    info, audio = measured.get("video") or {}, measured.get("audio")
    if measured.get("problem") or not info:
        problems.append("the file could not be read back: %s" % measured.get("problem", "no video stream"))
    else:
        length = measured.get("duration") or 0.0
        if abs(length - timeline["total"]) > 1.0:
            problems.append("the file is %.1f s long, but the scenes are %.1f s long" % (length, timeline["total"]))
        if engine != "none" and not audio:
            problems.append("the file has no audio stream, but a narration was recorded")
        elif engine != "none" and audio["peak"] < 0.01:
            problems.append("the audio stream is silent")
    if info:
        voice = engine + ("/" + state["beats"]["voice"] if state["beats"].get("voice") else "")
        print("  %s: %dx%d, %s frames in a second, %.1f s, %s" % (
            target, info["width"], info["height"], info["fps"], measured.get("duration", 0.0),
            "no audio (subtitles only)" if engine == "none" else "voice " + voice))
        print("  subtitles: %s" % (project / "video.srt"))
        print("  poster: %s (%s)" % (project / "poster.png", "the picture at %.1f s" % poster_at if poster_at is not None
                                       else "the last picture. For a different one, add --poster SECONDS"))
    for problem in problems:
        print("  ERROR %s" % problem)
    if not problems:
        shutil.rmtree(str(project / "media"), ignore_errors=True)  # working files of Manim, about 20 MB
        print("  The file has video%s and the expected length. Nobody listened to the audio: ask the user to listen."
              % ("" if engine == "none" else ", audio that is not silent,"))
        print("  To look at the final picture: video.py frame %s SECONDS [SECONDS ...]" % project)
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Make a narrated explainer video with Manim.")
    parser.add_argument("command", choices=("init", "draft", "frame", "final"))
    parser.add_argument("project", help="the video folder, for example demystify-out/SUBJECT")
    parser.add_argument("seconds", nargs="*", type=float, help="frame only: the moments to save, in seconds")
    parser.add_argument("--math", action="store_true", help="add Typst for formulas (MathTypst)")
    parser.add_argument("--fps", type=int, default=30, help="final only: frames in a second")
    parser.add_argument("--poster", type=float, default=None, metavar="SECONDS",
                        help="final only: the second of the video that poster.png shows (default: the last picture)")
    args = parser.parse_args(argv)

    project = Path(args.project)
    try:
        if args.command == "init":
            return init(project)
        if args.command == "draft":
            return draft(project, args.math)
        if args.command == "frame":
            if not args.seconds:
                print("video: give one or more moments in seconds, for example: video.py frame %s 12.5 14" % project,
                      file=sys.stderr)
                return 2
            return frame(project, args.seconds, args.math)
        return final(project, args.math, args.fps, args.poster)
    except NotReady as exc:
        print("video: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
