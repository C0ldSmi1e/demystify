"""The rules that keep one skill folder working in every agent.

Each test names the agent or tool that breaks when the rule is not followed.
"""

import ast
import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from helpers import REPO, SCRIPTS, SKILL, load, run_script

check_text = load("check_text")
look = load("look")

SKILL_MD = (SKILL / "SKILL.md").read_text(encoding="utf-8")
STDLIB_SCRIPTS = ["_common", "check_text", "look", "doctor", "narrate", "video"]
WORKER_SCRIPTS = ["_kokoro_worker", "_frames_worker"]  # these run inside a uv environment


def front_matter(text):
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML front matter"
    return match.group(1)


def top_level_keys(yaml_text):
    return [line.split(":", 1)[0] for line in yaml_text.splitlines() if re.match(r"^[A-Za-z_-]+:", line)]


class FrontMatter(unittest.TestCase):
    def setUp(self):
        self.yaml = front_matter(SKILL_MD)

    def test_only_fields_that_every_agent_and_validator_accepts(self):
        # claude.ai upload and the Agent Skills validator reject argument-hint, disable-model-invocation, ...
        self.assertEqual(sorted(top_level_keys(self.yaml)), ["description", "license", "metadata", "name"])

    def test_name_is_the_folder_and_the_plugin(self):
        name = re.search(r"^name: (\S+)$", self.yaml, re.MULTILINE).group(1)
        plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(name, SKILL.name)
        self.assertEqual(name, plugin["name"])
        self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(name), 64)

    def test_description_is_quoted_short_and_plain(self):
        line = re.search(r"^description: (.*)$", self.yaml, re.MULTILINE).group(1)
        self.assertTrue(line.startswith('"') and line.endswith('"'), "quote it: strict YAML parsers fail on a bare colon")
        text = line[1:-1]
        self.assertLessEqual(len(text), 1024)  # the Agent Skills limit
        self.assertNotRegex(text, r"[<>]")  # the Codex validator rejects angle brackets
        self.assertNotIn('"', text)


class Body(unittest.TestCase):
    def test_under_8000_bytes(self):
        # Codex cuts a skill at 8,000 bytes when a plugin uses the Agent Plugins format.
        self.assertLess(len(SKILL_MD.encode("utf-8")), 8000)

    def test_no_placeholders_that_only_some_agents_replace(self):
        # $ARGUMENTS and $1 stay as literal text in Codex, Gemini CLI, and Copilot. OpenCode runs !`...` and expands @file.
        body = SKILL_MD.split("\n---\n", 1)[1]
        self.assertNotRegex(body, r"\$ARGUMENTS")
        self.assertNotRegex(body, r"\$\d")
        self.assertNotIn("!`", body)
        self.assertNotRegex(body, r"(^|\s)@[\w./-]+")
        self.assertNotRegex(body, r"\$\{CLAUDE_")

    def test_every_file_that_the_skill_names_exists(self):
        named = set()
        for path in [SKILL / "SKILL.md"] + sorted((SKILL / "references").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            named.update(re.findall(r"\b((?:references|assets|scripts)/[\w.-]+\.\w+)", text))
        self.assertGreaterEqual(len(named), 10)
        for relative in sorted(named):
            self.assertTrue((SKILL / relative).is_file(), "%s is named but does not exist" % relative)

    def test_all_four_formats_have_a_reference(self):
        for name in ("text", "diagram", "page", "video"):
            self.assertIn("references/%s.md" % name, SKILL_MD)
            self.assertTrue((SKILL / "references" / (name + ".md")).is_file())

    def test_the_skill_follows_its_own_text_rules(self):
        for path in [SKILL / "SKILL.md"] + sorted((SKILL / "references").glob("*.md")):
            units = check_text.read_units(str(path), 25, 20)
            report = check_text.check(units, 80)
            self.assertTrue(report["ok"], "%s: %s" % (path.name, [f for f in report["findings"] if f["error"]]))


class Folder(unittest.TestCase):
    def test_no_file_that_an_installer_drops_or_breaks(self):
        for path in SKILL.rglob("*"):
            self.assertNotEqual(path.name, "metadata.json", "npx skills does not copy files with this name")
            self.assertFalse(path.is_symlink(), "%s: Codex and gh skill do not copy symbolic links" % path)
        self.assertFalse((REPO / "bin").exists(), "a top-level bin/ blocks the install on claude.ai and Cowork")

    def test_running_the_scripts_leaves_no_files_in_the_skill_folder(self):
        before = sorted(str(p.relative_to(SKILL)) for p in SKILL.rglob("*"))
        with tempfile.TemporaryDirectory() as tmp:
            text = Path(tmp) / "t.md"
            text.write_text("A short line of text for the check.\n", encoding="utf-8")
            project = Path(tmp) / "demystify-out" / "demo"
            for args in (("check_text", text), ("look", text), ("doctor",), ("video", "init", project),
                         ("narrate", project, "--engine", "none"), ("video", "frame", project, "1.0")):
                run_script(*args)
        after = sorted(str(p.relative_to(SKILL)) for p in SKILL.rglob("*"))
        self.assertEqual(before, after)

    def test_skill_is_nested_so_installers_copy_only_the_skill(self):
        self.assertFalse((REPO / "SKILL.md").exists(), "a root SKILL.md makes npx skills copy the whole repository")
        self.assertTrue((REPO / "skills" / "demystify" / "SKILL.md").is_file())

    def test_versions_agree(self):
        plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        skill = re.search(r'^  version: "([^"]+)"$', front_matter(SKILL_MD), re.MULTILINE).group(1)
        gemini = json.loads((REPO / "gemini-extension.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], skill)
        self.assertEqual(plugin["version"], gemini["version"])
        self.assertRegex(plugin["version"], r"^\d+\.\d+\.\d+$")

    def test_marketplace_lists_this_plugin_at_the_repository_root(self):
        market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(len(market["plugins"]), 1)
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])
        self.assertEqual(market["plugins"][0]["source"], "./")
        self.assertEqual(market["name"], plugin["name"])

    def test_license_is_present(self):
        self.assertIn("MIT License", (REPO / "LICENSE").read_text(encoding="utf-8"))


class Scripts(unittest.TestCase):
    def test_scripts_use_only_the_standard_library(self):
        # An agent runs them with the system python3. A missing package would stop the lower formats.
        allowed = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
        for name in STDLIB_SCRIPTS:
            tree = ast.parse((SCRIPTS / (name + ".py")).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [(node.module or "").split(".")[0]]
                for module in modules:
                    if module in STDLIB_SCRIPTS or module == "__future__" or allowed is None:
                        continue  # a sibling script in the same folder is fine
                    self.assertTrue(module in allowed, "%s.py imports %s, which is not in the standard library" % (name, module))

    def test_scripts_parse_as_python_3_8(self):
        for name in STDLIB_SCRIPTS:
            source = (SCRIPTS / (name + ".py")).read_text(encoding="utf-8")
            ast.parse(source, feature_version=(3, 8))

    def test_every_script_is_listed_here(self):
        present = sorted(p.stem for p in SCRIPTS.glob("*.py"))
        self.assertEqual(present, sorted(STDLIB_SCRIPTS + WORKER_SCRIPTS))

    def test_pinned_versions(self):
        common = load("_common")
        self.assertRegex(common.MANIM, r"^manim==\d+\.\d+\.\d+$")
        self.assertRegex(common.KOKORO, r"^kokoro-onnx==\d+\.\d+\.\d+$")
        for item in common.kokoro_files():
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(item["url"].startswith("https://github.com/"))


class Templates(unittest.TestCase):
    def test_sheet_is_valid_xml_and_only_sample_text_is_wrong(self):
        text = (SKILL / "assets" / "sheet.svg").read_text(encoding="utf-8")
        ElementTree.fromstring(text.encode("utf-8"))
        result = look.static_checks(text, True)
        self.assertEqual(result["errors"], [])
        self.assertGreater(len(result["template_text"]), 20)

    def test_page_is_one_offline_file_and_only_sample_text_is_wrong(self):
        text = (SKILL / "assets" / "page.html").read_text(encoding="utf-8")
        result = look.static_checks(text, False)
        self.assertEqual(result["errors"], [])
        self.assertGreater(len(result["template_text"]), 15)

    def test_every_sample_text_in_the_templates_is_marked(self):
        # A sample label without the word EDIT can stay in a result with no warning.
        sheet = (SKILL / "assets" / "sheet.svg").read_text(encoding="utf-8")
        for label in re.findall(r"<text[^>]*>([^<]+)</text>", sheet):
            if re.fullmatch(r"[A-F]|\d+", label.strip()):
                continue  # panel letters and scale numbers
            self.assertIn("EDIT", label, "sheet.svg: %r" % label)
        page = (SKILL / "assets" / "page.html").read_text(encoding="utf-8")
        body = page[page.index("<main>"):page.index("</main>")]
        allowed = {"The picture", "Step by step", "Try it", "Limits", "Terms", "Back", "Next",
                   "Move the picture sideways to see all of it.", "Tested:", "Inferred:", "Not verified:"}
        for label in re.findall(r">([^<>]+)<", body):
            label = " ".join(label.split())
            if label and label not in allowed:
                self.assertIn("EDIT", label, "page.html: %r" % label)

    def test_sample_text_is_reported_once_with_the_text(self):
        result = look.static_checks("<svg xmlns='http://www.w3.org/2000/svg'><text>EDIT: title</text></svg>", True)
        error = look.template_error(result["template_text"] + ["EDIT: title", "5 EDIT left"])
        self.assertEqual(error["rule"], "template-text")
        self.assertEqual(error["detail"].count("EDIT: title"), 1)
        self.assertIn("5 EDIT left", error["detail"])
        self.assertIsNone(look.template_error([]))

    def test_scene_kit_is_valid_python(self):
        source = (SKILL / "assets" / "scene_kit.py").read_text(encoding="utf-8")
        ast.parse(source)
        for name in ("class Explainer", "def beat", "def clear_scene", "def T(", "def M(", "def fit(", "def at("):
            self.assertIn(name, source)

    def test_the_kit_and_the_video_reference_give_the_same_smallest_text(self):
        kit = (SKILL / "assets" / "scene_kit.py").read_text(encoding="utf-8")
        sizes = re.search(r"^TITLE, HEAD, BODY, SMALL = (\d+), (\d+), (\d+), (\d+)$", kit, re.MULTILINE).groups()
        self.assertIn("_SMALLEST_FONT = SMALL", kit)
        reference = (SKILL / "references" / "video.md").read_text(encoding="utf-8")
        self.assertIn("The text sizes: %s." % ", ".join(sizes), reference)
        self.assertIn("Do not show text below size %s." % sizes[3], reference)

    def test_the_page_shell_has_the_arrowheads_that_the_reference_names(self):
        page = (SKILL / "assets" / "page.html").read_text(encoding="utf-8")
        sheet = (SKILL / "assets" / "sheet.svg").read_text(encoding="utf-8")
        diagram = (SKILL / "references" / "diagram.md").read_text(encoding="utf-8")
        for marker in re.findall(r"url\(#([\w-]+)\)", diagram):
            self.assertIn('id="%s"' % marker, sheet, "diagram.md names an arrowhead that sheet.svg does not have")
        for marker in ("arrow", "arrow-accent", "arrow-bad"):
            self.assertIn('<marker id="%s"' % marker, page)


if __name__ == "__main__":
    unittest.main()
