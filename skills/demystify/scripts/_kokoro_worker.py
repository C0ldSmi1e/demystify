"""Speak beats with the Kokoro voice model. narrate.py runs this file; do not run it yourself.

It runs inside a temporary `uv` environment that has kokoro-onnx and soundfile:

    uv run --no-project --python 3.12 --with kokoro-onnx==0.6.1 --with soundfile \
        python _kokoro_worker.py --model M --voices V --jobs jobs.json --result result.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path


def espeak_config(cache: Path):
    """Work around a limit in espeak-ng: it keeps the path of its data folder in 160 characters.

    The data folder is inside the uv cache, and that path is often longer. Then espeak-ng fails
    with "phontab: No such file or directory". A symbolic link does not help, so this function
    copies the folder (19 MB) to a short path, one time for each version.
    """
    import espeakng_loader
    from kokoro_onnx import EspeakConfig

    data = Path(espeakng_loader.get_data_path())
    if len(str(data)) < 150:
        return None
    try:
        from importlib.metadata import version

        tag = version("espeakng-loader")
    except Exception:  # noqa: BLE001 - the version is only a name for the copy
        tag = "copy"
    for folder in (cache / ("espeak-ng-data-" + tag), Path(tempfile.gettempdir()) / ("demystify-espeak-" + tag)):
        if len(str(folder)) >= 150:
            continue
        if not (folder / "phontab").exists():
            folder.parent.mkdir(parents=True, exist_ok=True)
            if folder.exists():
                shutil.rmtree(str(folder))
            shutil.copytree(str(data), str(folder))
        return EspeakConfig(lib_path=espeakng_loader.get_library_path(), data_path=str(folder))
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--voices", required=True)
    parser.add_argument("--jobs", required=True, help="JSON list of {id, sentences, out}")
    parser.add_argument("--result", required=True)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--lang", default="en-us")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--pause", type=float, default=0.16, help="seconds of silence between two sentences")
    parser.add_argument("--list-voices", action="store_true")
    args = parser.parse_args()

    import soundfile
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(args.model, args.voices, espeak_config=espeak_config(Path(args.cache)))
    if args.list_voices:
        print("\n".join(sorted(kokoro.get_voices())))
        return 0
    voices = set(kokoro.get_voices())
    if args.voice not in voices:
        print("kokoro: there is no voice %r. Some voices: %s" % (args.voice, ", ".join(sorted(voices)[:12])), file=sys.stderr)
        return 3

    import numpy

    # Speak each sentence by itself, so that the caller knows when each one starts.
    spoken, rate = [], 24000
    for job in json.loads(Path(args.jobs).read_text(encoding="utf-8")):
        parts = []
        for sentence in job["sentences"]:
            samples, rate = kokoro.create(sentence, voice=args.voice, speed=args.speed, lang=args.lang)
            parts.append(numpy.asarray(samples, dtype=numpy.float32))
        spoken.append((job, parts))

    pause = numpy.zeros(int(args.pause * rate), dtype=numpy.float32)

    results = []
    for job, parts in spoken:
        # The same loudness for each beat (about -20 dB), so that a beat recorded later sounds like the others.
        speech = numpy.concatenate(parts) if parts else numpy.zeros(1, dtype=numpy.float32)
        level = float(numpy.sqrt(numpy.mean(speech ** 2))) or 1.0
        peak = float(numpy.abs(speech).max()) or 1.0
        gain = min(0.1 / level, 0.95 / peak)
        pieces, spans, clock = [], [], 0.0
        for part in parts:
            if pieces:
                pieces.append(pause)
                clock += len(pause) / float(rate)
            pieces.append(part * gain)
            spans.append([round(clock, 3), round(clock + len(part) / float(rate), 3)])
            clock += len(part) / float(rate)
        soundfile.write(job["out"], numpy.concatenate(pieces), rate)
        results.append({"id": job["id"], "duration": round(clock, 3), "spans": spans})
    Path(args.result).write_text(json.dumps(results), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
