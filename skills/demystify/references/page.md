# Page: an explanation that the reader can operate

The result is one self-contained HTML file. A page is the correct format when the reader can change something and see the effect. If nothing on the page reacts, make a diagram.

## 1. Plan the page

Use the outline. The parts, from top to bottom:

1. **Title.** The takeaway as a sentence. Keep the conditions that make it true, for example "up to" and "by default".
2. **Answer.** One short paragraph.
3. **Picture.** An inline SVG diagram of the mechanism.
4. **Steps.** The key points, one step visible at a time. Each step marks the part of the picture that it explains.
5. **Try it.** One to three inputs that are connected to a live model of the mechanism. The result is adjacent to the inputs: a number, a sentence, and a small picture that changes.
6. **Limits.** What the model does not include, what can fail, and what is not verified.
7. **Terms and sources.**

## 2. Start from the shell

Copy `assets/page.html` to the output folder as `page.html`. Edit the copy. The shell gives you the layout, light and dark colours, a stepper that works with the keyboard, inputs with presets, a result area, and a footer for the source.

All the sample content is there only to show the technique. Replace all of it: the texts, the picture, the steps, the inputs, and the model. Each sample text starts with `EDIT`, and the check reports each one that remains. Keep the structure unless the subject needs a different one.

## 3. Rules

- **One file.** CSS and JavaScript are inline. No external scripts, fonts, styles, or images, and no network requests. The page must work offline.
- **A true model.** The "Try it" part calculates its result with the same rule as the real thing: the same algorithm, the same parameter names, the same default values as the source. Do not invent an output. If you simplify, say how in "Limits".
- **A model that only calculates.** Keep the model in one function, `model(inputs)`, that returns its results. It does not read the page and it does not change the page. Then you can test it.
- **Test the model.** If you can run the source, run the source and the model with the same inputs and compare the results. The check prints the value of an expression in the page: add `--print "JSON.stringify(model({a: 35, b: 20}))"`. Formats of numbers are a usual difference. For example, Python writes 0.25 with one decimal place as `0.2`, and JavaScript writes it as `0.3`.
- **One state object.** Each input writes to the state. One `render` function draws everything from the state. Call it when the page loads, so that the page is complete before the reader does something.
- **Sensible defaults.** The page starts with the normal case. Add two to four preset buttons for the interesting cases: the limit, the failure, the surprise.
- **Plain JavaScript.** No frameworks and no build step.
- **The picture.** It follows the layout rules of `references/diagram.md`, section 3, with three differences. Use the classes and the arrowheads of the page shell, not those of the sheet template. The text sizes are those of the shell classes: 16, 15, and 14. Keep the `viewBox` 720 wide.
- **Readable on a phone.** No horizontal scroll at a width of 360 pixels. Body text is 16 pixels or larger, and secondary text is 14 or larger. Text in a picture is 12 or larger at the size that a phone shows. Put a wide picture in the `.scroll` box of the shell, so that it keeps a readable size.
- **Stable layout.** The page must not jump when the reader moves a slider or goes to the next step. Give each area that changes a fixed size: the same number of lines in each state, or a minimum height.
- **Operable.** Each input is a real `button` or `input` with a visible label. It works with the keyboard. Obey `prefers-reduced-motion`.
- **Words.** Sentences follow `references/text.md`. Do not put long paragraphs on a page. A caption is one short sentence.
- **Marks.** A statement with no mark is a statement that you read in the source. Put each statement that you tested, inferred, or did not verify in "Limits". Start it with its mark: "Tested:", "Inferred:", or "Not verified:". The numbers that the model shows need no mark, because "Try it" says where they come from.
- **Motion with a purpose.** Animate only what changes in the mechanism. An animation is shorter than one second, or the reader steps through it.

## 4. Check

    python3 SKILL_DIR/scripts/look.py demystify-out/SUBJECT/page.html --mobile

The script renders the page in a local browser at desktop width and at a phone width of 360 pixels. It saves screenshots of the full page in `review/`. It reports these faults:

- Script errors, also the errors that occur when it presses each button and moves each slider.
- A page that becomes higher or lower when the script uses an input.
- Horizontal scroll, and text that is cut off, too small, or low in contrast.
- Text in a picture that overlaps other text, leaves its box, or leaves the picture.
- External requests, and files that the page needs.
- A page with no inputs, and sample text that remains.

Then look at all the screenshots yourself. The script does not find every fault. Make sure that the top of the page shows the answer and the picture, and that no part is empty or crowded.

The screenshots show the page as it loads. To see a different state, add `--do` with JavaScript that makes the state. For example:

    python3 SKILL_DIR/scripts/look.py demystify-out/SUBJECT/page.html --mobile --do "document.querySelector('[data-preset=failure]').click(); document.getElementById('lab-title').scrollIntoView()"

This adds one screenshot of that state at each width. Give `--do` again for each more state. Look at two states or more: the failure preset, and a step of "Step by step" that is not the first step.

Each run replaces the screenshots of the run before it. To keep them, add `--out` with a different folder.

Then check the text of the page:

    python3 SKILL_DIR/scripts/check_text.py demystify-out/SUBJECT/page.html

Correct the file and run the checks again.

## 5. Deliver

Give the path and open the file for the user: `open` on macOS, `xdg-open` on Linux, `start` on Windows. Tell the user the first thing to try, in one line.
