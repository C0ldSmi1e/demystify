# One file, explained four ways

Everything in [`token-bucket/`](token-bucket/) explains [`token_bucket.py`](token_bucket.py), a 45-line rate limiter.

Each result came from one request to Claude Code with the demystify plugin loaded. Nobody edited a result by hand.

| Request | Result | Time | Cost |
| --- | --- | --- | --- |
| `/demystify text: how examples/token_bucket.py limits requests` | [text.md](token-bucket/text.md) | 39 s | $0.25 |
| `/demystify diagram: how examples/token_bucket.py limits requests` | [diagram.svg](token-bucket/diagram.svg) | 3.5 min | $0.84 |
| `/demystify page: how examples/token_bucket.py limits requests` | [page.html](token-bucket/page.html) | 5 min | $1.23 |
| `/demystify video: how examples/token_bucket.py limits requests` | [video.mp4](token-bucket/video.mp4), [video.srt](token-bucket/video.srt) | 10 min | $1.71 |

Made on 2 October 2026 with Claude Code 2.1.287 and Claude Opus 5.5. Cost is at API prices. The voice in the video is Kokoro, which runs on the computer and is free.

The other files are previews for the README. `diagram.png` and `page.png` are screenshots, `poster.png` is the last frame of the video, and `video.gif` is a small silent copy of it with the subtitles drawn in.

To see the page work, download `page.html` and open it. GitHub shows its source, not the page.
