# Install

Every route below installs the same folder, `skills/demystify`. Pick the one for your agent.

Text, diagrams and pages work as soon as the skill is installed. Video needs a few tools on your machine; see [What video needs](#what-video-needs).

| Agent | Status |
| --- | --- |
| Claude Code | Install tested with 2.1.287. The examples in this repository were made with it. |
| Codex | Install tested with 0.150.1. |
| Gemini CLI | Install tested with 0.62.0. |
| Cursor, GitHub Copilot, OpenCode, others | The installer is tested. The agents themselves have not been run. |
| claude.ai, Cowork | Not tested. |

"Install tested" means the commands below ran on a clean setup and the agent listed the skill afterwards.

## Claude Code

```bash
claude plugin marketplace add C0ldSmi1e/demystify
claude plugin install demystify@demystify
```

Or, inside a session:

```text
/plugin marketplace add C0ldSmi1e/demystify
/plugin install demystify@demystify
```

Then type `/demystify` followed by what you want explained, or just ask for an explainer in your own words.

```bash
claude plugin update demystify@demystify        # update
claude plugin uninstall demystify@demystify     # remove
claude plugin marketplace remove demystify
```

## Codex

```bash
codex plugin marketplace add C0ldSmi1e/demystify
codex plugin add demystify@demystify
```

In Codex, type `$` and pick `demystify` from the list, or ask for an explainer in your own words. Installed as a plugin, the skill's full name is `demystify:demystify`.

If you prefer the short name `$demystify`, install it as a plain skill instead:

```bash
npx skills@latest add C0ldSmi1e/demystify -a codex
```

```bash
codex plugin marketplace upgrade demystify      # update
codex plugin remove demystify@demystify         # remove
codex plugin marketplace remove demystify
```

## Gemini CLI

```bash
gemini extensions install https://github.com/C0ldSmi1e/demystify
```

Then type `/demystify` followed by your request, or just ask. Check that it loaded with `gemini skills list`.

```bash
gemini extensions update demystify              # update
gemini extensions uninstall demystify           # remove
```

## Cursor, GitHub Copilot, OpenCode, and other agents

Most agents read skills from `.agents/skills/` in your project. This command puts the skill there:

```bash
npx skills@latest add C0ldSmi1e/demystify
```

Add `-g` to install it for all your projects, or `-a cursor` (or another agent name) to target one agent. Start a new chat afterwards and type `/demystify`.

```bash
npx skills@latest update                        # update
npx skills@latest remove demystify              # remove
```

## claude.ai and Cowork

Open **Customize → Plugins**, add a marketplace from GitHub, and enter `C0ldSmi1e/demystify`. Text, diagrams and pages work there. Video does not, because it needs a shell.

## By hand

Copy the folder `skills/demystify` into one of these places:

| Scope | Most agents | Claude Code |
| --- | --- | --- |
| One project | `.agents/skills/demystify` | `.claude/skills/demystify` |
| All projects | `~/.agents/skills/demystify` | `~/.claude/skills/demystify` |

## What video needs

Run the doctor. It only reads; it never installs anything.

```bash
python3 skills/demystify/scripts/doctor.py
```

(Use the path where the skill landed on your machine. You can also just ask your agent to "run the demystify doctor".)

It checks for three things and prints the exact fix for whatever is missing:

- **uv**, which runs Manim and the voice in throwaway environments. Nothing is installed permanently.
- **cairo**, a graphics library that Manim builds against on macOS and Linux. On a Mac: `brew install cairo pkg-config`.
- **A voice.** In order of preference:
  1. ElevenLabs, if `ELEVENLABS_API_KEY` is set in your environment. It is a paid service, and the key is only ever read from the environment.
  2. Kokoro, a free voice that runs on your machine. It is a one-time 354 MB download, and your agent asks before it starts.
  3. The built-in macOS voice.
  4. No voice: a silent video with subtitles.

You do not need LaTeX or ffmpeg.

The screenshot check for diagrams and pages uses Chrome, Chromium, Edge or Brave if one is installed. Without a browser the skill still works; it just tells you that nobody looked at the rendered result.
