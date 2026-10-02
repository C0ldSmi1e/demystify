#!/usr/bin/env python3
"""Record the narration of a video: one audio file for each beat, and beats.json with the lengths.

The animation takes its timing from beats.json, so record the narration before you write the
scenes, and record it again after you change the words.

Usage:
    narrate.py PROJECT_DIR                 choose the best voice that is available
    narrate.py PROJECT_DIR --download      also allow the one-time download of the Kokoro voice (354 MB)
    narrate.py PROJECT_DIR --engine say    use one engine: elevenlabs, kokoro, say, or none

Voices, in the order of the automatic choice:
    elevenlabs   if ELEVENLABS_API_KEY is in the environment. A paid service: ask the user first.
    kokoro       a free voice that runs on this computer. Needs `uv` and a one-time download.
    say          the system voice of macOS. No download.
    none         no audio. The video is silent and has subtitles.

Other options:
    --voice NAME   kokoro: af_heart (default), am_michael, bf_emma, bm_george, ...
                   elevenlabs: a voice id.  say: a system voice, for example Samantha.
    --speed X      kokoro only: 1.0 is normal.
    --lang CODE    kokoro only: en-us (default), en-gb, ...

PROJECT_DIR contains storyboard.json. The script writes PROJECT_DIR/audio/ and PROJECT_DIR/beats.json.
Exit status: 0 done, 1 could not record, 2 the storyboard is not valid.

Standard library only. Python 3.8 or later.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path


sys.dont_write_bytecode = True  # do not leave __pycache__ in the skill folder

from _common import KOKORO, SOUNDFILE, cache_dir, find_python, find_uv, kokoro_cached, kokoro_files, run, system, uv_run
from check_text import split_sentences

SCRIPTS = Path(__file__).resolve().parent
ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/%s/with-timestamps?output_format=mp3_44100_128"
ELEVEN_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # "George", a stock voice
ELEVEN_MODEL = "eleven_multilingual_v2"
KOKORO_VOICE = "af_heart"
WORDS_PER_SECOND = 2.8
PAUSE = 0.16  # seconds of silence between two sentences of one beat
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class StoryboardError(Exception):
    pass


class EngineError(Exception):
    pass


def read_storyboard(project: Path) -> dict:
    path = project / "storyboard.json"
    if not path.is_file():
        raise StoryboardError("%s does not exist. Make the project first: video.py init %s" % (path, project))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise StoryboardError("%s is not valid JSON: %s" % (path, exc)) from exc
    beats = data.get("beats") if isinstance(data, dict) else None
    if not isinstance(beats, list) or not beats:
        raise StoryboardError("storyboard.json needs a list \"beats\" with one beat or more")
    seen, clean = set(), []
    for index, beat in enumerate(beats, 1):
        if not isinstance(beat, dict):
            raise StoryboardError("beat %d is not an object" % index)
        beat_id = str(beat.get("id", ""))
        text = " ".join(str(beat.get("narration") or beat.get("text") or "").split())
        if not ID_RE.match(beat_id):
            raise StoryboardError("beat %d needs an id of letters, digits, - or _ (for example \"b01\")" % index)
        if beat_id in seen:
            raise StoryboardError("the id %r is used two times" % beat_id)
        if not text:
            raise StoryboardError("beat %s has no narration" % beat_id)
        if re.search(r"\bEDIT\b", text):
            raise StoryboardError("beat %s still has the template text \"EDIT\": write the narration first" % beat_id)
        seen.add(beat_id)
        entry = {"id": beat_id, "text": text, "sentences": split_sentences(text) or [text]}
        subtitle = " ".join(str(beat.get("subtitle") or "").split())
        if subtitle:
            entry["subtitle"] = subtitle
        clean.append(entry)
    return {"title": data.get("title", ""), "beats": clean}


def estimate(text: str) -> float:
    return round(max(1.5, len(text.split()) / WORDS_PER_SECOND + 0.4), 3)


def estimate_sentences(sentences: list) -> list:
    """Timings for a beat with no audio: [(start, end)] for each sentence."""
    spans, clock = [], 0.0
    for sentence in sentences:
        length = max(0.8, len(sentence.split()) / WORDS_PER_SECOND + 0.2)
        spans.append((round(clock, 3), round(clock + length, 3)))
        clock += length + PAUSE
    return spans


def spans_from_alignment(text: str, sentences: list, starts: list, ends: list) -> list:
    """Find when each sentence starts and ends, from the time of each character."""
    if not starts or len(starts) != len(ends):
        return []
    spans, cursor = [], 0
    scale = len(starts) / float(max(1, len(text)))  # 1.0 when there is one time for each character
    for sentence in sentences:
        at = text.find(sentence, cursor)
        if at < 0:
            return []
        first = min(len(starts) - 1, int(at * scale))
        last = min(len(ends) - 1, int((at + len(sentence) - 1) * scale))
        spans.append((round(float(starts[first]), 3), round(float(ends[last]), 3)))
        cursor = at + len(sentence)
    return spans


def beat_key(engine: str, voice: str, speed: float, lang: str, text: str) -> str:
    raw = "|".join([engine, voice, "%.3f" % speed, lang, text])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_previous(project: Path) -> dict:
    try:
        data = json.loads((project / "beats.json").read_text(encoding="utf-8"))
        return {beat["id"]: beat for beat in data.get("beats", [])}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


# --------------------------------------------------------------------------- engines


def speak_elevenlabs(todo: list, all_beats: list, audio_dir: Path, voice: str) -> dict:
    """One request for each beat. Returns {id: (file name, seconds)}."""
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise EngineError("ELEVENLABS_API_KEY is not in the environment")
    model = os.environ.get("DEMYSTIFY_ELEVENLABS_MODEL", ELEVEN_MODEL)
    order = [beat["id"] for beat in all_beats]
    texts = {beat["id"]: beat["text"] for beat in all_beats}
    done = {}
    for beat in todo:
        position = order.index(beat["id"])
        body = {"text": beat["text"], "model_id": model}
        if position > 0:
            body["previous_text"] = texts[order[position - 1]]
        if position < len(order) - 1:
            body["next_text"] = texts[order[position + 1]]
        request = urllib.request.Request(
            ELEVEN_URL % voice,
            data=json.dumps(body).encode("utf-8"),
            headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise EngineError("ElevenLabs answered %s for beat %s: %s" % (exc.code, beat["id"], detail)) from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise EngineError("ElevenLabs request failed for beat %s: %s" % (beat["id"], exc)) from exc
        audio = base64.b64decode(payload.get("audio_base64") or "")
        if not audio:
            raise EngineError("ElevenLabs returned no audio for beat %s" % beat["id"])
        alignment = payload.get("alignment") or {}
        ends = alignment.get("character_end_times_seconds") or []
        seconds = max(float(ends[-1]) if ends else 0.0, len(audio) * 8 / 128000.0)
        name = beat["id"] + ".mp3"
        (audio_dir / name).write_bytes(audio)
        spans = spans_from_alignment(beat["text"], beat["sentences"],
                                     alignment.get("character_start_times_seconds") or [], ends)
        done[beat["id"]] = (name, round(seconds, 3), spans)
    return done


def download_kokoro() -> None:
    for item in kokoro_files():
        path = item["path"]
        if path.is_file() and path.stat().st_size == item["size"]:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        print("narrate: downloading %s (%d MB) ..." % (path.name, item["size"] // 1000000), flush=True)
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(item["url"], timeout=60) as response, open(str(part), "wb") as out:
                received, next_mark = 0, 0.25
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if received >= next_mark * item["size"]:
                        print("narrate:   %d%%" % int(next_mark * 100), flush=True)
                        next_mark += 0.25
        except (urllib.error.URLError, OSError) as exc:
            raise EngineError("the download of %s failed: %s" % (path.name, exc)) from exc
        if digest.hexdigest() != item["sha256"]:
            part.unlink()
            raise EngineError("the download of %s does not match its checksum: deleted it" % path.name)
        os.replace(str(part), str(path))


def speak_kokoro(todo: list, audio_dir: Path, voice: str, speed: float, lang: str, allow_download: bool) -> dict:
    uv = find_uv()
    if not uv:
        raise EngineError("Kokoro needs `uv`, which is not installed (see doctor.py)")
    if not kokoro_cached():
        if not allow_download:
            raise EngineError(
                "the Kokoro voice model is not on this computer. It is a one-time download of 354 MB to %s. "
                "Ask the user. If they agree, run this command again with --download" % (cache_dir() / "kokoro"))
        download_kokoro()
    model, voices = [str(item["path"]) for item in kokoro_files()]
    python, _found = find_python(uv)
    work = Path(tempfile.mkdtemp(prefix="demystify-narrate-"))
    try:
        jobs = [{"id": b["id"], "sentences": b["sentences"], "out": str(audio_dir / (b["id"] + ".wav"))} for b in todo]
        (work / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
        command = uv_run(uv, python, [KOKORO, SOUNDFILE], [
            "python", SCRIPTS / "_kokoro_worker.py", "--model", model, "--voices", voices,
            "--jobs", work / "jobs.json", "--result", work / "result.json",
            "--voice", voice, "--speed", speed, "--lang", lang, "--cache", cache_dir(), "--pause", PAUSE,
        ])
        process = run(command, timeout=1800)
        if process.returncode != 0 or not (work / "result.json").exists():
            tail = "\n".join((process.stderr or process.stdout or "").strip().splitlines()[-6:])
            raise EngineError("Kokoro did not finish:\n%s" % tail)
        results = json.loads((work / "result.json").read_text(encoding="utf-8"))
        return {item["id"]: (item["id"] + ".wav", item["duration"], [tuple(span) for span in item["spans"]])
                for item in results}
    finally:
        shutil.rmtree(str(work), ignore_errors=True)


def say_voice(requested: str) -> str:
    if requested:
        return requested
    listing = run(["say", "-v", "?"], timeout=20).stdout or ""
    names = {line.split("  ")[0].strip() for line in listing.splitlines() if "en_" in line}
    for name in ("Samantha", "Alex", "Daniel", "Karen"):
        if name in names:
            return name
    return ""


def speak_say(todo: list, audio_dir: Path, voice: str) -> dict:
    if system() != "macos" or not shutil.which("say"):
        raise EngineError("the `say` voice exists only on macOS")
    voice = say_voice(voice)
    work = Path(tempfile.mkdtemp(prefix="demystify-say-"))
    done = {}
    try:
        for beat in todo:
            frames, spans, params, clock = [], [], None, 0.0
            for index, sentence in enumerate(beat["sentences"]):
                part = work / ("%s-%d.wav" % (beat["id"], index))
                words = sentence if not sentence.startswith("-") else " " + sentence
                command = ["say"] + (["-v", voice] if voice else []) + [
                    "-o", str(part), "--data-format=LEI16@22050", words]
                process = subprocess.run(command, capture_output=True, text=True)
                if process.returncode != 0:
                    raise EngineError("say failed for beat %s: %s" % (beat["id"], process.stderr.strip()[:200]))
                with wave.open(str(part), "rb") as handle:
                    params = handle.getparams()
                    data = handle.readframes(handle.getnframes())
                    seconds = handle.getnframes() / float(handle.getframerate())
                if frames:
                    silence = int(PAUSE * params.framerate) * params.sampwidth * params.nchannels
                    frames.append(b"\x00" * silence)
                    clock += PAUSE
                frames.append(data)
                spans.append((round(clock, 3), round(clock + seconds, 3)))
                clock += seconds
            name = beat["id"] + ".wav"
            with wave.open(str(audio_dir / name), "wb") as handle:
                handle.setparams(params)
                handle.writeframes(b"".join(frames))
            done[beat["id"]] = (name, round(clock, 3), spans)
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    return done


# --------------------------------------------------------------------------- choice


def available(engine: str, allow_download: bool):
    """Return (usable, reason)."""
    if engine == "elevenlabs":
        return (True, "") if os.environ.get("ELEVENLABS_API_KEY") else (False, "no ELEVENLABS_API_KEY in the environment")
    if engine == "kokoro":
        if not find_uv():
            return False, "`uv` is not installed"
        if kokoro_cached() or allow_download:
            return True, ""
        return False, "the voice model is not downloaded (354 MB, one time): ask the user, then add --download"
    if engine == "say":
        return (True, "") if system() == "macos" and shutil.which("say") else (False, "not macOS")
    return True, ""


def narrate(project: Path, engine: str, voice: str, speed: float, lang: str, allow_download: bool) -> dict:
    board = read_storyboard(project)
    beats = board["beats"]
    audio_dir = project / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    notes = []

    candidates = ["elevenlabs", "kokoro", "say", "none"] if engine == "auto" else [engine]
    previous = load_previous(project)
    for candidate in candidates:
        usable, reason = available(candidate, allow_download)
        if not usable:
            if engine != "auto":
                raise EngineError("%s is not available: %s" % (candidate, reason))
            notes.append("%s was not used: %s" % (candidate, reason))
            continue
        used_voice = voice or {"elevenlabs": os.environ.get("DEMYSTIFY_ELEVENLABS_VOICE", ELEVEN_VOICE),
                               "kokoro": KOKORO_VOICE}.get(candidate, "")
        if candidate == "say":
            used_voice = say_voice(voice)
        keys = {b["id"]: beat_key(candidate, used_voice, speed, lang, b["text"]) for b in beats}
        todo = []
        for beat in beats:
            old = previous.get(beat["id"])
            reusable = (old and old.get("key") == keys[beat["id"]] and old.get("audio")
                        and (project / old["audio"]).is_file())
            if not reusable:
                todo.append(beat)
        try:
            if candidate == "elevenlabs":
                fresh = speak_elevenlabs(todo, beats, audio_dir, used_voice)
            elif candidate == "kokoro":
                fresh = speak_kokoro(todo, audio_dir, used_voice, speed, lang, allow_download) if todo else {}
            elif candidate == "say":
                fresh = speak_say(todo, audio_dir, used_voice)
            else:
                fresh = {}
        except EngineError as exc:
            if engine != "auto":
                raise
            notes.append("%s failed: %s" % (candidate, exc))
            continue

        result = []
        for beat in beats:
            entry = {"id": beat["id"], "text": beat["text"], "key": keys[beat["id"]]}
            old = previous.get(beat["id"]) or {}
            if candidate == "none":
                spans = estimate_sentences(beat["sentences"])
                entry["duration"] = spans[-1][1]
            elif beat["id"] in fresh:
                name, seconds, spans = fresh[beat["id"]]
                entry["audio"] = "audio/" + name
                entry["duration"] = seconds
            else:
                entry["audio"] = old["audio"]
                entry["duration"] = old["duration"]
                spans = [(item["start"], item["end"]) for item in old.get("sentences", [])]
            if len(spans) != len(beat["sentences"]):  # no times for the sentences: one sentence for the beat
                spans = [(0.0, entry["duration"])]
                texts = [beat["text"]]
            else:
                texts = beat["sentences"]
            # "text" is what the voice says. "subtitle" is the written form, where it is different.
            entry["sentences"] = [{"text": text, "start": start, "end": end} for text, (start, end) in zip(texts, spans)]
            if beat.get("subtitle"):
                entry["written"] = beat["subtitle"]  # video.py compares it with the storyboard
                written = split_sentences(beat["subtitle"])
                if len(written) == len(texts):
                    for sentence, form in zip(entry["sentences"], written):
                        if form != sentence["text"]:
                            sentence["subtitle"] = form
                else:
                    entry["subtitle"] = beat["subtitle"]
                    notes.append("beat %s: the subtitle has %d sentence%s and the narration has %d, so the full "
                                 "subtitle shows during the full beat. Give them the same number of sentences."
                                 % (beat["id"], len(written), "" if len(written) == 1 else "s", len(texts)))
            result.append(entry)
        total = round(sum(b["duration"] for b in result), 3)
        data = {"engine": candidate, "voice": used_voice, "speed": speed, "lang": lang,
                "total": total, "beats": result}
        (project / "beats.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        data["notes"] = notes
        data["recorded"] = len(todo) if candidate != "none" else 0
        return data
    raise EngineError("no voice is available")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record the narration of a demystify video.")
    parser.add_argument("project", help="the video folder that contains storyboard.json")
    parser.add_argument("--engine", choices=("auto", "elevenlabs", "kokoro", "say", "none"), default="auto")
    parser.add_argument("--download", action="store_true", help="allow the one-time download of the Kokoro voice (354 MB)")
    parser.add_argument("--voice", default="")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--lang", default="en-us")
    args = parser.parse_args(argv)

    project = Path(args.project)
    try:
        data = narrate(project, args.engine, args.voice, args.speed, args.lang, args.download)
    except StoryboardError as exc:
        print("narrate: %s" % exc, file=sys.stderr)
        return 2
    except EngineError as exc:
        print("narrate: %s" % exc, file=sys.stderr)
        return 1

    voice = data["engine"] + ("/" + data["voice"] if data["voice"] else "")
    print("narrate: %d beats, %.1f s of narration, voice %s (%d recorded now, %d reused)" % (
        len(data["beats"]), data["total"], voice, data["recorded"], len(data["beats"]) - data["recorded"]
        if data["engine"] != "none" else 0))
    for beat in data["beats"]:
        print("  %-8s %5.1f s  %s" % (beat["id"], beat["duration"], beat["text"][:70]))
    print("  wrote %s" % (project / "beats.json"))
    for note in data["notes"]:
        print("NOTE: %s" % note)
    if data["engine"] == "none":
        print("NOTE: no voice was used. The lengths are estimates, and the video will be silent with subtitles.")
    if data["engine"] == "say":
        print("NOTE: this is the system voice. Kokoro sounds better and is free: ask the user about the download.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
