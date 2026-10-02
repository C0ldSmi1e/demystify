# Diagram: one sheet that a reader understands in a minute

The result is one self-contained SVG file. It opens in a browser. A README or a document can embed it.

## 1. Choose what to draw

| The outline is about | Draw |
| --- | --- |
| Parts, and how they contain or use each other | Block diagram |
| Steps or data that move from one part to the next | Flow, left to right |
| Messages between actors in time | Sequence diagram, time goes down |
| Conditions and transitions | State diagram |
| Options against the same criteria | Comparison table |
| Quantities | Bars on one scale |
| A value that changes in time | Line chart with two axes |
| Events with dates | Timeline |
| One real example with its parts named | Annotated example |

One panel shows one idea. A sheet has 2 to 6 panels. For code, a good sheet has three: the flow, one worked example, and the values that matter. A sheet with one large diagram is also correct.

Draw less. The reader must get the main point in one minute. Three clear panels are better than six full panels. If a panel does not help the reader to get the main point, remove it.

## 2. Start from the template

Copy `assets/sheet.svg` to the output folder as `diagram.svg`. Edit the copy. The template has these parts:

- A canvas of 1600 x 800 with a frame.
- A headline at the top. It gives the takeaway.
- Six sample panels, A to F. Each one shows how to draw one kind: flow, annotated example, table, comparison, bars, timeline. The caption at the right of a panel title gives the kind or the unit, for example "flow" or "tokens, 0 to 20".
- A footer line for the source, the date, and what is not verified.
- The styles and the arrowheads.

All the sample content is there only to show the technique. Replace all of it with your content, or delete it. Each sample text starts with `EDIT`, and the check reports each one that remains. Delete the panels that you do not use, and make the other panels larger.

For one large diagram, delete all the panels and draw in the area below the headline. Keep the frame, the headline, the footer, and the styles. Change the size of the canvas only if the content has a different shape. Then change `viewBox`, `width`, and `height` together.

## 3. Layout rules

SVG does not wrap text and does not move elements apart. You set the position of each element, so plan the grid first.

- **Grid.** Give each box a position on a grid of columns and rows. Keep 24 or more between boxes. Keep 12 or more between the edge of a box and its text.
- **Text width.** One monospace character is 0.6 x the font size wide. One sans-serif character is about 0.5. Calculate the width before you put text in a box. For example, 30 monospace characters at size 14 are 252 wide.
- **Text that does not fit.** Make the text shorter, make the box larger, or divide the text into lines with `tspan` elements. Do not make the text smaller than 12.
- **Sizes.** Headline 24, panel title 16, labels and sentences 14, notes 12. The text in boxes and the sentences of an example are 14. Arrow labels, axis labels, captions, and remarks are notes at 12.
- **Labels and notes.** A label has 6 words or fewer. It is not a sentence, so it can have no subject: "takes 1 token". A note is one short sentence. Put a label adjacent to its line or in its box, not across a line. Use real names from the source: function names, file names, values with units.
- **Lines.** Use straight lines or lines with right angles. A line does not go through a box or a label. A line can go across the edge of a grey area that groups boxes. The data line of a chart can have any angle.
- **Arrowheads.** Use the markers in the template: `marker-end="url(#arrow)"`, `url(#arrow-blue)`, or `url(#arrow-red)`. An arrow that refers to a marker that does not exist has no head.
- **Colour.** Use the ink, the greys, the blue, and the red of the template. Blue and red each have one meaning in the full sheet. For example, blue is the normal path and red is a failure. The grey classes have no meaning: use them for groups and for bars. If a colour has a meaning, add a key or a note. Colour is not the only signal: add a word or a mark.
- **Reading order.** Left to right, then top to bottom. Give the steps numbers if the layout does not make the sequence clear.
- **Self-contained.** No scripts, no external images, no external fonts, no external styles.
- **Valid XML.** Write `&amp;` for &, `&lt;` for <, and `&gt;` for > in text. Close each tag.

## 4. Content rules

- The headline gives the takeaway, not the topic. Write "A token bucket lets a burst pass, then holds a steady rate", not "Token bucket". Keep the conditions that make it true, for example "up to" and "by default".
- Show the concrete example from your outline with its real numbers.
- Complete the footer: the source, the date, and what is not verified.
- A part with no mark is a part that you read in the source or calculated from it. Mark a part that you tested with "(tested)", and a part that you inferred with "(inferred)". Put what you did not verify in the footer.
- Use one word for one thing in the full sheet, as `references/text.md` says.

## 5. Check

    python3 SKILL_DIR/scripts/look.py demystify-out/SUBJECT/diagram.svg

The script renders the file in a local browser (Chrome, Chromium, Edge, or Brave). It saves a PNG in the `review/` folder adjacent to the file. It reports these faults:

- Text that overlaps other text, leaves its box, or leaves the drawing.
- A shape that is outside the drawing, and a path that draws nothing.
- A missing arrowhead, invalid XML, and sample text that remains.

Then look at the PNG yourself. The script does not find these faults:

- A line that goes through a label or a box.
- An arrow that points at nothing.
- A panel that is crowded, or a panel that is almost empty.
- A fact that is incorrect.

Small text is hard to read in the full picture. To see one region at a larger size, add `--zoom X,Y,W,H` in the units of the drawing. For example, `--zoom 0,100,800,330` shows the top left part. You can give `--zoom` more than one time.

Correct the file and run the script again. If the script finds no browser, say in your report that nobody looked at the rendered diagram.

## 6. Deliver

Give the path. Open the file for the user: `open` on macOS, `xdg-open` on Linux, `start` on Windows. The PNG in `review/` is useful for chat tools, slides, and documents that cannot show SVG.

If the user asks for Mermaid, a Mermaid block is acceptable for a simple flow or sequence of 12 nodes or fewer. It is also acceptable when the result goes into a Markdown file that renders Mermaid. Use the same content rules.
