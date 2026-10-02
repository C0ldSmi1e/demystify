import json
import tempfile
import unittest
from pathlib import Path

from helpers import load, run_script

look = load("look")
common = load("_common")

HAS_BROWSER = common.find_browser() is not None

GOOD_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300">
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
    <path d="M0 0L10 5L0 10z" fill="#1a56db"/></marker></defs>
  <rect width="800" height="300" fill="#fff"/>
  <rect x="20" y="100" width="220" height="80" fill="#e8f0fe" stroke="#1a56db"/>
  <text x="130" y="146" text-anchor="middle" font-family="system-ui" font-size="18">Request</text>
  <rect x="290" y="100" width="220" height="80" fill="#e8f0fe" stroke="#1a56db"/>
  <text x="400" y="146" text-anchor="middle" font-family="system-ui" font-size="18">Rate limiter</text>
  <path d="M240 140H288" stroke="#1a56db" stroke-width="2" marker-end="url(#arrow)"/>
</svg>
"""

BAD_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300">
  <rect width="800" height="300" fill="#fff"/>
  <rect x="20" y="100" width="160" height="60" fill="#e8f0fe" stroke="#1a56db"/>
  <text x="30" y="136" font-family="system-ui" font-size="18">A label that is far too long for this box</text>
  <text x="300" y="60" font-family="system-ui" font-size="18">First heading here</text>
  <text x="310" y="64" font-family="system-ui" font-size="18">Second heading here</text>
  <text x="700" y="290" font-family="system-ui" font-size="18">This text runs off the canvas edge</text>
  <path d="M240 140H288" stroke="#1a56db" stroke-width="2" marker-end="url(#nope)"/>
</svg>
"""

GOOD_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Good</title>
<style>body{margin:0;font:16px/1.5 system-ui;color:#1f2933}main{max-width:720px;margin:0 auto;padding:24px}</style></head>
<body><main><h1>A bucket that refills</h1><p>Press the button to take a token.</p>
<p><button id="take">Take a token</button> <label>Size <input id="size" type="range" min="1" max="20" value="10"></label></p>
<p>Tokens left: <output id="left">10</output></p></main>
<script>var state={left:10};function render(){document.getElementById('left').textContent=state.left;}
document.getElementById('take').addEventListener('click',function(){state.left=Math.max(0,state.left-1);render();});
document.getElementById('size').addEventListener('input',function(e){state.left=+e.target.value;render();});render();</script>
</body></html>
"""

BAD_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Bad</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">
<style>body{margin:0;font:16px/1.5 system-ui}.wide{width:900px;background:#eee}.faint{color:#c9c9c9}</style></head>
<body><h1>Bad page</h1><div class="wide">This box is 900 px wide.</div><p class="faint">This grey text is hard to read.</p>
<img src="chart.png" alt="chart"><button id="go">Go</button>
<script>document.getElementById('go').addEventListener('click',function(){ missingFunction(); });</script></body></html>
"""


def rules(findings):
    return sorted({f["rule"] for f in findings})


class WithoutBrowser(unittest.TestCase):
    def test_clean_files_have_no_static_findings(self):
        for text, is_svg in ((GOOD_SVG, True), (GOOD_PAGE, False)):
            result = look.static_checks(text, is_svg)
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["warnings"], [])

    def test_missing_arrowhead_is_an_error(self):
        result = look.static_checks(BAD_SVG, True)
        self.assertEqual(rules(result["errors"]), ["missing-reference"])
        self.assertIn("#nope", result["errors"][0]["detail"])

    def test_svg_that_is_not_xml_is_an_error(self):
        broken = '<svg xmlns="http://www.w3.org/2000/svg"><text x="1" y="9">Read & write</text></svg>'
        self.assertEqual(rules(look.static_checks(broken, True)["errors"]), ["not-well-formed"])

    def test_page_must_be_one_offline_file(self):
        errors = look.static_checks(BAD_PAGE, False)["errors"]
        self.assertEqual(rules(errors), ["external-request", "needs-another-file"])

    def test_links_and_inline_data_are_allowed(self):
        page = ('<html><body><a href="https://example.com/docs">docs</a><a href="other.html">next</a>'
                '<img src="data:image/png;base64,AAAA" alt=""><svg><use href="#shape"/><g id="shape"/></svg></body></html>')
        result = look.static_checks(page, False)
        self.assertEqual(result["errors"], [])

    def test_svg_size_reads_width_height_or_viewbox(self):
        self.assertEqual(look.svg_size('<svg width="800" height="300">'), (800, 300))
        self.assertEqual(look.svg_size('<svg viewBox="0 0 1600 800">'), (1600, 800))
        self.assertEqual(look.svg_size('<svg width="400" viewBox="0 0 1600 800">'), (400, 200))
        self.assertEqual(look.svg_size('<svg viewBox="0 0 4000 2000">'), (2000, 1000))
        self.assertEqual(look.svg_size('<svg width="100%">'), (1200, 675))

    def test_slices_cover_a_page_from_the_top(self):
        self.assertEqual(look.slice_offsets(600, 900, 3), [0])
        self.assertEqual(look.slice_offsets(1270, 900, 3), [0, 370])
        self.assertEqual(look.slice_offsets(5000, 900, 3), [0, 900, 1800])

    def test_scripts_go_first_and_last_without_moving_lines(self):
        page = "<!doctype html>\n<html>\n<head>\n<title>t</title></head>\n<body>\n<p>x</p>\n</body></html>"
        copy = look.with_scripts(page, "<script>first()</script>", "<script>last()</script>")
        self.assertEqual(copy.count("\n"), page.count("\n"))
        self.assertLess(copy.index("first()"), copy.index("<title>"))
        self.assertLess(copy.index("<p>x</p>"), copy.index("last()"))
        self.assertLess(copy.index("last()"), copy.index("</body>"))

    def test_missing_file_is_exit_2(self):
        self.assertEqual(run_script("look", "/nonexistent/file.svg").returncode, 2)


@unittest.skipUnless(HAS_BROWSER, "no Chrome-family browser on this machine")
class WithBrowser(unittest.TestCase):
    def run_look(self, name, text, *args):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / name
        path.write_text(text, encoding="utf-8")
        proc = run_script("look", path, "--json", *args, timeout=240)
        return proc.returncode, json.loads(proc.stdout)

    def test_good_diagram_passes_and_is_photographed(self):
        code, report = self.run_look("good.svg", GOOD_SVG)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["screenshots"]), 1)
        self.assertTrue(Path(report["screenshots"][0]).read_bytes().startswith(b"\x89PNG"))

    def test_bad_diagram_faults_are_measured(self):
        code, report = self.run_look("bad.svg", BAD_SVG)
        self.assertEqual(code, 1)
        self.assertEqual(rules(report["errors"]),
                         ["missing-reference", "text-outside-canvas", "text-overflows-box", "text-overlap"])

    def test_shapes_that_vanish_are_errors(self):
        lost = ('<path d="M680540l4 4l8 -9" stroke="#000" fill="none"/>'
                '<rect x="5000" y="40" width="50" height="50" fill="red"/></svg>')
        code, report = self.run_look("lost.svg", GOOD_SVG.replace("</svg>", lost))
        self.assertEqual(code, 1)
        self.assertEqual(rules(report["errors"]), ["broken-path", "shape-outside-canvas"])

    def test_a_headline_is_a_sentence_but_a_paragraph_in_one_label_gets_a_warning(self):
        headline = " ".join(["word"] * 22)
        paragraph = " ".join(["word"] * 30)
        line = '<text x="20" y="%d" font-family="system-ui" font-size="8">%s</text></svg>'
        code, report = self.run_look("headline.svg", GOOD_SVG.replace("</svg>", line % (30, headline)))
        self.assertNotIn("long-label", rules(report["warnings"]))
        code, report = self.run_look("paragraph.svg", GOOD_SVG.replace("</svg>", line % (30, paragraph)))
        self.assertIn("long-label", rules(report["warnings"]))

    def test_zoom_saves_an_enlarged_region(self):
        code, report = self.run_look("good.svg", GOOD_SVG, "--zoom", "0,0,400,150")
        self.assertEqual(code, 0, report)
        self.assertEqual(len(report["screenshots"]), 2)
        header = Path(report["screenshots"][1]).read_bytes()[16:24]
        self.assertEqual((int.from_bytes(header[:4], "big"), int.from_bytes(header[4:], "big")), (1200, 450))

    def test_bad_zoom_value_is_refused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "good.svg"
        path.write_text(GOOD_SVG, encoding="utf-8")
        self.assertEqual(run_script("look", path, "--zoom", "left half").returncode, 2)

    def test_good_page_passes_at_both_widths(self):
        code, report = self.run_look("good.html", GOOD_PAGE, "--mobile")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["info"]["controls"], 2)
        self.assertGreaterEqual(report["info"]["interactions"], 3)
        self.assertEqual(len(report["screenshots"]), 2)

    def test_bad_page_faults_are_measured_once(self):
        code, report = self.run_look("bad.html", BAD_PAGE, "--mobile")
        self.assertEqual(code, 1)
        self.assertEqual(rules(report["errors"]),
                         ["external-request", "horizontal-overflow", "needs-another-file", "script-error"])
        details = [e["detail"] for e in report["errors"]]
        self.assertEqual(len(details), len(set(details)))
        self.assertEqual(sum(1 for e in report["errors"] if e["rule"] == "script-error"), 1)
        self.assertTrue(any(d.startswith("at phone width: ") for d in details))
        self.assertFalse(any("demystify-look-" in d for d in details))
        self.assertIn("low-contrast", rules(report["warnings"]))

    def test_every_screen_of_a_long_page_is_photographed(self):
        tall = GOOD_PAGE.replace("</main>", "".join(
            "<section style='min-height:900px'><h2>Part %d</h2><p>Text of part %d.</p></section>" % (n, n)
            for n in range(1, 4)) + "</main>")
        code, report = self.run_look("tall.html", tall, "--mobile")
        self.assertEqual(code, 0, report)
        desktop = [s for s in report["screenshots"] if ".desktop-" in s]
        self.assertGreaterEqual(len(desktop), 3)
        sizes = [Path(s).stat().st_size for s in desktop]
        self.assertTrue(all(size > 7000 for size in sizes), sizes)  # a blank screenshot is about 5 KB
        self.assertEqual(len(set(Path(s).read_bytes() for s in desktop)), len(desktop))
        self.assertTrue(any(".mobile" in s for s in report["screenshots"]))

    def test_do_shows_a_state_that_is_not_the_first_view(self):
        code, report = self.run_look("good.html", GOOD_PAGE, "--do", "document.getElementById('take').click()")
        self.assertEqual(code, 0, report)
        first = [s for s in report["screenshots"] if s.endswith(".desktop.png")][0]
        state = [s for s in report["screenshots"] if ".do-1." in s][0]
        self.assertNotEqual(Path(first).read_bytes(), Path(state).read_bytes())

    def test_do_at_phone_width_and_the_size_of_the_page_in_that_state(self):
        code, report = self.run_look("good.html", GOOD_PAGE, "--mobile", "--do", "document.getElementById('take').click()")
        self.assertEqual(code, 0, report)
        state = report["states"][0]
        self.assertEqual([Path(s).name for s in state["screenshots"]], ["good.do-1.png", "good.do-1.mobile.png"])
        self.assertEqual(state["page"], report["info"]["page"])
        self.assertNotIn("page-jumps", rules(report["warnings"]))

    def test_do_code_that_fails_is_an_error(self):
        code, report = self.run_look("good.html", GOOD_PAGE, "--do", "document.getElementById('nope').click()")
        self.assertEqual(code, 1)
        self.assertEqual(rules(report["errors"]), ["do-failed"])

    def test_print_gives_the_value_of_an_expression_in_the_page(self):
        code, report = self.run_look(
            "good.html", GOOD_PAGE,
            "--print", "JSON.stringify(state)",
            "--print", "(document.getElementById('take').click(), state.left)",
            "--print", "new Promise(function (done) { setTimeout(function () { done('later'); }, 20); })")
        self.assertEqual(code, 0, report)
        self.assertEqual([v["value"] for v in report["values"]], ['{"left":10}', "9", "later"])

    def test_print_that_fails_is_an_error(self):
        code, report = self.run_look("good.html", GOOD_PAGE, "--print", "missing.value")
        self.assertEqual(code, 1)
        self.assertEqual(rules(report["errors"]), ["print-failed"])
        self.assertIn("missing", report["errors"][0]["detail"])

    def test_a_page_that_jumps_when_a_control_is_used_gets_a_warning(self):
        jumps = GOOD_PAGE.replace(
            "state.left=Math.max(0,state.left-1);render();",
            "state.left=Math.max(0,state.left-1);render();"
            "document.querySelector('main').insertAdjacentHTML('beforeend','<p>One more line.</p>');")
        code, report = self.run_look("jumps.html", jumps)
        self.assertEqual(code, 0, report)
        found = [w["detail"] for w in report["warnings"] if w["rule"] == "page-jumps"]
        self.assertEqual(len(found), 1, report["warnings"])
        self.assertIn("button#take", found[0])
        self.assertIn("higher", found[0])

    def test_a_state_that_is_higher_than_the_start_gets_a_warning(self):
        code, report = self.run_look(
            "good.html", GOOD_PAGE, "--do",
            "document.querySelector('main').insertAdjacentHTML('beforeend', '<p>One more line.</p>')")
        self.assertEqual(code, 0, report)
        found = [w["detail"] for w in report["warnings"] if w["rule"] == "page-jumps"]
        self.assertEqual(len(found), 1, report["warnings"])
        self.assertIn("after --do 1", found[0])

    def test_a_part_that_opens_is_not_a_jump(self):
        opens = GOOD_PAGE.replace(
            "</main>", "<details><summary>More</summary><p>Hidden text.</p><p>More hidden text.</p></details></main>")
        code, report = self.run_look("opens.html", opens)
        self.assertEqual(code, 0, report)
        self.assertNotIn("page-jumps", rules(report["warnings"]))

    def test_the_copies_of_the_page_have_no_motion(self):
        slow = GOOD_PAGE.replace("</style>", "#left{transition:opacity 30s}#left.gone{opacity:0}</style>")
        code, report = self.run_look(
            "slow.html", slow, "--print",
            "(document.getElementById('left').classList.add('gone'), new Promise(function (done) { "
            "setTimeout(function () { done(getComputedStyle(document.getElementById('left')).opacity); }, 50); }))")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["values"][0]["value"], "0")

    def test_width_gives_the_page_a_window_of_that_width(self):
        code, report = self.run_look("good.html", GOOD_PAGE, "--width", "360")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["info"]["viewport"][0], 360)

    def test_small_text_in_a_picture_gets_a_warning(self):
        picture = ('<svg viewBox="0 0 1200 60" style="display:block;width:100%" role="img" aria-label="a bar">'
                   '<text x="10" y="30" font-size="14">A label in a wide picture</text></svg></main>')
        code, report = self.run_look("small.html", GOOD_PAGE.replace("</main>", picture))
        self.assertEqual(code, 0, report)
        self.assertIn("tiny-text", rules(report["warnings"]))

    def test_sample_text_that_a_script_writes_is_found(self):
        page = GOOD_PAGE.replace("state.left;}", "'EDIT ' + state.left;}")
        code, report = self.run_look("leftover.html", page)
        self.assertEqual(code, 1)
        self.assertEqual(rules(report["errors"]), ["template-text"])

    def test_page_without_controls_gets_a_warning(self):
        page = "<!doctype html><html><head><title>t</title></head><body><p>Only text here.</p></body></html>"
        code, report = self.run_look("static.html", page)
        self.assertEqual(code, 0)
        self.assertIn("no-controls", rules(report["warnings"]))


if __name__ == "__main__":
    unittest.main()
