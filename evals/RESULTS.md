# Results

Two small runs on 2 October 2026, reported as they came out. The raw numbers are in [results-2026-10-02.json](results-2026-10-02.json).

Every request ran three times with the plugin loaded and three times with no plugin, in clean sessions, with Claude Code 2.1.287 and Claude Sonnet 5.5. The subject was always the same 45-line rate limiter.

## What was measured

The pass/fail graders in this folder are too coarse to tell the two sides apart, so two scripts look closer.

- `look.py` opens each diagram and page in a real browser. An **error** is text that overlaps other text, leaves its box, or leaves the drawing, a script error, or a page that scrolls sideways on a phone. A **warning** is text too small to read, text too faint to read, or a page that changes height when you use a control.
- `measure.py` also reads the words. A diagram has a **worked example** if it shows a wait time that someone calculated, such as `Retry-After: 0.2`. A result **says what was checked** if it marks something as tested, inferred or not verified.

## With a shell

This is normal use: the agent can run the skill's check scripts and look at what it made.

```bash
python3 evals/with_shell.py --runs 3 --model claude-sonnet-5-5
```

| | With the skill | Without |
| --- | --- | --- |
| Skill loaded by itself | 6 of 6 | n/a |
| **Diagram**: errors in one diagram | 0 | 0 |
| **Diagram**: has a worked example | 3 of 3 | 0 of 3 |
| **Diagram**: says what was checked | 3 of 3 | 0 of 3 |
| **Diagram**: words in the drawing | 311 | 69 |
| **Page**: errors in one page | 0 | 0.33 |
| **Page**: warnings in one page | 0 | 13 |
| **Page**: says what was checked | 3 of 3 | 0 of 3 |
| Cost of one diagram | $0.26 | $0.08 |
| Cost of one page | $0.38 | $0.13 |
| Time for one diagram | 69 s | 20 s |
| Time for one page | 114 s | 40 s |

The whole run cost $2.56. With the skill, the agent ran `look.py` one to three times for each result.

## Without a shell

On the machine that produced these numbers, `claude plugin eval` would not give its runs a shell. So here the skill could read its instructions and write files, but it could not run a check or look at a screenshot. The numbers show what the instructions and the templates do alone.

```bash
claude plugin eval . --runs 3 --model claude-sonnet-5-5 --keep-temp --json results.json --allow-tools Write Edit
python3 evals/measure.py results.json
```

| | With the skill | Without |
| --- | --- | --- |
| Skill loaded when the request asked for an explanation | 9 of 9 | n/a |
| Skill loaded on an ordinary coding request | 0 of 3 | n/a |
| **Text**: answer in the first line | 3 of 3 | 0 of 3 |
| **Text**: headings in one answer | 0 | 7.7 |
| **Text**: longest sentence, in words | 22 | 14.7 |
| **Text**: passes the form check | 2 of 3 | 3 of 3 |
| **Diagram**: errors in one diagram | 0 | 0 |
| **Diagram**: has a worked example | 3 of 3 | 0 of 3 |
| **Page**: errors in one page | 0 | 1 |
| **Page**: warnings in one page | 2 | 13.7 |
| Cost of one text answer | $0.08 | $0.04 |
| Cost of one diagram | $0.30 | $0.07 |
| Cost of one page | $0.33 | $0.19 |

This run cost $3.19.

## How to read it

- **Pages gain the most.** Left alone, the model made pages that jumped when you moved a slider and had text too small for a phone, every time. With the skill and a shell, there was nothing left to report.
- **Diagrams were laid out well either way.** The difference is in what they say. Without the skill you get a clean flowchart of the code. With it you get the flowchart, a worked example with real numbers, and a note of what was tested.
- **Text changes shape, not sentence length.** The model alone already writes short sentences when asked for Simplified Technical English. It also writes seven or eight headings and puts the answer under them. The skill puts the answer first and uses no headings.
- **The check matters.** Without a shell, two pages in three still jumped, and one text answer in three had a paragraph that was too long. Those are the faults the check scripts exist to catch. With a shell they were gone.
- **It costs more.** About three times the price and three times the wait for a diagram or a page. The extra goes on reading the instructions, testing the code, and looking at the result.

## Limits

- Three runs for each row. A difference of one is noise.
- One model, one subject, one day.
- The scripts that measure the results are the same scripts that the skill uses to check its work. A fault that the scripts cannot see is not counted for either side.
- The text case ran once more after a last change to the text rules, and its row is from that run. The other rows are from the run before it. The files they depend on did not change.
- Whether the skill loads by itself is a decision of the model. An earlier wording of its description missed one diagram request in six. The wording was changed, and the six runs above all loaded it. Typing `/demystify` always loads it.
- Video has no row. A video takes about ten minutes, and nothing here can judge one. The repository has a [real example](../examples/token-bucket/video.mp4) and tests that render short videos.
