#!/usr/bin/env python3
"""Kontroly konfigurácie add-onu, ktoré sa inak zistia až u používateľa:
každá option musí mať schému aj preklady vo všetkých jazykoch."""

import re
import unittest
from pathlib import Path

ROOT   = Path(__file__).resolve().parents[1]
ADDON  = ROOT / "snapframe"
CONFIG = ADDON / "config.yaml"
LANGS  = ("en", "sk", "de")


def _block(text, header):
    """Kľúče prvej úrovne v danej sekcii config.yaml (bez YAML parsera)."""
    out   = []
    inside = False
    for line in text.split("\n"):
        if line.startswith(header + ":"):
            inside = True
            continue
        if inside:
            if line and not line.startswith(" "):
                break
            m = re.match(r"^  ([a-z_0-9]+):", line)
            if m:
                out.append(m.group(1))
    return out


class TestAddonConfig(unittest.TestCase):
    def setUp(self):
        self.text    = CONFIG.read_text(encoding="utf-8")
        self.options = _block(self.text, "options")
        self.schema  = _block(self.text, "schema")

    def test_every_option_has_a_schema_entry(self):
        self.assertTrue(self.options)
        self.assertEqual(sorted(self.options), sorted(self.schema))

    def test_every_option_is_translated(self):
        for lang in LANGS:
            path = ADDON / "translations" / "{}.yaml".format(lang)
            with self.subTest(lang=lang):
                self.assertTrue(path.is_file(), "chýba preklad {}".format(path))
                translated = _block(path.read_text(encoding="utf-8"), "configuration")
                missing = sorted(set(self.options) - set(translated))
                extra   = sorted(set(translated) - set(self.options))
                self.assertEqual(missing, [], "nepreložené options")
                self.assertEqual(extra, [], "preklad pre neexistujúcu option")

    def test_version_has_a_changelog_entry(self):
        version = re.search(r'^version:\s*"?([^"\n]+)"?', self.text, re.M).group(1).strip()
        changelog = (ADDON / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [{}]".format(version), changelog)

    def test_healthcheck_probes_an_unauthenticated_endpoint(self):
        """Health check nemá prihlasovacie údaje – nesmie mieriť na chránenú routu.

        (Kľúč `watchdog:` v config.yaml je zastaraný, add-on linter ho odmieta –
        sondu preto definuje HEALTHCHECK v Dockerfile.)
        """
        dockerfile = (ADDON / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("/health", dockerfile)
        self.assertNotIn("\nwatchdog:", self.text)

    def test_ingress_does_not_repeat_defaults(self):
        """ingress_port ani webui sa pri zapnutom ingresse neuvádzajú."""
        if re.search(r"^ingress:\s*true", self.text, re.M):
            self.assertIsNone(re.search(r"^ingress_port:", self.text, re.M))
            self.assertIsNone(re.search(r"^webui:", self.text, re.M))


if __name__ == "__main__":
    unittest.main()
