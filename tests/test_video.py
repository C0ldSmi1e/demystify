import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import SKILL, load, run_script

video = load("video")
doctor = load("doctor")


def quiet_init(project):
    """video.init prints what it wrote. The tests do not need that text."""
    with contextlib.redirect_stdout(io.StringIO()):
        return video.init(project)


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "demystify-out" / "demo"

    def ready(self):
        """A project with a storyboard, a matching narration, and scenes that are not the template."""
        quiet_init(self.project)
        beats = [{"id": "b01", "narration": "A short line.", "visual": "v"}]
        (self.project / "storyboard.json").write_text(json.dumps({"beats": beats}), encoding="utf-8")
        (self.project / "beats.json").write_text(json.dumps({
            "engine": "none", "voice": "", "beats": [{"id": "b01", "text": "A short line.", "duration": 2.0}],
        }), encoding="utf-8")
        (self.project / "scenes.py").write_text(
            'from scene_kit import *\n\n\nclass Video(Explainer):\n    def construct(self):\n'
            '        with self.beat("b01") as dur:\n            self.wait(dur)\n', encoding="utf-8")


class Init(Project):
    def test_creates_the_project_and_hides_the_output_folder_from_git(self):
        self.assertEqual(quiet_init(self.project), 0)
        for name in ("storyboard.json", "scenes.py", "scene_kit.py"):
            self.assertTrue((self.project / name).is_file(), name)
        self.assertEqual((self.project.parent / ".gitignore").read_text(encoding="utf-8"), "*\n")
        self.assertEqual((self.project / "scene_kit.py").read_bytes(), (SKILL / "assets" / "scene_kit.py").read_bytes())
        json.loads((self.project / "storyboard.json").read_text(encoding="utf-8"))

    def test_init_says_that_it_hides_the_output_folder(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            video.init(self.project)
        self.assertIn(".gitignore", out.getvalue())

    def test_does_not_overwrite_work(self):
        quiet_init(self.project)
        (self.project / "storyboard.json").write_text('{"beats": []}', encoding="utf-8")
        (self.project / "scenes.py").write_text("# mine\n", encoding="utf-8")
        quiet_init(self.project)
        self.assertEqual((self.project / "storyboard.json").read_text(encoding="utf-8"), '{"beats": []}')
        self.assertEqual((self.project / "scenes.py").read_text(encoding="utf-8"), "# mine\n")

    def test_template_scenes_are_valid_python(self):
        compile(video.SCENES, "scenes.py", "exec")
        json.loads(video.STORYBOARD)


class Guards(Project):
    def test_needs_narration_first(self):
        quiet_init(self.project)
        with self.assertRaises(video.NotReady) as caught:
            video.check_project(self.project)
        self.assertIn("narrate.py", str(caught.exception))

    def test_template_scenes_are_refused(self):
        self.ready()
        (self.project / "scenes.py").write_text(video.SCENES, encoding="utf-8")
        with self.assertRaises(video.NotReady) as caught:
            video.check_project(self.project)
        self.assertIn("EDIT", str(caught.exception))

    def test_storyboard_changed_after_narration(self):
        self.ready()
        changed = {"beats": [{"id": "b01", "narration": "A different line.", "visual": "v"}]}
        (self.project / "storyboard.json").write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(video.NotReady) as caught:
            video.check_project(self.project)
        self.assertIn("narrate.py", str(caught.exception))

    def test_subtitle_changed_after_narration(self):
        self.ready()
        changed = {"beats": [{"id": "b01", "narration": "A short line.", "subtitle": "A short line!", "visual": "v"}]}
        (self.project / "storyboard.json").write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(video.NotReady) as caught:
            video.check_project(self.project)
        self.assertIn("narrate.py", str(caught.exception))

    def test_ready_project_passes_and_gets_the_current_kit(self):
        self.ready()
        (self.project / "scene_kit.py").write_text("# old kit\n", encoding="utf-8")
        state = video.check_project(self.project)
        self.assertEqual(state["beats"]["engine"], "none")
        self.assertEqual((self.project / "scene_kit.py").read_bytes(), (SKILL / "assets" / "scene_kit.py").read_bytes())

    def test_command_line_exit_2_when_not_ready(self):
        proc = run_script("video", "draft", self.project)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("video.py init", proc.stderr)


class Reports(unittest.TestCase):
    def test_faults_are_sentences_a_person_can_act_on(self):
        timeline = {
            "overruns": [{"beat": "b03", "seconds": 2.7}],
            "layout": [{"beat": "b01", "kind": "text-outside-frame", "what": "A long line"},
                       {"beat": "b02", "kind": "text-overlap", "what": "First / Second", "at": 12.42},
                       {"beat": "b02", "kind": "text-too-small", "what": "A formula (size 12, smallest is 22)"}],
            "unused_beats": ["b04"],
        }
        found = video.faults(timeline)
        self.assertEqual(len(found), 5)
        self.assertIn("2.7 s longer", found[0])
        self.assertIn("leaves the frame", found[1])
        self.assertIn("b02 at 12.4 s: text overlaps", found[2])
        self.assertIn("too small", found[3])
        self.assertIn("no scene plays it", found[4])

    def test_frame_needs_a_draft_and_some_moments(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_script("video", "frame", tmp).returncode, 2)
            proc = run_script("video", "frame", tmp, "3.5")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("video.py draft", proc.stderr)

    def test_failure_report_names_error_line_and_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "scenes.py").write_text("a\nb\nformula = MathTex('x')\n", encoding="utf-8")
            output = "\n".join([
                "| /tmp/x/scenes.py:3 in construct |",
                "| subprocess.py:1955 in _execute_child |",
                "FileNotFoundError: [Errno 2] No such file or directory: 'latex'",
            ])
            text = video.explain_failure(output, project)
        self.assertIn("FileNotFoundError", text)
        self.assertIn("scenes.py line 3: formula = MathTex('x')", text)
        self.assertIn("needs LaTeX", text)

    def test_manimgl_name_gets_a_hint(self):
        text = video.explain_failure("NameError: name 'ShowCreation' is not defined", Path("."))
        self.assertIn("ManimGL", text)


class Doctor(unittest.TestCase):
    def test_report_shape(self):
        report = doctor.examine()
        self.assertTrue(report["ready"]["text"] and report["ready"]["diagram"] and report["ready"]["page"])
        names = [item["name"] for item in report["items"]]
        for name in ("browser", "uv", "cairo", "elevenlabs", "kokoro", "say"):
            self.assertIn(name, names)
        for item in report["items"]:
            if item["needed"] and not item["ok"] and item["name"] != "python":
                self.assertTrue(item["fix"], "a missing needed item must come with a fix: %s" % item["name"])
        self.assertIn("demystify doctor", doctor.render(report))

    def test_never_prints_the_key(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "super-secret-value"}):
            report = doctor.examine()
            self.assertNotIn("super-secret-value", json.dumps(report))
            self.assertNotIn("super-secret-value", doctor.render(report))

    def test_json_output(self):
        proc = run_script("doctor", "--json")
        self.assertIn(proc.returncode, (0, 1))
        self.assertIn("ready", json.loads(proc.stdout))


if __name__ == "__main__":
    unittest.main()
