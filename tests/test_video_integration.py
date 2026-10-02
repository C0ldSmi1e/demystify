"""Render real videos. Slow, and it downloads Manim into the uv cache the first time.

Run with:  DEMYSTIFY_SLOW_TESTS=1 python3 -m unittest discover -s tests -p 'test_video_integration.py'
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import load, run_script

common = load("_common")

WANTED = os.environ.get("DEMYSTIFY_SLOW_TESTS") == "1"
READY = bool(common.find_uv()) and (common.system() == "windows" or common.pkg_config("cairo")[0])

STORYBOARD = {"title": "Test", "beats": [
    {"id": "b01", "narration": "This is the first beat of the test.", "visual": "a title"},
    {"id": "b02", "narration": "This is the second beat.", "subtitle": "This is beat 2.", "visual": "a circle"},
    {"id": "b03", "narration": "This is the last beat.", "visual": "two labels"},
]}

GOOD_SCENES = '''"""A small test video."""

from scene_kit import *


class Video(Explainer):
    def construct(self):
        title = T("A test video", size=TITLE).to_edge(UP, buff=0.8)
        with self.beat("b01") as dur:
            assert 0.0 < dur.at("first beat") < dur.at("test") < dur
            self.wait_until(dur.at("first beat"))
            self.play(Write(title), run_time=0.8)
        circle = Circle(color=BLUE)
        level = ValueTracker(1.0)
        count = always_redraw(lambda: M("%d" % level.get_value(), size=SMALL).next_to(circle, DOWN, buff=0.4))
        with self.beat("b02") as dur:
            self.play(Create(circle), run_time=min(1.0, dur))
            self.add(count)
            self.play(level.animate.set_value(5.0), run_time=0.5)
        left = T("left").next_to(circle, LEFT, buff=0.6)
        right = M("right").next_to(circle, RIGHT, buff=0.6)
        with self.beat("b03") as dur:
            self.play(FadeIn(left), FadeIn(right), run_time=min(1.0, dur))
        self.clear_scene()  # also stops the updater of `count`
        assert not self.mobjects
'''

FAULTY_SCENES = '''"""Faults on purpose."""

from scene_kit import *


class Video(Explainer):
    def construct(self):
        wide = T("This line of text is much too long to stay inside the frame of the video at this size", size=HEAD)
        early = T("Alpha one").to_edge(UP)
        on_top = T("Alpha two").move_to(early)
        tiny = T("tiny", size=14).to_edge(DOWN)
        with self.beat("b01") as dur:
            self.play(FadeIn(early), FadeIn(on_top), run_time=0.3)  # text on text, gone before the beat ends
            self.play(FadeOut(early), FadeOut(on_top), run_time=0.3)
            self.play(FadeIn(wide), FadeIn(tiny), run_time=1.0)
        self.clear_scene()
        first = T("First label")
        second = T("Second label").move_to(first).shift(RIGHT * 0.3 + DOWN * 0.1)
        with self.beat("b02") as dur:
            self.play(FadeIn(first), FadeIn(second), run_time=dur + 3.0)
'''


@unittest.skipUnless(WANTED and READY, "set DEMYSTIFY_SLOW_TESTS=1 on a computer where doctor.py says that video is ready")
class RenderVideo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "demystify-out" / "test"
        self.assertEqual(run_script("video", "init", self.project).returncode, 0)
        (self.project / "storyboard.json").write_text(json.dumps(STORYBOARD), encoding="utf-8")

    def narrate(self, engine):
        proc = run_script("narrate", self.project, "--engine", engine, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_draft_measures_the_faults(self):
        self.narrate("none")
        (self.project / "scenes.py").write_text(FAULTY_SCENES, encoding="utf-8")
        proc = run_script("video", "draft", self.project, timeout=1800)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertRegex(proc.stdout, r"b01 at [\d.]+ s: text leaves the frame")
        self.assertRegex(proc.stdout, r"b01 at 0\.3 s: text overlaps other text: Alpha one / Alpha two")
        self.assertRegex(proc.stdout, r"b01 at [\d.]+ s: text is too small to read: tiny \(size 14, smallest is 22\)")
        self.assertRegex(proc.stdout, r"b02 at [\d.]+ s: text overlaps other text: First label / Second label")
        self.assertIn("b02: the animation is", proc.stdout)
        self.assertIn("b03: the narration was recorded, but no scene plays it", proc.stdout)
        self.assertTrue((self.project / "review" / "sheet.png").is_file())
        self.assertTrue((self.project / "review" / "b01.png").is_file())

    def test_final_without_voice_has_subtitles(self):
        self.narrate("none")
        (self.project / "scenes.py").write_text(GOOD_SCENES, encoding="utf-8")
        draft = run_script("video", "draft", self.project, timeout=1800)
        self.assertEqual(draft.returncode, 0, draft.stdout + draft.stderr)
        self.assertIn("Measured faults: none", draft.stdout)
        from_draft = run_script("video", "frame", self.project, "1.0", timeout=600)
        self.assertIn("from the last draft", from_draft.stdout)
        final = run_script("video", "final", self.project, "--poster", "1.5", timeout=1800)
        self.assertEqual(final.returncode, 0, final.stdout + final.stderr)
        self.assertIn("1920x1080", final.stdout)
        self.assertIn("no audio (subtitles only)", final.stdout)
        self.assertIn("the picture at 1.5 s", final.stdout)
        self.assertGreater((self.project / "video.mp4").stat().st_size, 10000)
        subtitles = (self.project / "video.srt").read_text(encoding="utf-8")
        self.assertIn("This is the first beat of the test.", subtitles)
        self.assertIn("This is beat 2.", subtitles)  # the written form, not what the voice says
        self.assertNotIn("second beat", subtitles)
        self.assertTrue((self.project / "poster.png").read_bytes().startswith(b"\x89PNG"))
        from_final = run_script("video", "frame", self.project, "1.0", "2.5", timeout=600)
        self.assertEqual(from_final.returncode, 0, from_final.stdout + from_final.stderr)
        self.assertIn("from the final video", from_final.stdout)
        self.assertTrue((self.project / "review" / "t002.50.png").read_bytes().startswith(b"\x89PNG"))

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("say"), "the say voice exists only on macOS")
    def test_final_with_a_voice_has_audio_that_is_not_silent(self):
        self.narrate("say")
        (self.project / "scenes.py").write_text(GOOD_SCENES, encoding="utf-8")
        final = run_script("video", "final", self.project, timeout=1800)
        self.assertEqual(final.returncode, 0, final.stdout + final.stderr)
        self.assertIn("voice say", final.stdout)
        self.assertIn("audio that is not silent", final.stdout)

    def test_changed_storyboard_needs_new_narration(self):
        self.narrate("none")
        (self.project / "scenes.py").write_text(GOOD_SCENES, encoding="utf-8")
        changed = json.loads(json.dumps(STORYBOARD))
        changed["beats"][0]["narration"] = "These words are new."
        (self.project / "storyboard.json").write_text(json.dumps(changed), encoding="utf-8")
        proc = run_script("video", "draft", self.project, timeout=600)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("narrate.py", proc.stderr)


if __name__ == "__main__":
    unittest.main()
