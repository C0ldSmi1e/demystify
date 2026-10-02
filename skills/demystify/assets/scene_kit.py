"""Scene kit for demystify videos. For Manim Community 0.21.

`video.py init` copies this file into the video project. Edit scenes.py, not this file.

What it gives you:

    from scene_kit import *          # the Manim API, plus the names below

    T(text, size=BODY, color=FG, weight=NORMAL)   # text that needs no LaTeX and uses a font that exists
    M(text, size=BODY, color=FG)                  # the same, in the monospace font
    FG MUTED BLUE YELLOW GREEN RED PURPLE BG      # one palette for every video
    TITLE HEAD BODY SMALL                         # font sizes: 46, 36, 28, 22
    fit(mobject, max_width=13.0, max_height=7.0)  # make it smaller if it is larger than this

    class Video(Explainer):
        def construct(self):
            with self.beat("b01") as dur:           # plays the narration of beat b01 and adds its subtitles
                self.play(..., run_time=1.0)
                self.wait_until(dur.starts[1])      # wait for the second sentence of the beat
                self.play(..., run_time=1.0)
                self.wait_until(dur.at("five requests"))   # wait until the voice says these words
            self.clear_scene()                      # fade out everything

`dur` is the length of the narration in seconds. `dur.starts` has the second at which each
sentence of the beat starts. `dur.at("words")` estimates the second at which the voice says the
words. The block lasts until the voice stops, plus a short gap.

In a beat, the kit measures the picture at the end of each animation. It records text that leaves
the frame, text that overlaps other text, text that is too small, and animation that runs longer
than its narration. `video.py draft` prints these faults. It does not measure the picture while an
animation runs.

The kit keeps its own data in attributes that start with `_dm_`. Do not use that prefix.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import manimpango
from manim import *  # noqa: F401,F403
from manim import (
    NORMAL,
    FadeOut,
    ManimColor,
    Scene,
    Text,
    config,
)

PROJECT = Path(__file__).resolve().parent

# One palette. These names replace Manim's own BLUE, YELLOW, GREEN, RED, and PURPLE.
BG = ManimColor("#0e1116")
FG = ManimColor("#e6edf3")
MUTED = ManimColor("#9aa4b0")
BLUE = ManimColor("#58c4dd")
YELLOW = ManimColor("#f2cc60")
GREEN = ManimColor("#7ee787")
RED = ManimColor("#ff7b72")
PURPLE = ManimColor("#d2a8ff")

# Font sizes. Do not show text that is smaller than SMALL: the draft reports it.
TITLE, HEAD, BODY, SMALL = 46, 36, 28, 22

# Keep content in this area. The full frame is 14.2 wide and 8 high.
SAFE_WIDTH, SAFE_HEIGHT = 13.0, 7.0


def _first_installed(candidates):
    installed = set(manimpango.list_fonts())
    for name in candidates:
        if name in installed:
            return name
    return ""


FONT = _first_installed(["Inter", "Helvetica Neue", "Helvetica", "Arial", "Segoe UI", "DejaVu Sans", "Liberation Sans", "Noto Sans"])
MONO = _first_installed(["JetBrains Mono", "SF Mono", "Menlo", "DejaVu Sans Mono", "Liberation Mono", "Consolas", "Courier New"])


def T(text, size=BODY, color=FG, weight=NORMAL, **kwargs):
    """Text in the sans-serif font of the kit. Needs no LaTeX."""
    if FONT:
        kwargs.setdefault("font", FONT)
    return Text(str(text), font_size=size, color=color, weight=weight, **kwargs)


def M(text, size=BODY, color=FG, **kwargs):
    """Text in the monospace font of the kit: code, numbers, identifiers."""
    if MONO:
        kwargs.setdefault("font", MONO)
    return Text(str(text), font_size=size, color=color, **kwargs)


def fit(mobject, max_width=SAFE_WIDTH, max_height=SAFE_HEIGHT):
    """Make a mobject smaller if it is larger than the given size. Returns the mobject.

    If text becomes very small as a result, the draft reports it. Then use fewer words or two lines.
    """
    if mobject.width > max_width:
        mobject.scale(max_width / mobject.width)
    if mobject.height > max_height:
        mobject.scale(max_height / mobject.height)
    return mobject


class Beat(float):
    """The length of the narration of a beat, in seconds.

    `starts` has the second, from the start of the beat, at which each sentence starts.
    `starts[0]` is 0.0. Use it with `self.wait_until(dur.starts[1])`.
    """

    starts = (0.0,)
    sentences = ()

    def at(self, words):
        """The second, from the start of the beat, at which the voice says these words.

        The kit knows when each sentence starts and ends. In a sentence, this is an estimate from
        the position of the words. Use it with `self.wait_until(dur.at("five requests"))`.
        """
        wanted = " ".join(str(words).lower().split())
        for sentence in self.sentences:
            spoken = " ".join(sentence["text"].lower().split())
            position = spoken.find(wanted)
            if wanted and position >= 0:
                share = position / float(max(1, len(spoken)))
                return sentence["start"] + share * (sentence["end"] - sentence["start"])
        raise ValueError("the narration of this beat does not say %r. It says: %s"
                         % (words, " ".join(sentence["text"] for sentence in self.sentences)))


_TEXT_CLASSES = {"Text", "MarkupText", "Paragraph", "MathTex", "Tex", "SingleStringMathTex", "Typst", "MathTypst"}
_SMALLEST_FONT = SMALL  # text below this size is hard to read in a video


def _load_beats():
    path = PROJECT / "beats.json"
    if not path.exists():
        raise FileNotFoundError(
            "beats.json is missing. Record the narration first: python3 SKILL_DIR/scripts/narrate.py %s" % PROJECT)
    data = json.loads(path.read_text(encoding="utf-8"))
    return {beat["id"]: beat for beat in data["beats"]}


class Explainer(Scene):
    """Base class of a demystify video. Write `class Video(Explainer)` in scenes.py."""

    GAP = 0.3  # seconds of silence after each beat

    def setup(self):
        self.camera.background_color = BG
        self._dm_beats = _load_beats()
        self._dm_used = []
        self._dm_seen = set()
        self._dm_timeline = []
        self._dm_overruns = []
        self._dm_layout = []
        self._dm_beat_start = 0.0
        self._dm_current = None
        self._dm_measured = 0

    @contextmanager
    def beat(self, beat_id):
        """Play the narration of one beat while the animations in the block run.

        Gives the length of the narration in seconds (a `Beat`). The audio starts at the real clock
        of the scene, so the voice and the picture stay together.
        """
        if beat_id not in self._dm_beats:
            raise KeyError(
                "beat %r is not in beats.json. Beats there: %s. If you changed the storyboard, run narrate.py again."
                % (beat_id, ", ".join(self._dm_beats)))
        if beat_id in self._dm_used:
            raise ValueError("beat %r is used two times in scenes.py" % beat_id)
        self._dm_used.append(beat_id)
        data = self._dm_beats[beat_id]
        start = self._dm_beat_start = self.renderer.time
        if data.get("audio"):
            self.add_sound(str(PROJECT / data["audio"]))
        sentences = data.get("sentences") or [{"text": data["text"], "start": 0.0, "end": data["duration"]}]
        if data.get("subtitle"):  # one written form for the full beat
            self.add_subcaption(data["subtitle"], duration=max(0.5, data["duration"]), offset=0)
        else:
            for sentence in sentences:
                self.add_subcaption(sentence.get("subtitle") or sentence["text"],
                                    duration=max(0.5, sentence["end"] - sentence["start"]), offset=sentence["start"])
        length = Beat(data["duration"])
        length.starts = tuple(sentence["start"] for sentence in sentences)
        length.sentences = tuple(sentences)
        self._dm_current = beat_id
        yield length
        rest = data["duration"] + self.GAP - (self.renderer.time - start)
        if rest > 1 / config.frame_rate:
            self.wait(rest)
        elif rest < -0.5:
            self._dm_overruns.append({"beat": beat_id, "seconds": round(-rest, 2)})
        self._dm_timeline.append({
            "id": beat_id, "start": round(start, 3), "end": round(self.renderer.time, 3),
            "narration": data["duration"],
        })
        self._dm_measure(beat_id)
        self._dm_current = None

    def play(self, *args, **kwargs):
        """Play the animations. In a beat, the kit then measures the picture."""
        super().play(*args, **kwargs)
        if getattr(self, "_dm_current", None):
            self._dm_measure(self._dm_current)

    def wait_until(self, seconds):
        """Wait until this many seconds after the start of the current beat. Does nothing if that time is past."""
        rest = float(seconds) - (self.renderer.time - self._dm_beat_start)
        if rest > 1 / config.frame_rate:
            self.wait(rest)

    def clear_scene(self, run_time=0.5):
        """Fade out everything on the screen. Call it between scenes.

        It stops the updaters first, because an object that draws itself again in each frame does not fade.
        """
        mobjects = list(self.mobjects)
        for mobject in mobjects:
            mobject.clear_updaters()
        if mobjects:
            self.play(*[FadeOut(m) for m in mobjects], run_time=run_time)

    # ------------------------------------------------------------------ measurement

    def _dm_texts(self):
        found = []

        def walk(mobject):
            if type(mobject).__name__ in _TEXT_CLASSES:
                found.append(mobject)
                return
            for child in mobject.submobjects:
                walk(child)

        for mobject in self.mobjects:
            walk(mobject)
        return found

    @staticmethod
    def _dm_opacity(mobject):
        values = []
        for part in mobject.family_members_with_points():
            for getter in ("get_fill_opacity", "get_stroke_opacity"):
                try:
                    values.append(float(getattr(part, getter)()))
                except Exception:  # noqa: BLE001 - an object without that property
                    pass
        return max(values) if values else 0.0

    @staticmethod
    def _dm_label(mobject):
        text = getattr(mobject, "original_text", None) or getattr(mobject, "text", None) or type(mobject).__name__
        text = " ".join(str(text).split())
        return text if len(text) <= 40 else text[:39] + "…"

    def _dm_fault(self, beat_id, kind, what):
        key = (kind, what)
        if key not in self._dm_seen:
            self._dm_seen.add(key)
            self._dm_layout.append({"beat": beat_id, "kind": kind, "what": what, "at": round(float(self.renderer.time), 2)})

    def _dm_measure(self, beat_id):
        self._dm_measured += 1
        half_w, half_h = config.frame_width / 2, config.frame_height / 2
        boxes = []
        for text in self._dm_texts():
            if text.width < 1e-6 or text.height < 1e-6 or self._dm_opacity(text) < 0.05:
                continue
            label = self._dm_label(text)
            left, right = float(text.get_left()[0]), float(text.get_right()[0])
            bottom, top = float(text.get_bottom()[1]), float(text.get_top()[1])
            if left < -half_w - 0.02 or right > half_w + 0.02 or bottom < -half_h - 0.02 or top > half_h + 0.02:
                self._dm_fault(beat_id, "text-outside-frame", label)
            try:
                size = float(text.font_size)
            except Exception:  # noqa: BLE001 - a formula has no font size
                size = None
            if size is not None and size < _SMALLEST_FONT - 0.5:
                self._dm_fault(beat_id, "text-too-small", "%s (size %d, smallest is %d)" % (label, round(size), _SMALLEST_FONT))
            boxes.append((left, right, bottom, top, label))
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                width = min(a[1], b[1]) - max(a[0], b[0])
                height = min(a[3], b[3]) - max(a[2], b[2])
                if width <= 0 or height <= 0:
                    continue
                smaller = min((a[1] - a[0]) * (a[3] - a[2]), (b[1] - b[0]) * (b[3] - b[2]))
                if width * height > 0.15 * smaller:
                    self._dm_fault(beat_id, "text-overlap", "%s / %s" % tuple(sorted((a[4], b[4]))))

    def tear_down(self):
        report = {
            "fps": float(config.frame_rate),
            "size": [int(config.pixel_width), int(config.pixel_height)],
            "total": round(float(self.renderer.time), 3),
            "beats": self._dm_timeline,
            "overruns": self._dm_overruns,
            "layout": self._dm_layout,
            "measured": self._dm_measured,
            "unused_beats": [b for b in self._dm_beats if b not in self._dm_used],
        }
        (PROJECT / "timeline.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        super().tear_down()
