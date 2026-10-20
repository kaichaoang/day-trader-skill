import json
import os
import re
import unittest

from _load import ROOT

# KC branch: four kc- skills plus two kept from the day-trading pack
SKILLS = ["kc-portfolio", "kc-compliance", "kc-tranches", "kc-morning-report", "trader-news", "trader-alerts"]
REMOVED = ["trader-scanner", "trader-entry", "trader-exit", "trader-timemachine", "trader-risk",
           "trader-budget", "trader-broker", "trader-analyst", "trader-pelosi"]


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


def every_text_file():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "trader")]
        for f in files:
            if f.endswith((".md", ".py", ".json", ".csv", ".txt", ".xml")) or f == "LICENSE":
                yield os.path.join(base, f)


class Repo(unittest.TestCase):
    def test_skill_folders_at_the_root(self):
        found = sorted(d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_frontmatter_name_and_description(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertGreater(len(fm), 200, "%s description is too thin" % s)
            low = " ".join(text.lower().split())
            self.assertIn("not financial advice", low, s)

    def test_no_skill_places_orders(self):
        for s in SKILLS:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertTrue("never plac" in low or "places no" in low or "nothing on this branch places" in low
                            or "never places" in low or "does not place" in low or "places every trade himself" in low, s)

    def test_removed_skills_are_not_referenced_by_kc_skills(self):
        for s in SKILLS:
            if not s.startswith("kc-"):
                continue
            for f in os.listdir(os.path.join(ROOT, s)):
                if os.path.isdir(os.path.join(ROOT, s, f)):
                    continue
                with open(os.path.join(ROOT, s, f), encoding="utf-8") as fh:
                    text = fh.read()
                for old in REMOVED:
                    self.assertNotIn(old, text, "%s/%s" % (s, f))

    def test_plugin_manifest(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            plugin = json.load(fh)
        self.assertEqual(plugin["skills"], "./")
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            market = json.load(fh)
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])

    def test_real_holdings_stay_out_of_git(self):
        with open(os.path.join(ROOT, ".gitignore")) as fh:
            self.assertIn("trader/", fh.read().split())

    def test_no_em_dashes(self):
        for path in every_text_file():
            rel = os.path.relpath(path, ROOT)
            if rel.startswith(os.path.join("tests", "fixtures")):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                self.assertNotIn(chr(0x2014), fh.read(), rel)

    def test_every_tool_runs_on_python_3_8(self):
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in os.listdir(folder):
                if not f.endswith(".py"):
                    continue
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    src = fh.read()
                for bad in ("import zoneinfo", "from zoneinfo", ".removeprefix(", ".removesuffix("):
                    self.assertNotIn(bad, src, "%s/%s" % (s, f))
                for bad in ("list[", "dict[", "tuple["):
                    self.assertNotRegex(src, r"(?<![\w.\"'])%s" % re.escape(bad), "%s/%s" % (s, f))


if __name__ == "__main__":
    unittest.main()
