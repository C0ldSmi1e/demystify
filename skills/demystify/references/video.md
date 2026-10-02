# Video: a short narrated animation

The result is an MP4 with narration, and a subtitle file. The animation library is Manim Community, which gives the "3Blue1Brown style". Make the video 45 to 120 seconds long, unless the user asks for a different length. The work takes 20 to 40 minutes.

A video hides errors well. A viewer does not easily see an incorrect statement in a smooth animation. Thus the outline must be correct before you start, and you must look at the frames before you deliver.

## 0. Preflight

    python3 SKILL_DIR/scripts/doctor.py

The script lists what the video step needs, what is missing, and the command that corrects each item. Show each missing item and its command to the user. Wait for the answer. Do not run an install command unless the user agrees.

This skill installs nothing permanently. Manim and the voice engine run in temporary environments that `uv` makes.

## 1. Make the project

    python3 SKILL_DIR/scripts/video.py init demystify-out/SUBJECT

This writes `storyboard.json`, `scenes.py`, and `scene_kit.py` into the folder. It also writes `demystify-out/.gitignore`. All the commands below use the same folder.

## 2. Write the storyboard

Edit `storyboard.json`. A beat is one or two spoken sentences, plus what the screen shows during those sentences.

- Write 8 to 20 beats, with one idea in each beat.
- `narration` follows `references/text.md`, and it is for the ear. A sentence has 20 words or fewer. Do not use symbols, and do not read file paths aloud.
- `visual` is your plan for the picture: what appears, moves, or changes. If nothing changes during a beat, join it to an adjacent beat. No script reads `visual`.
- The first beat gives the question or the surprise. The last beat gives the takeaway in one sentence.
- The voice speaks about 170 words in a minute. Thus 200 words make about 70 seconds.
- Say an inferred point as an inferred point: "probably", "the code suggests".

The narration is also the text of the subtitles. If the voice must say something in a different way from how you write it, add a `subtitle` to the beat with the written form. For example, the narration "The server answers four twenty-nine" has the subtitle "The server answers 429". Give the subtitle the same number of sentences as the narration. Then each sentence of the subtitle shows while the voice says it.

Check the narration:

    python3 SKILL_DIR/scripts/check_text.py demystify-out/SUBJECT/storyboard.json

## 3. Record the narration first

    python3 SKILL_DIR/scripts/narrate.py demystify-out/SUBJECT

The script tries these voices in sequence, and tells you which voice it used:

1. ElevenLabs, if `ELEVENLABS_API_KEY` is in the environment. This is a paid service. Get the agreement of the user before the first run.
2. Kokoro, a free voice that runs on the computer. It needs a download of 354 MB, one time. Ask the user. Then run the command again with `--download`.
3. `say`, the system voice of macOS. It needs no download, and its quality is lower.
4. No voice. The video is silent and has subtitles.

The script writes one audio file for each beat. It also writes `beats.json` with the measured length of each beat and the start of each sentence. The animation takes its timing from these numbers. Thus you must record again after you change the narration.

## 4. Write the scenes

Edit `scenes.py`. The class `Video` has one method for each scene. In a method, put the animations of each beat in a block:

    with self.beat("b03") as dur:
        self.play(FadeIn(bucket), run_time=1.0)
        self.wait_until(dur.starts[1])
        self.play(Create(arrow), run_time=1.0)
        self.wait_until(dur.at("five requests"))
        self.play(Indicate(rate), run_time=0.8)

The kit, `scene_kit.py`, gives you these things:

| Name | What it does |
| --- | --- |
| `self.beat("b03")` | Plays the audio of the beat and adds its subtitles. It holds the picture until the voice stops. |
| `dur` | The length of the narration in seconds. The animations of a beat must have a total length of `dur` or less. |
| `dur.starts` | The second at which each sentence of the beat starts. `dur.starts[1]` is the second sentence. |
| `dur.at("five requests")` | The second at which the voice says these words. In a sentence, the time is an estimate. |
| `self.wait_until(t)` | Waits until `t` seconds after the start of the beat. Use it to show a thing when the voice says it. |
| `self.clear_scene()` | Fades out everything, and stops the updaters. Call it between scenes. |
| `T(text, size=BODY, color=FG, weight=NORMAL)` | Text. For bold text, give `weight=BOLD`. |
| `M(text, size=BODY, color=FG)` | Monospace text: code, numbers, names from the source. |
| `fit(mobject, max_width=13.0, max_height=7.0)` | Makes the object smaller if it is larger than this size. |
| `FG`, `MUTED`, `BLUE`, `YELLOW`, `GREEN`, `RED`, `PURPLE` | The colours. |
| `TITLE`, `HEAD`, `BODY`, `SMALL` | The text sizes: 46, 36, 28, 22. |

The kit keeps its own data in attributes that start with `_dm_`. Do not use that prefix for your names.

These rules prevent the usual failures:

- **Manim Community 0.21.** Do not use ManimGL names such as `ShowCreation` or `TexMobject`.
- **No LaTeX.** These classes need LaTeX and fail without it: `MathTex`, `Tex`, `Title`, `BulletedList`, `DecimalNumber`, `Integer`, `Variable`, `Matrix`, `BarChart`, `BraceLabel`. Axes with `include_numbers=True` fail also. Make all text with `T("...")`. Make numbers and axis labels from text. `Table`, `Code`, `Brace`, and plain `Axes` and `NumberLine` work without LaTeX. For formulas, read "Math" below.
- **Fonts.** Do not give a font name, because the font is possibly not on the computer. `T()` and `M()` select a font that exists.
- **Stay in the frame.** The frame is 14.2 wide and 8 high, with the origin at its centre. Keep x between -6.5 and 6.5, and y between -3.5 and 3.5. Set positions with `next_to`, `arrange`, `to_edge`, and `move_to`.
- **Subtitles.** The subtitles are a separate file. A player shows them across the bottom of the picture. If you can, keep text above y = -3.0.
- **Space.** Keep 0.3 or more between a label and each shape that is near it, not only the shape that the label belongs to.
- **Text width.** A monospace character is 0.23 wide at size 28, and 0.18 at size 22. A sans-serif character is about 0.18 wide at size 28. Thus the frame holds 55 monospace characters at size 28. To make a label fit its box, use `fit(label, max_width=box.width - 0.6)`.
- **Text size.** Do not show text below size 22. The draft reports smaller text, also text that `fit` made smaller. Then use fewer words or two lines.
- **A simple stage.** Show about six labelled things at most. Keep an object on the screen if the next beat needs it. Remove an object that the viewer does not need.
- **Show what the voice says.** Each sentence of the narration needs something on the screen that agrees with it, at the time that the voice says it.
- **A true picture.** The picture obeys the same facts as the narration. Do not show a change that the source does not make. If the picture simplifies, the voice says so.
- **Real names.** Show the names from the source with `M(...)`: the functions, the parameters, the values. Then the viewer can find them in the file.
- **One tracker for things that move together.** Use one `ValueTracker` with `always_redraw`. For example, `Create` and `MoveAlongPath` do not move at the same speed, so a dot does not stay on the end of a curve that grows.
- **An object that redraws.** Put an `always_redraw` object on the stage with `self.add`. It does not fade in. Do not copy it before it is on the stage, and do not change its `submobjects` yourself.
- **A faded object is gone.** After `FadeOut`, make a new object if you need the object again.
- **Remove each part.** `self.remove(group)` does not remove parts that an animation added one at a time. Use `FadeOut(group)`, `self.remove(*group)`, or `self.clear_scene()`.
- **Opacity.** Use `set_stroke(opacity=...)` or `fill_opacity=`. A bare `set_opacity` also fills curves.
- **Groups with images.** Use `Group`, not `VGroup`, when a group contains an image.
- **The end.** Hold the last picture for 1.5 seconds. Do not fade it out.

### Math

To show a formula, add `--math` to the `video.py` commands and use `MathTypst("e^(i pi) + 1 = 0")`. The syntax is Typst, not LaTeX:

| To show | Write |
| --- | --- |
| A power, an index | `x^2`, `x_1`, `e^(i pi)` |
| A fraction | `a/b` or `(a + b)/c` |
| A root | `sqrt(x)` |
| A sum | `sum_(i=1)^n i` |
| An integral | `integral_0^1 x^2 dif x` |
| Greek letters | `alpha`, `pi`, `theta` |

Render a draft and look at each formula.

## 5. Draft, then look

    python3 SKILL_DIR/scripts/video.py draft demystify-out/SUBJECT

This makes a fast 720p render. It prints the start and the end of each beat. It writes `review/sheet.png`, which shows two frames for each beat: the middle of the beat and the end of its narration. It also writes each of these frames at full size. Each draft replaces the frames of the draft before it.

The draft reports the faults that it can measure:

- An animation that is longer than its narration.
- Text that leaves the frame, overlaps other text, or is too small. The kit measures the text at the end of each animation in a beat. The report gives the time of each fault.
- A beat that no scene plays.

Read `review/sheet.png`. Then read the full-size frames. The script does not find these faults:

- A fault that is there only while an animation runs.
- A label that touches a line or a shape.
- An arrow that points at nothing.
- A frame that is crowded, or a frame that is almost empty.
- A picture that does not show what the narration says.

Two frames for each beat do not show each change. To see a different moment, use the `frame` command with the seconds that you want:

    python3 SKILL_DIR/scripts/video.py frame demystify-out/SUBJECT 12.5 14.0

Take a frame for each moment where an object appears, moves fast, or changes, and for each fault in the report.

Correct `scenes.py` and run the draft again. Do four draft rounds at most. Then make the final render and report what remains.

If the render fails, the script shows the error and the line in `scenes.py`.

## 6. Final render and check

    python3 SKILL_DIR/scripts/video.py final demystify-out/SUBJECT

This makes the 1080p render. It writes `video.mp4`, `video.srt`, and `poster.png`. It then checks the file: a video stream, an audio stream that is not silent, and the expected length. It also deletes the working files of Manim.

The poster is the last picture of the video. For a different picture, add `--poster SECONDS`. After the final render, the `frame` command takes its frames from `video.mp4`.

## 7. Deliver

Give the path, the length, and the voice that the script used. Open the file for the user: `open` on macOS, `xdg-open` on Linux, `start` on Windows.

Say plainly that you looked at the frames but did not hear the audio. Ask the user to listen one time. A video has no place for marks, so list in your reply the points that are inferred or not verified.
