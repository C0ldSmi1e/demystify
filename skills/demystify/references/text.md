# Text: explain in Simplified Technical English style

Simplified Technical English (STE) is the controlled language of the ASD-STE100 specification. Its authors made it for aircraft maintenance manuals, so that a reader cannot misread a sentence. This file gives its sentence rules in a short form. It does not contain the official dictionary. A text that follows this file is in STE style. It is not certified STE.

## Shape of the answer

1. **The answer.** The first sentence says what the reader asked for. Do not write a preface. If the answer has two parts, use two sentences. A term can come before its definition, if the definition is in the next sentence. If the mechanism has a standard name, use that name.
2. **The idea.** Say what the thing is for and why it works that way, in plain words. The reader gets the picture before the details.
3. **The mechanism.** Give the steps that matter, in the sequence in which they occur. Do not repeat the code line by line. The reader can read the code.
4. **One example.** Use real names and numbers. You can calculate the numbers of the example from the source. If you tested the example, say so in the example. If the example is a sequence of events, write the events as a numbered list.
5. **The limits.** Say when it does not apply and what can fail. Select the limits that matter most to a person who uses the thing.

## Length and layout

- Use as few words as the subject permits. For one function or one small file, 150 to 300 words is usual. This is not a limit: do not remove a fact that the reader needs.
- Use short paragraphs. Use a numbered list only for steps in a sequence. A step can start with its condition: "If the bucket is empty, ...". Use bullets for a set of items that are not steps, for example the limits. Use a table only for a real comparison.
- Do not put a heading above an answer of three lines. In a longer answer, start the example and the limits with a bold lead-in: **Example.** and **Limits.**
- Use a code name only where the reader needs it: to find the place in the source, or to change a value. Give the name of a parameter one time, with its value. Say the idea in plain words. A sentence with three code names is hard to read.
- Code, commands, file names, and quoted text are exempt from the rules below. Show them in code format.

## Rules (default level: 80%)

1. **One idea in each sentence.** Maximum 25 words. For an instruction, maximum 20 words.
2. **One topic in each paragraph.** Maximum 6 sentences.
3. **Active voice.** Name the actor: "The server rejects the request", not "The request is rejected".
4. **Simple tenses.** Use the present, the past, or the future. Write "the job stopped", not "the job has stopped", unless the present result is the point.
5. **One word for one thing.** Choose one name for each thing and one verb for each action. Do not change them for variety.
6. **Verbs, not noun phrases.** Write "check the log", not "perform a check of the log".
7. **Plain words.** Write "use", not "utilize". Write "start", not "spin up". Write "before", not "prior to". Write "about", not "approximately". Do not use idioms.
8. **Keep the small words.** Do not remove "the", "a", "that", or the subject to save space.
9. **Maximum three nouns in a row.** Write "the inlet valve of the fuel pump", not "fuel pump inlet valve assembly".
10. **Lists for sequences.** Put three or more steps or conditions in a vertical list.
11. **No semicolons.** Write two sentences.
12. **Define a term one time.** Give the definition at the first use, or in the sentence after it. Then use the term unchanged.
13. **An instruction is a command.** Write "run the test", not "you should run the test". Put a condition first: "If the test fails, read the log."
14. **Warnings first.** Put a warning before the step that it applies to. Start it with the command. Then give the risk.

At 80%, the vocabulary is free. Use the normal technical words of the subject. One sentence in five can be longer than the limit, if a shorter sentence is less clear. No sentence can be more than 10 words over the limit.

## Strict level (100%)

Use this level when the user asks for "strict" or "100%". All the rules above apply with no exceptions. These rules also apply:

- Do not use the passive voice in an instruction. In a description, use it only if the actor is not known.
- Do not use verb forms that end in -ing, except as part of a technical name.
- Do not use the present perfect or the past perfect.
- Each word keeps one meaning and one part of speech in the full text. If "close" is a verb, do not use it to mean "near".

## What must not change

- Uncertainty is content. "May fail" does not become "fails". If the source does not know, the text does not know.
- Numbers, units, names, identifiers, negations, and conditions stay exact.
- When you divide a sentence into two, keep each condition with the statement that it applies to. For example, "by default" must stay with each default value.
- Do not add a cause, a frequency, or a mechanism that the source does not give.
- Knowledge from outside the source is permitted if it helps the reader. Put the mark "General knowledge:" on it.
- If a rule makes a sentence incorrect or unclear, clarity is more important. Keep the longer sentence and say so in one line.

## Marks

A statement with no mark is a statement that you read in the source or calculated from it. Do not put a mark on each sentence. Put a mark only on the other statements, at the start of the sentence: "Tested:", "Inferred:", "Not verified:", or "General knowledge:". A mark applies to the sentences after it, to the end of the paragraph or the list item, or to the next mark. Most of these statements are in the limits.

## Other languages

STE is English. If the user writes in a different language, answer in that language and keep the same principles: one idea in each sentence, short sentences, active voice, one word for one thing. The check script measures sentence length only for languages that put spaces between words.

## Check

A short answer of 150 words or fewer needs no file and no script. Read it one time against the source, then give it in the reply.

For a longer answer, do the two checks in this sequence.

1. **Meaning.** Read the draft against your outline and against the source. Make sure that each term has a definition, each number is correct, each condition is with its statement, the example agrees with the limits, and each inference has its mark. This check finds the important faults. A script cannot do it.
2. **Form.** Save the draft as `text.md` in the output folder. Then run the script.

The command for the form check:

    python3 SKILL_DIR/scripts/check_text.py demystify-out/SUBJECT/text.md

Add `--level 100` for strict text. The script counts the words, the words in each sentence, the sentences in each paragraph, and the semicolons. Inline code counts as one word. Correct each line that the script marks ERROR, then run it again.

- The script uses the limit of 25 words for each sentence, because it cannot tell an instruction from a description. Count the words of each instruction yourself.
- A line that the script marks `note` is a long sentence that the level permits. It is not a fault.
- The advice of the script about passive verbs and ornate words is a hint, not a fault.

The script does not check the rules of the strict level. If you cannot run scripts, find the three longest sentences and count their words yourself. Count the sentences of the longest paragraph also.

If you change a fact during the check, change `outline.md` also.

## Deliver

Give the text in your reply. The file is a copy for the user. Do not open it.

After the text, add four short lines at most: the path of the copy, the result of the form check, what you could not check, and the offer of a diagram. Do not repeat the limits or the sources. They are in the text.
