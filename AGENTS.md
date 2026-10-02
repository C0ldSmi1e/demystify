# Guide for agents

You are an AI agent working with this repository, either because a user asked you to install the skill or because you are changing it. Read this file first.

## If a user asked you to install it

1. Find out which agent you are running in. If you are not sure, ask the user.
2. Open [INSTALL.md](INSTALL.md) and use the section for that agent.
3. Show the user the commands before you run them. Installing a skill changes their setup, so it is their call.
4. Afterwards, tell them how to use it: `/demystify` and then what they want explained (`$demystify` in Codex).

Do not run the fixes that `scripts/doctor.py` prints unless the user says yes. The same goes for the 354 MB voice download.

## Where things are

| Path | What it is |
| --- | --- |
| `skills/demystify/SKILL.md` | The skill. A short router: read the request, pick a format, load one reference. |
| `skills/demystify/references/` | One file for each format: `text.md`, `diagram.md`, `page.md`, `video.md`. |
| `skills/demystify/assets/` | Starting points: `sheet.svg` (diagram), `page.html` (page), `scene_kit.py` (video). |
| `skills/demystify/scripts/` | The checks and the video pipeline. Standard library only, Python 3.8+. |
| `.claude-plugin/` | Plugin and marketplace manifests. Claude Code, Codex and Cowork read these. |
| `gemini-extension.json` | Manifest for Gemini CLI. |
| `examples/` | One subject, `token_bucket.py`, explained four ways. The skill made everything in `examples/token-bucket/`. |
| `evals/` | Prompts and graders for `claude plugin eval`. |
| `tests/` | Unit tests. `tests/test_package.py` holds the rules below as tests. |

## Rules for changing the skill

One folder has to work in every agent, so these hold:

- **Front matter**: only `name`, `description`, `license`, `metadata`. Other keys break uploads and validators elsewhere.
- **No placeholders in SKILL.md**: no `$ARGUMENTS`, `$1`, `` !`command` `` or `@file`. Only some agents replace them; the rest show them as literal text.
- **Paths**: no agent changes into the skill folder. Scripts are called as `python3 SKILL_DIR/scripts/x.py`, never by relying on the executable bit.
- **Size**: SKILL.md stays under 8,000 bytes. Detail belongs in `references/`.
- **Scripts**: standard library only, valid Python 3.8. Anything heavier runs through `uv run --with` at a pinned version.
- **No surprises**: no silent installs, no downloads without a yes from the user, no API key written anywhere.
- **Files**: no `metadata.json`, no symlinks in the skill folder, no top-level `bin/`.
- **Versions**: `plugin.json`, `gemini-extension.json` and the `metadata.version` in SKILL.md carry the same number.
- **Plain words**: SKILL.md and the references follow the skill's own text rules. `check_text.py` runs on them in the tests.

## Checks to run before you finish

```bash
python3 -m unittest discover -s tests            # about a minute; the browser tests need Chrome, Edge or Brave
DEMYSTIFY_SLOW_TESTS=1 python3 -m unittest discover -s tests -p 'test_video_integration.py'   # renders real videos
claude plugin validate --strict .
```

State what you ran and what it printed. If you could not run a check, say so.
