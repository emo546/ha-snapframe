#!/usr/bin/env python3
"""Testy webového rozhrania – dôraz na cesty prichádzajúce z URL.

Flask konvertor <path:…> prepustí do handlera aj "../..", takže každá routa,
ktorá z URL skladá cestu na disku, to musí ustáť: mazanie, zápis thumbnailu
aj čítanie EXIF idú mimo send_from_directory a jeho safe_join.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapframe" / "rootfs" / "usr" / "bin"))

os.environ.setdefault("SNAPFRAME_ASSET_DIR", str(
    Path(__file__).resolve().parents[1] / "snapframe" / "rootfs" / "usr" / "share" / "snapframe"))

from PIL import Image          # noqa: E402
import webserver               # noqa: E402


class WebTestCase(unittest.TestCase):
    def setUp(self):
        self.root  = Path(tempfile.mkdtemp(prefix="snapframe-test-"))
        self.lib   = self.root / "converted"
        (self.lib / "Rodina").mkdir(parents=True)
        self.outside = self.root / "tajne.txt"
        self.outside.write_text("secret", encoding="utf-8")
        for rel in ("a.jpg", "Rodina/b.jpg"):
            Image.new("RGB", (40, 30), (10, 120, 90)).save(self.lib / rel)

        self._orig = (webserver.OUTPUT_FOLDER, webserver.BASIC_AUTH_USER,
                      webserver.BASIC_AUTH_PASS, webserver.API_TOKEN,
                      webserver.GEOCACHE_FILE)
        webserver.OUTPUT_FOLDER   = str(self.lib)
        webserver.BASIC_AUTH_USER = ""
        webserver.BASIC_AUTH_PASS = ""
        webserver.API_TOKEN       = ""
        webserver.GEOCACHE_FILE   = str(self.root / "geocode.json")
        webserver.app.config["TESTING"] = True
        self.client = webserver.app.test_client()

    def tearDown(self):
        (webserver.OUTPUT_FOLDER, webserver.BASIC_AUTH_USER, webserver.BASIC_AUTH_PASS,
         webserver.API_TOKEN, webserver.GEOCACHE_FILE) = self._orig
        shutil.rmtree(self.root, ignore_errors=True)


class TestPathTraversal(WebTestCase):
    """Cesta z URL nesmie opustiť knižnicu fotiek."""

    ESCAPES = [
        "../tajne.txt",
        "Rodina/../../tajne.txt",
        "..%2ftajne.txt",
        "%2e%2e%2ftajne.txt",
        "../../etc/passwd",
    ]

    def test_delete_cannot_escape_library(self):
        for path in self.ESCAPES:
            with self.subTest(path=path):
                r = self.client.post("/delete/" + path)
                self.assertEqual(r.status_code, 404)
        self.assertTrue(self.outside.exists(), "súbor mimo knižnice bol presunutý")

    def test_photo_and_thumb_cannot_escape_library(self):
        for path in self.ESCAPES:
            with self.subTest(path=path):
                self.assertEqual(self.client.get("/photo/" + path).status_code, 404)
                self.assertEqual(self.client.get("/thumb/" + path).status_code, 404)

    def test_exif_cannot_escape_library(self):
        r = self.client.get("/exif/../tajne.txt")
        self.assertEqual(r.status_code, 404)

    def test_album_listing_cannot_escape_library(self):
        """Nezmyselný album spadne na celú knižnicu – nikdy nie mimo nej."""
        for album in ("../", "..", "../../", "_kos", "/etc"):
            with self.subTest(album=album):
                r = self.client.get("/photos?album=" + album)
                self.assertEqual(r.status_code, 200)
                for name in r.get_json()["photos"]:
                    self.assertTrue((self.lib / name).resolve()
                                    .is_relative_to(self.lib.resolve()))

    def test_upload_cannot_escape_library(self):
        import io
        buf = io.BytesIO()
        Image.new("RGB", (20, 20), (1, 2, 3)).save(buf, "JPEG")
        buf.seek(0)
        r = self.client.post("/upload", data={
            "file":  (buf, "x.jpg"),
            "album": "../../uniknuty",
        }, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        self.assertFalse((self.root.parent / "uniknuty").exists())
        saved = self.lib / r.get_json()["saved"]
        self.assertTrue(saved.resolve().is_relative_to(self.lib.resolve()))


class TestNormalPaths(WebTestCase):
    def test_photo_and_thumb_are_served(self):
        self.assertEqual(self.client.get("/photo/a.jpg").status_code, 200)
        self.assertEqual(self.client.get("/thumb/Rodina/b.jpg").status_code, 200)

    def test_photos_are_listed(self):
        photos = self.client.get("/photos").get_json()["photos"]
        self.assertEqual(sorted(photos), ["Rodina/b.jpg", "a.jpg"])

    def test_album_filter(self):
        photos = self.client.get("/photos?album=Rodina").get_json()["photos"]
        self.assertEqual(photos, ["Rodina/b.jpg"])

    def test_delete_moves_photo_to_trash(self):
        r = self.client.post("/delete/Rodina/b.jpg")
        self.assertEqual(r.status_code, 200)
        self.assertFalse((self.lib / "Rodina" / "b.jpg").exists())
        self.assertTrue((self.lib / "_kos" / "Rodina" / "b.jpg").exists())

    def test_hidden_dirs_are_not_albums(self):
        (self.lib / "_kos").mkdir(exist_ok=True)
        names = [a["name"] for a in self.client.get("/albums").get_json()["albums"]]
        self.assertNotIn("_kos", names)
        self.assertIn("Rodina", names)


class TestAuth(WebTestCase):
    def test_basic_auth_rejects_wrong_password(self):
        webserver.BASIC_AUTH_USER = "admin"
        webserver.BASIC_AUTH_PASS = "tajne"
        self.assertEqual(self.client.get("/photos").status_code, 401)
        ok = self.client.get("/photos", headers={
            "Authorization": "Basic YWRtaW46dGFqbmU=",     # admin:tajne
        })
        self.assertEqual(ok.status_code, 200)

    def test_reads_stay_open_when_token_is_set(self):
        webserver.API_TOKEN = "t0ken"
        self.assertEqual(self.client.get("/photos").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_writes_require_token_when_set(self):
        webserver.API_TOKEN = "t0ken"
        for path in ("/delete/a.jpg", "/scan", "/weather-mode/on", "/waste/config"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path).status_code, 401)
        r = self.client.post("/delete/a.jpg", headers={"X-SnapFrame-Token": "t0ken"})
        self.assertEqual(r.status_code, 200)

    def test_writes_open_when_no_token_configured(self):
        self.assertEqual(self.client.post("/delete/a.jpg").status_code, 200)


class TestPage(WebTestCase):
    def test_index_has_no_unreplaced_placeholders(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("__SNAPFRAME_CFG__", html)
        self.assertNotIn("__ASSET_V__", html)
        self.assertIn("window.SNAPFRAME_CFG", html)

    def test_static_assets_are_served_and_cacheable(self):
        for asset in ("/static/app.js", "/static/app.css"):
            with self.subTest(asset=asset):
                r = self.client.get(asset)
                self.assertEqual(r.status_code, 200)
                self.assertIn("max-age", r.headers.get("Cache-Control", ""))


if __name__ == "__main__":
    unittest.main()
