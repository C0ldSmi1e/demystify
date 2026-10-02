"""Take frames out of a rendered video and measure it. video.py runs this file; do not run it yourself.

It runs inside the same temporary `uv` environment as Manim, which already contains PyAV and Pillow,
so the video step needs no system ffmpeg.

    python _frames_worker.py --video V.mp4 --timeline timeline.json --out review/ [--poster poster.png]

For each beat it writes two full-size frames: review/<beat>-mid.png (the middle of the beat) and
review/<beat>.png (the end of its narration). It also writes a contact sheet of all of them
(review/sheet.png) and prints one JSON object with what it measured.
With --at it writes one frame for each given second instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import av
from PIL import Image, ImageDraw, ImageFont

THUMB_WIDTH = 480
COLUMNS = 4
LABEL_HEIGHT = 30


def probe(path: Path) -> dict:
    info = {"video": None, "audio": None}
    with av.open(str(path)) as container:
        if container.streams.video:
            stream = container.streams.video[0]
            info["video"] = {
                "codec": stream.codec_context.name,
                "width": stream.codec_context.width,
                "height": stream.codec_context.height,
                "fps": round(float(stream.average_rate), 3) if stream.average_rate else None,
            }
        if container.duration:
            info["duration"] = round(container.duration / float(av.time_base), 3)
        if container.streams.audio:
            stream = container.streams.audio[0]
            peak = 0.0
            for frame in container.decode(stream):
                samples = frame.to_ndarray()
                top = float(abs(samples).max()) if samples.size else 0.0
                if samples.dtype.kind != "f":
                    top /= float(2 ** (8 * samples.dtype.itemsize - 1))
                peak = max(peak, top)
            info["audio"] = {"codec": stream.codec_context.name, "peak": round(peak, 4)}
    return info


def grab(path: Path, times: list) -> list:
    """Return the frame at each time (seconds, ascending). A time after the end gives the last frame."""
    images, index, last = [], 0, None
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        for frame in container.decode(stream):
            moment = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
            last = frame
            while index < len(times) and moment >= times[index] - 1e-3:
                images.append(frame.to_image())
                index += 1
            if index >= len(times):
                break
    while len(images) < len(times) and last is not None:
        images.append(last.to_image())
    return images


def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # an older Pillow
        return ImageFont.load_default()


def contact_sheet(images: list, labels: list) -> Image.Image:
    thumbs = []
    for image in images:
        height = int(image.height * THUMB_WIDTH / image.width)
        thumbs.append(image.resize((THUMB_WIDTH, height)))
    cell_h = thumbs[0].height + LABEL_HEIGHT
    rows = -(-len(thumbs) // COLUMNS)
    sheet = Image.new("RGB", (COLUMNS * THUMB_WIDTH, rows * cell_h), "#20242b")
    draw = ImageDraw.Draw(sheet)
    for index, (thumb, label) in enumerate(zip(thumbs, labels)):
        x, y = (index % COLUMNS) * THUMB_WIDTH, (index // COLUMNS) * cell_h
        draw.text((x + 8, y + 6), label, fill="#e6edf3", font=font(16))
        sheet.paste(thumb, (x, y + LABEL_HEIGHT))
        draw.rectangle([x, y + LABEL_HEIGHT, x + THUMB_WIDTH - 1, y + cell_h - 1], outline="#3a414b")
    return sheet


def end_of_narration(beat: dict) -> float:
    """The moment when the voice of a beat stops: everything that the beat adds is on the screen by then."""
    return max(beat["start"], min(beat["end"], beat["start"] + beat["narration"]) - 0.05)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--timeline", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--poster", default="")
    parser.add_argument("--poster-at", type=float, default=None, help="the second that the poster shows")
    parser.add_argument("--at", default="", help="comma-separated seconds: save one frame for each")
    args = parser.parse_args()

    video = Path(args.video)
    timeline = json.loads(Path(args.timeline).read_text(encoding="utf-8"))
    result = probe(video)
    beats = timeline.get("beats", [])

    if args.out and args.at:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        times = sorted(float(value) for value in args.at.split(",") if value.strip())
        result["stills"] = []
        for moment, image in zip(times, grab(video, times)):
            target = out / ("t%06.2f.png" % moment)
            image.save(str(target))
            result["stills"].append(str(target))
    elif args.out and beats:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for old in out.glob("*.png"):
            old.unlink()
        # Two moments for each beat: the middle, where things move, and the end of the narration.
        wanted = []
        for beat in beats:
            last = end_of_narration(beat)
            wanted.append((beat["id"], "mid", (beat["start"] + last) / 2.0))
            wanted.append((beat["id"], "end", last))
        order = sorted(range(len(wanted)), key=lambda i: wanted[i][2])
        frames = grab(video, [wanted[i][2] for i in order])
        images = [None] * len(wanted)
        for position, index in enumerate(order):
            images[index] = frames[position]
        stills = []
        for (beat_id, part, _moment), image in zip(wanted, images):
            target = out / ("%s.png" % beat_id if part == "end" else "%s-mid.png" % beat_id)
            image.save(str(target))
            if part == "end":
                stills.append(str(target))
        labels = ["%s %s  %.1f s" % (beat_id, part, moment) for beat_id, part, moment in wanted]
        sheet_path = out / "sheet.png"
        contact_sheet(images, labels).save(str(sheet_path))
        result["sheet"] = str(sheet_path)
        result["stills"] = stills

    if args.poster and beats:
        # The last picture holds the takeaway, so it is the poster unless the caller gives a different moment.
        moment = args.poster_at if args.poster_at is not None else max(0.0, timeline.get("total", 0.0) - 0.2)
        grab(video, [moment])[0].save(args.poster)
        result["poster"] = args.poster

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
