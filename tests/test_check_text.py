import json
import tempfile
import unittest
from pathlib import Path

from helpers import load, run_script

check_text = load("check_text")

SHORT = "The server keeps a bucket of tokens for each client."
OVER_LIMIT = (
    "The server keeps a bucket of tokens for each client and it takes one token from the bucket "
    "each time that the client sends a new request to it."
)
FAR_OVER_LIMIT = OVER_LIMIT + " " + "and then it also writes one more line into the audit log for later".rstrip(".") + "."


def report(text, level=80, **kwargs):
    units = check_text.units_from_markdown(text, "t.md", kwargs.get("limit", 25))
    return check_text.check(units, level)


class SentenceSplitting(unittest.TestCase):
    def test_splits_on_sentence_ends(self):
        self.assertEqual(check_text.split_sentences("One idea. Another idea! A third?"),
                         ["One idea.", "Another idea!", "A third?"])

    def test_keeps_abbreviations_and_decimals_together(self):
        self.assertEqual(len(check_text.split_sentences("Use a plain word, e.g. Start, not a rare one.")), 1)
        self.assertEqual(len(check_text.split_sentences("The width is 0.6 x the font size. It is exact.")), 2)
        self.assertEqual(len(check_text.split_sentences("Open SKILL.md and read it.")), 1)

    def test_colon_ends_a_sentence_only_before_a_list(self):
        self.assertEqual(len(check_text.split_sentences("Plain words: use, not utilize.")), 1)
        self.assertEqual(len(check_text.split_sentences("Do these steps:")), 1)

    def test_word_count_ignores_bare_punctuation(self):
        self.assertEqual(check_text.count_words("Close the valve - now."), 4)
        self.assertEqual(check_text.count_words("Run CODE and read URL ."), 5)


class MarkdownReading(unittest.TestCase):
    def test_code_headings_tables_and_quotes_are_exempt(self):
        text = "\n".join([
            "# " + FAR_OVER_LIMIT,
            "",
            "```",
            FAR_OVER_LIMIT + "; " + FAR_OVER_LIMIT,
            "```",
            "",
            "| " + FAR_OVER_LIMIT + " | b |",
            "",
            "> " + FAR_OVER_LIMIT,
            "",
            "    indented code " + FAR_OVER_LIMIT,
            "",
            SHORT,
        ])
        result = report(text, level=100)
        self.assertTrue(result["ok"], result["findings"])
        self.assertEqual(result["stats"]["sentences"], 1)

    def test_yaml_front_matter_is_not_prose(self):
        text = "---\nname: x\ndescription: \"" + FAR_OVER_LIMIT + "\"\n---\n\n" + SHORT + "\n"
        result = report(text, level=100)
        self.assertTrue(result["ok"], result["findings"])
        self.assertEqual(result["stats"]["sentences"], 1)

    def test_inline_code_and_links_count_as_words_a_reader_sees(self):
        units = check_text.units_from_markdown(
            "Run `python3 a/very/long/path/to/script.py --with many --flags` and open [the docs](https://example.com/x).",
            "t.md", 25)
        self.assertEqual(units[0].text, "Run CODE and open the docs.")

    def test_a_numbered_item_has_the_same_limit_as_other_text(self):
        # A numbered item can be a description, so only --steps gives it the limit of an instruction.
        words_22 = "Open the file and read each line of it until the end and then close the file with care for all now."
        self.assertEqual(check_text.count_words(words_22), 22)
        for text in ("1. " + words_22, "- " + words_22, words_22):
            self.assertTrue(report(text, level=100)["ok"], text)
            self.assertFalse(report(text, level=100, limit=20)["ok"], text)


class Levels(unittest.TestCase):
    def test_level_100_rejects_any_long_sentence(self):
        self.assertFalse(report(" ".join([SHORT] * 4) + "\n\n" + OVER_LIMIT, level=100)["ok"])

    def test_level_80_allows_one_in_five(self):
        text = "\n\n".join([" ".join([SHORT] * 4), OVER_LIMIT])  # 1 of 5 over the limit
        result = report(text, level=80)
        self.assertTrue(result["ok"], result["findings"])
        self.assertEqual(result["stats"]["over_limit"], 1)

    def test_level_80_rejects_more_than_one_in_five(self):
        text = "\n\n".join([" ".join([SHORT] * 3), OVER_LIMIT, OVER_LIMIT])  # 2 of 5
        result = report(text, level=80)
        self.assertFalse(result["ok"])
        self.assertEqual(sum(1 for f in result["findings"] if f["error"]), 1)

    def test_level_80_rejects_a_sentence_far_over_the_limit(self):
        self.assertGreater(check_text.count_words(FAR_OVER_LIMIT), 35)
        text = "\n\n".join([" ".join([SHORT] * 5), " ".join([SHORT] * 4), FAR_OVER_LIMIT])
        self.assertFalse(report(text, level=80)["ok"])

    def test_paragraph_and_semicolon_rules_hold_at_both_levels(self):
        seven = " ".join([SHORT] * 7)
        for level in (80, 100):
            self.assertFalse(report(seven, level=level)["ok"])
            self.assertFalse(report("The bucket is empty; the server waits.", level=level)["ok"])

    def test_a_lead_in_is_not_a_sentence_of_its_paragraph(self):
        six = "**Example.** " + " ".join([SHORT] * 6)
        seven = "**Example.** " + " ".join([SHORT] * 7)
        self.assertTrue(report(six)["ok"])
        result = report(seven)
        self.assertFalse(result["ok"])
        self.assertIn("7 sentences in one paragraph", result["findings"][0]["message"])

    def test_list_items_do_not_count_as_one_paragraph(self):
        text = "\n".join("- " + SHORT for _ in range(9))
        self.assertTrue(report(text, level=100)["ok"])


class Advice(unittest.TestCase):
    def test_advice_never_fails_the_check(self):
        result = report("The request is rejected by the server. We utilize a cache prior to the call.")
        self.assertTrue(result["ok"])
        rules = {a["rule"] for a in result["advice"]}
        self.assertEqual(rules, {"passive", "plain-word"})

    def test_hedges_are_not_advice(self):
        result = report("The request may have failed. The cause could be an old client.")
        self.assertEqual(result["advice"], [])


class OtherInputs(unittest.TestCase):
    def test_html_skips_code_script_and_headings(self):
        html = (
            "<!doctype html><html><head><title>" + FAR_OVER_LIMIT + "</title><style>p{color:red}</style></head><body>"
            "<h1>" + FAR_OVER_LIMIT + "</h1><p>" + SHORT + " Run <code>a b c d e f g h i j k l m n o p q r s t u v w x y z</code> now.</p>"
            "<pre>" + FAR_OVER_LIMIT + "</pre><script>var s = '" + FAR_OVER_LIMIT + "';</script>"
            "<ol><li>" + SHORT + "</li></ol><button>Send</button></body></html>"
        )
        units = check_text.units_from_html(html, "p.html", 25)
        self.assertEqual([u.kind for u in units], ["paragraph", "item"])
        self.assertIn("Run CODE now.", units[0].text)
        self.assertEqual(units[1].limit, 25)
        self.assertTrue(check_text.check(units, 100)["ok"])

    def test_storyboard_uses_the_narration_limit(self):
        beats = {"beats": [{"id": "b01", "narration": SHORT}, {"id": "b02", "narration": OVER_LIMIT}]}
        units = check_text.units_from_storyboard(beats, "storyboard.json", 20)
        result = check_text.check(units, 100)
        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["source"], "storyboard.json beat b02")

    def test_storyboard_on_the_command_line_is_strict_without_a_flag(self):
        words_22 = "Open the file and read each line of it until the end and then close the file with care for all now."
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "storyboard.json"
            board.write_text(json.dumps({"beats": [{"id": "b01", "narration": " ".join([SHORT] * 9) + " " + words_22}]}),
                             encoding="utf-8")
            proc = run_script("check_text", board)
        self.assertEqual(proc.returncode, 1)  # one sentence in ten is over 20 words: level 80 would pass it
        self.assertIn("level 100", proc.stdout)
        self.assertIn("narration", proc.stdout)

    def test_text_without_spaces_between_words_is_reported_not_failed(self):
        result = report("这是一个很长的句子。")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stats"]["length_not_checked"], 1)


class CommandLine(unittest.TestCase):
    def test_exit_status_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / "good.md", Path(tmp) / "bad.md"
            good.write_text(SHORT + "\n", encoding="utf-8")
            bad.write_text(FAR_OVER_LIMIT + "\n", encoding="utf-8")
            self.assertEqual(run_script("check_text", good).returncode, 0)
            failed = run_script("check_text", bad, "--json")
            self.assertEqual(failed.returncode, 1)
            self.assertFalse(json.loads(failed.stdout)["ok"])
            self.assertEqual(run_script("check_text", Path(tmp) / "missing.md").returncode, 2)

    def test_reads_standard_input(self):
        proc = run_script("check_text", "-", stdin=SHORT + "\n")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("PASS", proc.stdout)

    def test_steps_gives_every_sentence_the_limit_of_an_instruction(self):
        words_22 = "Open the file and read each line of it until the end and then close the file with care for all now."
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "steps.md"
            file.write_text("1. " + words_22 + "\n", encoding="utf-8")
            plain = run_script("check_text", file, "--level", "100")
            steps = run_script("check_text", file, "--level", "100", "--steps")
        self.assertEqual(plain.returncode, 0, plain.stdout)
        self.assertIn("does not know which sentences are instructions", plain.stdout)
        self.assertEqual(steps.returncode, 1, steps.stdout)
        self.assertIn("limit 20", steps.stdout)

    def test_the_report_says_which_long_sentences_the_level_permits(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "t.md"
            file.write_text("\n\n".join([" ".join([SHORT] * 4), OVER_LIMIT]) + "\n", encoding="utf-8")
            proc = run_script("check_text", file)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("sentences over the limit: 1 \u00b7 level 80 permits 1 in this text", proc.stdout)
        self.assertIn("note ", proc.stdout)
        self.assertIn("level 80 permits this one", proc.stdout)
        self.assertNotIn("ERROR", proc.stdout)


if __name__ == "__main__":
    unittest.main()
