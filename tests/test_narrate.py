import base64
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from helpers import load, run_script

narrate = load("narrate")

BEATS = [
    {"id": "b01", "narration": "A server must protect itself.", "visual": "a box"},
    {"id": "b02", "narration": "A token bucket does this.", "visual": "a bucket"},
    {"id": "b03", "narration": "So bursts are allowed.", "visual": "text"},
]


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "demo"
        self.project.mkdir()

    def write(self, beats=None, raw=None):
        text = raw if raw is not None else json.dumps({"title": "t", "beats": BEATS if beats is None else beats})
        (self.project / "storyboard.json").write_text(text, encoding="utf-8")


class Storyboard(Project):
    def test_reads_ids_and_narration(self):
        self.write()
        board = narrate.read_storyboard(self.project)
        self.assertEqual([b["id"] for b in board["beats"]], ["b01", "b02", "b03"])
        self.assertEqual(board["beats"][0]["text"], "A server must protect itself.")

    def test_rejects_what_cannot_be_recorded(self):
        cases = {
            "missing file": None,
            "not JSON": "{nope",
            "no beats": json.dumps({"beats": []}),
            "bad id": json.dumps({"beats": [{"id": "b 1", "narration": "x"}]}),
            "same id twice": json.dumps({"beats": [{"id": "a", "narration": "x"}, {"id": "a", "narration": "y"}]}),
            "empty narration": json.dumps({"beats": [{"id": "a", "narration": "  "}]}),
            "template text": json.dumps({"beats": [{"id": "a", "narration": "EDIT: the question."}]}),
        }
        for label, raw in cases.items():
            with self.subTest(label):
                if raw is None:
                    (self.project / "storyboard.json").unlink() if (self.project / "storyboard.json").exists() else None
                else:
                    self.write(raw=raw)
                with self.assertRaises(narrate.StoryboardError):
                    narrate.read_storyboard(self.project)

    def test_command_line_exit_2_for_a_bad_storyboard(self):
        self.write(raw=json.dumps({"beats": [{"id": "a", "narration": "EDIT"}]}))
        self.assertEqual(run_script("narrate", self.project, "--engine", "none").returncode, 2)


class Sentences(Project):
    def test_each_sentence_gets_its_own_time(self):
        self.write(beats=[{"id": "b01", "narration": "The bucket is full. A request takes one token.", "visual": "v"}])
        narrate.narrate(self.project, "none", "", 1.0, "en-us", False)
        beat = json.loads((self.project / "beats.json").read_text(encoding="utf-8"))["beats"][0]
        self.assertEqual([s["text"] for s in beat["sentences"]], ["The bucket is full.", "A request takes one token."])
        first, second = beat["sentences"]
        self.assertEqual(first["start"], 0.0)
        self.assertGreater(second["start"], first["end"])
        self.assertEqual(beat["duration"], second["end"])

    def test_subtitle_can_differ_from_what_the_voice_says(self):
        self.write(beats=[{"id": "b01", "narration": "The server answers four twenty-nine. The client waits.",
                           "subtitle": "The server answers 429. The client waits.", "visual": "v"}])
        narrate.narrate(self.project, "none", "", 1.0, "en-us", False)
        beat = json.loads((self.project / "beats.json").read_text(encoding="utf-8"))["beats"][0]
        self.assertEqual(beat["text"], "The server answers four twenty-nine. The client waits.")
        self.assertEqual([s["text"] for s in beat["sentences"]],
                         ["The server answers four twenty-nine.", "The client waits."])
        self.assertEqual([s.get("subtitle") for s in beat["sentences"]], ["The server answers 429.", None])
        self.assertNotIn("subtitle", beat)

    def test_subtitle_with_a_different_number_of_sentences_is_one_cue(self):
        self.write(beats=[{"id": "b01", "narration": "One. Two. Three.", "subtitle": "One, two, three.", "visual": "v"}])
        data = narrate.narrate(self.project, "none", "", 1.0, "en-us", False)
        beat = json.loads((self.project / "beats.json").read_text(encoding="utf-8"))["beats"][0]
        self.assertEqual(beat["subtitle"], "One, two, three.")
        self.assertEqual([s["text"] for s in beat["sentences"]], ["One.", "Two.", "Three."])  # the times stay
        self.assertTrue(any("b01" in note and "same number of sentences" in note for note in data["notes"]))

    def test_sentence_times_from_character_times(self):
        text = "Hi there. Bye now."
        starts = [i * 0.1 for i in range(len(text))]
        ends = [i * 0.1 + 0.1 for i in range(len(text))]
        spans = narrate.spans_from_alignment(text, ["Hi there.", "Bye now."], starts, ends)
        self.assertEqual(spans, [(0.0, 0.9), (1.0, 1.8)])
        self.assertEqual(narrate.spans_from_alignment(text, ["Hi there.", "Bye now."], [], []), [])


class NoVoice(Project):
    def test_estimates_lengths_and_writes_beats(self):
        self.write()
        data = narrate.narrate(self.project, "none", "", 1.0, "en-us", False)
        saved = json.loads((self.project / "beats.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["engine"], "none")
        self.assertEqual([b["id"] for b in saved["beats"]], ["b01", "b02", "b03"])
        self.assertTrue(all(b["duration"] >= 1.5 and "audio" not in b for b in saved["beats"]))
        self.assertAlmostEqual(saved["total"], sum(b["duration"] for b in saved["beats"]), places=2)
        self.assertEqual(data["recorded"], 0)

    def test_longer_text_gets_a_longer_estimate(self):
        self.assertGreater(narrate.estimate("one two three four five six seven eight nine ten"), narrate.estimate("one two"))


class Choice(Project):
    def test_forced_engine_that_is_missing_is_an_error(self):
        self.write()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            with self.assertRaises(narrate.EngineError):
                narrate.narrate(self.project, "elevenlabs", "", 1.0, "en-us", False)

    def test_auto_falls_to_no_voice_and_says_why(self):
        self.write()
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(narrate, "find_uv", return_value=None), \
                mock.patch.object(narrate, "system", return_value="linux"):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            data = narrate.narrate(self.project, "auto", "", 1.0, "en-us", False)
        self.assertEqual(data["engine"], "none")
        self.assertEqual(len(data["notes"]), 3)

    def test_kokoro_is_not_downloaded_without_permission(self):
        with mock.patch.object(narrate, "find_uv", return_value="/usr/bin/uv"), \
                mock.patch.object(narrate, "kokoro_cached", return_value=False):
            usable, reason = narrate.available("kokoro", allow_download=False)
            self.assertFalse(usable)
            self.assertIn("--download", reason)
            self.assertTrue(narrate.available("kokoro", allow_download=True)[0])

    def test_key_changes_with_voice_and_text(self):
        base = narrate.beat_key("kokoro", "af_heart", 1.0, "en-us", "hello")
        self.assertEqual(base, narrate.beat_key("kokoro", "af_heart", 1.0, "en-us", "hello"))
        self.assertNotEqual(base, narrate.beat_key("kokoro", "am_michael", 1.0, "en-us", "hello"))
        self.assertNotEqual(base, narrate.beat_key("kokoro", "af_heart", 1.0, "en-us", "hello!"))


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ElevenLabs(Project):
    """The request and the handling of the answer, with the network replaced. No real call is made."""

    def reply(self, seconds=2.0, audio=b"ID3" + b"\x00" * 1000):
        payload = {"audio_base64": base64.b64encode(audio).decode(),
                   "alignment": {"character_start_times_seconds": [0.0, 0.5],
                                 "character_end_times_seconds": [0.5, seconds]}}
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    def test_sends_key_in_header_and_neighbour_text(self):
        self.write()
        requests = []

        def fake(request, timeout=0):
            requests.append(request)
            return self.reply()

        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret-key"}), \
                mock.patch.object(narrate.urllib.request, "urlopen", fake):
            data = narrate.narrate(self.project, "elevenlabs", "", 1.0, "en-us", False)

        self.assertEqual(data["engine"], "elevenlabs")
        self.assertEqual(len(requests), 3)
        first, second = requests[0], requests[1]
        self.assertEqual(first.get_header("Xi-api-key"), "secret-key")
        self.assertIn("/with-timestamps", first.full_url)
        self.assertNotIn("secret-key", first.full_url)
        body = json.loads(second.data.decode("utf-8"))
        self.assertEqual(body["text"], "A token bucket does this.")
        self.assertEqual(body["previous_text"], "A server must protect itself.")
        self.assertEqual(body["next_text"], "So bursts are allowed.")
        saved = json.loads((self.project / "beats.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["beats"][0]["audio"], "audio/b01.mp3")
        self.assertEqual(saved["beats"][0]["duration"], 2.0)
        self.assertTrue((self.project / "audio" / "b01.mp3").read_bytes().startswith(b"ID3"))
        self.assertNotIn("secret-key", (self.project / "beats.json").read_text(encoding="utf-8"))

    def test_second_run_records_only_changed_beats(self):
        self.write()
        calls = []

        def fake(request, timeout=0):
            calls.append(json.loads(request.data.decode("utf-8"))["text"])
            return self.reply()

        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"}), \
                mock.patch.object(narrate.urllib.request, "urlopen", fake):
            narrate.narrate(self.project, "elevenlabs", "", 1.0, "en-us", False)
            changed = [dict(b) for b in BEATS]
            changed[1]["narration"] = "A token bucket does this job."
            self.write(beats=changed)
            data = narrate.narrate(self.project, "elevenlabs", "", 1.0, "en-us", False)
        self.assertEqual(calls[3:], ["A token bucket does this job."])
        self.assertEqual(data["recorded"], 1)

    def test_service_error_is_reported_without_the_key(self):
        self.write()

        def fake(request, timeout=0):
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"bad key"}'))

        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret-key"}), \
                mock.patch.object(narrate.urllib.request, "urlopen", fake):
            with self.assertRaises(narrate.EngineError) as caught:
                narrate.narrate(self.project, "elevenlabs", "", 1.0, "en-us", False)
        self.assertIn("401", str(caught.exception))
        self.assertNotIn("secret-key", str(caught.exception))

    def test_auto_uses_the_next_voice_when_the_service_fails(self):
        self.write()

        def fake(request, timeout=0):
            raise urllib.error.URLError("no network")

        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"}), \
                mock.patch.object(narrate.urllib.request, "urlopen", fake), \
                mock.patch.object(narrate, "find_uv", return_value=None), \
                mock.patch.object(narrate, "system", return_value="linux"):
            data = narrate.narrate(self.project, "auto", "", 1.0, "en-us", False)
        self.assertEqual(data["engine"], "none")
        self.assertTrue(any("elevenlabs failed" in note for note in data["notes"]))


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("say"), "the say voice exists only on macOS")
class SystemVoice(Project):
    def test_records_a_wav_and_measures_it(self):
        self.write(beats=BEATS[:1])
        data = narrate.narrate(self.project, "say", "", 1.0, "en-us", False)
        beat = data["beats"][0]
        self.assertEqual(beat["audio"], "audio/b01.wav")
        self.assertGreater(beat["duration"], 0.5)
        self.assertGreater((self.project / "audio" / "b01.wav").stat().st_size, 10000)


if __name__ == "__main__":
    unittest.main()
