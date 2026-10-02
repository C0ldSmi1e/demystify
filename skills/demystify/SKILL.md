---
name: demystify
description: "Explain a topic, code, a diff, or a result in the format that is easiest to understand - plain Simplified Technical English text, a one-sheet diagram, an interactive HTML page, or a narrated explainer video. Use when the user asks for an explainer, asks for a diagram, an interactive page, or a video that shows or explains how something works, asks for ASD-STE100 or Simplified Technical English, or names demystify."
license: MIT
metadata:
  version: "0.1.0"
  author: "Daniel Yu"
  homepage: "https://github.com/C0ldSmi1e/demystify"
---

# Demystify

Explain one subject so that a reader understands it quickly. Use one of four formats: text, diagram, page, or video. Each format has a reference file and a check that you do before you deliver.

## Paths

File names in this skill are relative to the directory that contains this SKILL.md. Call that directory SKILL_DIR. Build an absolute path from it before you read a file or run a script. Run scripts with `python3`, for example `python3 SKILL_DIR/scripts/look.py FILE` (on Windows, `python`). Stay in the project of the user. Do not change directory into SKILL_DIR.

## 1. Read the request

The request is the text that the user gave with this skill, or the message that made you load it. Find these things:

- **Subject.** What to explain. If the user gives only a format ("page", "now as a video"), the subject is the one that you explained last.
- **Format.** A first word `text`, `diagram`, `page`, or `video`, or the same wish in plain words ("as a diagram", "make a video").
- **Level.** For text only. `strict` or "100%" means the strict rules. If the user does not say, use the default level, 80%.
- **Reader.** Use the reader that the user names. If there is none, write for an engineer who knows the language and the usual tools, but not this code or this topic.

Ask a question only if you cannot tell what the subject is.

## 2. Pick the format

If the user named a format, use it. If not, pick the lightest format that shows the main point:

| The main point is | Format |
| --- | --- |
| A definition, a reason, a short procedure | text |
| Structure, flow, sequence, states, a comparison, or an overview of a whole topic | diagram |
| Behaviour that changes with inputs, or a subject with several parts to explore | page |
| Motion or change over time | page with steps, and offer a video |

Do not start a video unless the user asks for one. A video takes a long time and needs tools. Offer it in one line.

## 3. Get the facts first

Do this for every format, before you write or draw.

1. Read the real source: the code, the diff, the document, the data. Do not explain from memory what you can read.
2. If the code is safe to run, run it to test the numbers of your example. A test run must not leave files in the project. For Python, use `python3 -B`. Give a test program on standard input, or put it in a temporary folder outside the project.
3. Write a short outline: the answer in one sentence, 3 to 7 key points in sequence, one concrete example with real names and numbers, and the limits.
4. Give each point a mark: read in the source, tested, inferred, not verified, or general knowledge.

Every format tells the same outline. When you write files, save the outline as `outline.md` in the output folder, and keep it correct when you change a fact. It can hold facts that the result leaves out. Then a second format can use it.

## 4. Build

Read one reference file and follow it:

| Format | Read | Result |
| --- | --- | --- |
| text | `references/text.md` | The explanation in your reply. A long one also has a copy in a file |
| diagram | `references/diagram.md` | One self-contained SVG file |
| page | `references/page.md` | One self-contained HTML file |
| video | `references/video.md` | An MP4 with narration, and a subtitle file |

These rules apply to every format:

- **Words.** Labels, captions, and narration follow the sentence rules in `references/text.md`. Read that file also, if you did not read it before.
- **Truth.** Do not invent a fact. Keep the strength of each claim: "may" stays "may". Keep numbers, units, names, and conditions exact. Knowledge from outside the source is permitted, with a mark that says so.
- **Marks.** A statement with no mark is a statement that you read in the source or calculated from it. Each reference file says where the other marks go.
- **Files.** Write results to `demystify-out/SUBJECT/` in the current project. SUBJECT is a short name in lower case with hyphens, for example `token-bucket`. If the user names a different place, use that place. When you create `demystify-out/`, also create `demystify-out/.gitignore` that contains only the line `*`. Then git ignores the folder. If you cannot write files, give the result in the reply or in the artifact tool of the host.
- **Consent.** Do not install software, download large files, or use a paid service unless the user agrees. The scripts tell you when one of these is necessary.
- **Secrets.** Read API keys only from the environment. Do not write a key, a token, or private data into a result.

## 5. Check and deliver

Each reference file has a check. A check has two parts: a script that measures, and your own look at the result. A script that reports no faults is not the end of the check. Do your own look each time.

One round is: check, then correct what the script and you found. Stop when a round finds no fault. Do three rounds at most, unless the reference file gives a different number. After the last correction, run the script one more time. If faults remain, deliver the result and list them.

The reference file says how to deliver. Where it says nothing, tell the user these things in a few lines:

1. What you made and where it is. Open it for the user if you can.
2. How you checked it and what you could not check. For example, you cannot hear audio.
3. The points that are inferred or not verified, and the sources. Do not repeat what the result already says.
4. One line that offers the next format, if there is one: text, then diagram, then page, then video.

Do not say that text is "ASD-STE100 compliant". Say that it is written in STE style.
