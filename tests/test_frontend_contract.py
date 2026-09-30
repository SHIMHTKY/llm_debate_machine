"""Asset/DOM contracts for the native frontend, independent of real model data."""

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import parse_qs, urlsplit


FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


class IndexParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.assets = []
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        for name in ("href", "src"):
            if attrs.get(name, "").startswith("/assets/"):
                self.assets.append(attrs[name])
        if tag == "button":
            self.buttons.append(attrs)


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = IndexParser()
        cls.index.feed((FRONTEND / "index.html").read_text(encoding="utf-8"))

    def test_unique_dom_ids(self):
        duplicates = [name for name, count in Counter(self.index.ids).items() if count > 1]
        self.assertEqual(duplicates, [])

    def test_static_script_ids_still_exist(self):
        referenced = set()
        for name in ("motion.js", "app.js", "shell.js"):
            source = (FRONTEND / name).read_text(encoding="utf-8")
            referenced.update(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', source))
        self.assertEqual(referenced - set(self.index.ids), set())

    def test_assets_exist_and_share_cache_version(self):
        imports = re.findall(r'@import url\("([^"\n]+)"\)', (FRONTEND / "styles.css").read_text())
        self.assertEqual(len(imports), 5)
        versions = set()
        for url in self.index.assets + imports:
            parsed = urlsplit(url)
            path = parsed.path.removeprefix("/assets/").removeprefix("./")
            self.assertTrue((FRONTEND / path).is_file(), path)
            version = parse_qs(parsed.query).get("v")
            self.assertTrue(version, url)
            versions.add(version[0])
        self.assertEqual(len(versions), 1, versions)

    def test_static_icon_controls_are_named(self):
        for button in self.index.buttons:
            if "icon-button" in button.get("class", "").split():
                self.assertTrue(button.get("aria-label"), button.get("id"))

    def test_motion_runtime_precedes_business_script(self):
        scripts = [urlsplit(url).path for url in self.index.assets if urlsplit(url).path.endswith(".js")]
        self.assertLess(scripts.index("/assets/motion.js"), scripts.index("/assets/app.js"))

    def test_non_submit_buttons_cannot_submit_debate(self):
        for button in self.index.buttons:
            expected_type = "submit" if button.get("id") == "startDebateBtn" else "button"
            self.assertEqual(button.get("type"), expected_type, button.get("id"))

    def test_preview_server_is_standalone(self):
        import frontend_preview

        populated = frontend_preview.make_settings()
        self.assertEqual(len(populated["debater_presets"]), 2)
        self.assertIn("127.0.0.1.invalid", populated["model_suppliers"][0]["base_url"])


if __name__ == "__main__":
    unittest.main()
