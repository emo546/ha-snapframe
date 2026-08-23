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
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapframe" / "rootfs" / "usr" / "bin"))

os.environ.setdefault("SNAPFRAME_ASSET_DIR", str(
    Path(__file__).resolve().parents[1] / "snapframe" / "rootfs" / "usr" / "share" / "snapframe"))

from PIL import Image          # noqa: E402
import photoindex              # noqa: E402
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
                      webserver.GEOCACHE_FILE, webserver.THUMB_DIR,
                      webserver.THUMB_CACHE)
        webserver.THUMB_DIR       = str(self.root / "thumbs")
        webserver.THUMB_CACHE     = "addon"
        photoindex._conn  = None
        photoindex.DB_FILE = str(self.root / "index.db")
        photoindex.init()
        webserver.OUTPUT_FOLDER   = str(self.lib)
        webserver.BASIC_AUTH_USER = ""
        webserver.BASIC_AUTH_PASS = ""
        webserver.API_TOKEN       = ""
        webserver.GEOCACHE_FILE   = str(self.root / "geocode.json")
        webserver.app.config["TESTING"] = True
        self.client = webserver.app.test_client()

    def tearDown(self):
        (webserver.OUTPUT_FOLDER, webserver.BASIC_AUTH_USER, webserver.BASIC_AUTH_PASS,
         webserver.API_TOKEN, webserver.GEOCACHE_FILE, webserver.THUMB_DIR,
         webserver.THUMB_CACHE) = self._orig
        if photoindex._conn is not None:
            photoindex._conn.close()
            photoindex._conn = None
        shutil.rmtree(self.root, ignore_errors=True)


class TestWeatherHourLabel(unittest.TestCase):
    """HA posiela hodinovú predpoveď v UTC – _hour_label musí prevádzať do
    lokálnej zóny kontajnera, nielen odseknúť ciferník z UTC reťazca.
    Predtým sa 14:00 UTC v CEST (+02:00) zobrazovalo ako '14:00', teda
    o dve hodiny v minulosti."""

    def setUp(self):
        self._orig_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Bratislava"
        time.tzset()

    def tearDown(self):
        if self._orig_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._orig_tz
        time.tzset()

    def test_utc_offset_is_applied_in_summer(self):
        # CEST je UTC+2 – 14:00 UTC musí byť 16:00 lokálne, nie 14:00.
        self.assertEqual(webserver._hour_label("2026-08-23T14:00:00+00:00"), "16:00")

    def test_z_suffix_is_treated_as_utc(self):
        self.assertEqual(webserver._hour_label("2026-08-23T14:00:00Z"), "16:00")

    def test_already_local_offset_is_respected(self):
        self.assertEqual(webserver._hour_label("2026-08-23T16:00:00+02:00"), "16:00")

    def test_naive_datetime_is_left_unconverted(self):
        # Bez zóny niet čo prevádzať – ostáva ako fallback.
        self.assertEqual(webserver._hour_label("2026-08-23T14:00:00"), "14:00")

    def test_garbage_input_never_raises(self):
        self.assertEqual(webserver._hour_label(""), "")
        self.assertEqual(webserver._hour_label(None), "")
        self.assertEqual(webserver._hour_label("not-a-date"), "")

    def test_hourly_payload_carries_the_raw_iso_time_too(self):
        """Prehliadač na tablete má spoľahlivejšiu lokálnu zónu než kontajner
        (rovnaký princíp ako pri kalendári odpadu) – iso musí prejsť ďalej
        nezmenené, aby si čas vedel prepočítať sám."""
        out = webserver._parse_hourly([
            {"datetime": "2026-08-23T14:00:00+00:00", "temperature": 21.4, "condition": "sunny"},
        ])
        self.assertEqual(out[0]["iso"], "2026-08-23T14:00:00+00:00")
        self.assertEqual(out[0]["time"], "16:00")


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


class TestPhotoScanning(WebTestCase):
    """list_photos/list_albums prešli z Path.iterdir()+is_file()+stat()+resolve()
    (viacero syscallov na súbor, na CIFS teda viacero sieťových ciest tam a späť)
    na os.scandir(), ktorého DirEntry si stat() zapamätá. Toto overuje, že
    výstup zostal rovnaký a že skryté priečinky sa naozaj vôbec neprechádzajú –
    nielen že sa z výsledku vyfiltrujú až po tom, čo sa celé prejdú."""

    def test_hidden_dirs_are_never_descended_into(self):
        deep = self.lib / "_kos" / "vela" / "hlboko"
        deep.mkdir(parents=True)
        Image.new("RGB", (10, 10)).save(deep / "zmazana.jpg")

        real_scandir = webserver.os.scandir
        visited = []

        def spy(path="."):
            visited.append(str(path))
            return real_scandir(path)

        webserver.os.scandir = spy
        try:
            photos = webserver.list_photos("all")
        finally:
            webserver.os.scandir = real_scandir

        self.assertFalse(any("_kos" in p for p in photos))
        self.assertFalse(any(v.endswith("_kos") for v in visited),
                          "_kos sa nemal vôbec prejsť, len preskočiť")

    def test_album_listing_is_not_recursive(self):
        nested = self.lib / "Rodina" / "podpriecinok"
        nested.mkdir()
        Image.new("RGB", (10, 10)).save(nested / "vnutorna.jpg")
        photos = self.client.get("/photos?album=Rodina").get_json()["photos"]
        self.assertEqual(photos, ["Rodina/b.jpg"])

    def test_all_photos_view_still_recurses(self):
        nested = self.lib / "Rodina" / "podpriecinok"
        nested.mkdir()
        Image.new("RGB", (10, 10)).save(nested / "vnutorna.jpg")
        photos = self.client.get("/photos").get_json()["photos"]
        self.assertIn("Rodina/podpriecinok/vnutorna.jpg", photos)

    def test_album_photo_count_ignores_trash(self):
        (self.lib / "_kos").mkdir(exist_ok=True)
        for i in range(5):
            Image.new("RGB", (10, 10)).save(self.lib / "_kos" / "x{}.jpg".format(i))
        albums = self.client.get("/albums").get_json()["albums"]
        by_name = {a["name"]: a["count"] for a in albums}
        self.assertNotIn("_kos", by_name)
        self.assertEqual(by_name.get("Rodina"), 1)

    def test_large_album_lists_every_photo(self):
        big = self.lib / "Velky"
        big.mkdir()
        for i in range(150):
            Image.new("RGB", (10, 10), (i % 255, 0, 0)).save(big / "f{:03d}.jpg".format(i))
        photos = self.client.get("/photos?album=Velky").get_json()["photos"]
        self.assertEqual(len(photos), 150)


class TestThumbnails(WebTestCase):
    def test_thumbs_live_outside_the_photo_library(self):
        self.assertEqual(self.client.get("/thumb/a.jpg").status_code, 200)
        self.assertFalse((self.lib / "_thumbs").exists(),
                         "thumbnail sa zapísal do knižnice fotiek")
        self.assertTrue(list((self.root / "thumbs").rglob("*.jpg")))

    def test_thumb_size_is_quantised(self):
        for requested, expected in ((300, 512), (1024, 1024), (1500, 1600),
                                    (5000, 2048), ("nezmysel", 1024)):
            with self.subTest(requested=requested):
                self.assertEqual(webserver._closest_size(requested), expected)

    def test_requested_width_produces_its_own_variant(self):
        self.assertEqual(self.client.get("/thumb/a.jpg?w=1600").status_code, 200)
        self.assertTrue((self.root / "thumbs" / "1600").exists())

    def test_png_thumb_is_served_as_jpeg(self):
        Image.new("RGB", (40, 30), (5, 5, 5)).save(self.lib / "c.png")
        r = self.client.get("/thumb/c.png")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["Content-Type"].split(";")[0], "image/jpeg")

    def test_delete_removes_the_thumbnail(self):
        self.client.get("/thumb/a.jpg")
        self.assertTrue(list((self.root / "thumbs").rglob("a.jpg*")))
        self.client.post("/delete/a.jpg")
        self.assertFalse(list((self.root / "thumbs").rglob("a.jpg*")))


class TestExif(WebTestCase):
    """EXIF sa číta so zatvoreným súborom – GPS blok sa načítava lenivo,
    takže je to presne to miesto, kde sa dá refaktorom nenápadne prísť o dáta."""

    def _photo_with_gps(self, name="gps.jpg"):
        exif = Image.Exif()
        exif[0x0132] = "2021:07:14 10:11:12"
        exif[0x8825] = {1: "N", 2: (48.0, 8.0, 30.0), 3: "E", 4: (17.0, 6.0, 15.0)}
        path = self.lib / name
        Image.new("RGB", (20, 20), (3, 3, 3)).save(path, "JPEG", exif=exif)
        return path

    def test_date_and_gps_are_read(self):
        path = self._photo_with_gps()
        data = webserver._load_exif(path)
        self.assertEqual(data["date"].year, 2021)
        self.assertAlmostEqual(data["gps"][0], 48.1416666, places=4)
        self.assertAlmostEqual(data["gps"][1], 17.1041666, places=4)

    def test_exif_endpoint_reports_the_date(self):
        self._photo_with_gps()
        data = self.client.get("/exif/gps.jpg").get_json()
        self.assertIn("2021", data["date"])

    def test_gps_survives_a_round_trip_through_the_index(self):
        path = self._photo_with_gps()
        webserver._photo_meta(path)                 # naplní index
        webserver._exif_cache._cache.clear()
        _date, gps, _loc = webserver._photo_meta(path)
        self.assertIsNotNone(gps)
        self.assertAlmostEqual(gps[0], 48.1416666, places=4)


class TestPhotoIndex(WebTestCase):
    def test_listing_does_not_reopen_indexed_photos(self):
        """Druhý výpis už nesmie siahať na súbory – to je celý zmysel indexu."""
        webserver.pregenerate_thumbs()
        opened = []
        real_open = webserver.Image.open

        def counting_open(path, *a, **kw):
            opened.append(str(path))
            return real_open(path, *a, **kw)

        webserver.Image.open = counting_open
        try:
            webserver._exif_cache._cache.clear()
            self.client.get("/photos")
        finally:
            webserver.Image.open = real_open
        self.assertEqual(opened, [])

    def test_changed_photo_is_reindexed(self):
        self.client.get("/photos")
        row = photoindex.get("a.jpg", (self.lib / "a.jpg").stat().st_mtime)
        self.assertIsNotNone(row)
        os.utime(self.lib / "a.jpg", (1, 1))
        self.assertIsNone(photoindex.get("a.jpg", 1))

    def test_deleted_photo_is_pruned(self):
        webserver.pregenerate_thumbs()
        self.assertIn("a.jpg", photoindex.all_dates())
        self.client.post("/delete/a.jpg")
        self.assertNotIn("a.jpg", photoindex.all_dates())


class TestAuth(WebTestCase):
    def test_basic_auth_rejects_wrong_password(self):
        webserver.BASIC_AUTH_USER = "admin"
        webserver.BASIC_AUTH_PASS = "tajne"
        self.assertEqual(self.client.get("/photos").status_code, 401)
        ok = self.client.get("/photos", headers={
            "Authorization": "Basic YWRtaW46dGFqbmU=",     # admin:tajne
        })
        self.assertEqual(ok.status_code, 200)

    def test_health_probe_stays_open(self):
        """Watchdog Supervisora nemá prihlasovacie údaje – nesmie dostať 401."""
        webserver.BASIC_AUTH_USER = "admin"
        webserver.BASIC_AUTH_PASS = "tajne"
        webserver.API_TOKEN       = "t0ken"
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

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
