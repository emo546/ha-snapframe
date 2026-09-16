#!/usr/bin/env python3
"""Testy HEIC watchera.

macOS necháva na SMB shari vedľa fotky pomocný súbor "._<meno>" (AppleDouble)
aj s príponou pôvodného súboru (napr. "._IMG_0137.HEIC") – watcher ho nesmie
poslať na konverziu ani zmazať, len ho nechať na mieste bez povšimnutia.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapframe" / "rootfs" / "usr" / "bin"))

import watcher   # noqa: E402


class TestScanFolderSkipsAppleDouble(unittest.TestCase):
    """scan_folder() zbiera kandidátov na konverziu – AppleDouble súbory
    (aj v podpriečinku) sa medzi ne nesmú dostať, skutočný HEIC áno."""

    def setUp(self):
        self.root  = Path(tempfile.mkdtemp(prefix="snapframe-watcher-test-"))
        self.watch = self.root / "upload"
        self.watch.mkdir()
        (self.watch / "IMG.HEIC").write_bytes(b"fake heic bytes")
        (self.watch / "._IMG_0137.HEIC").write_bytes(b"fake apple double bytes")
        sub = self.watch / "Album"
        sub.mkdir()
        (sub / "._IMG_0200.HEIC").write_bytes(b"fake apple double bytes")

        self._orig_watch_folder = watcher.WATCH_FOLDER
        watcher.WATCH_FOLDER = str(self.watch)

        # process_file sa v tomto teste nahradí falošnou implementáciou – ide
        # o to, čo scan_folder vôbec vyberie na spracovanie, nie o samotnú
        # (offline nemožnú) HEIC dekódovanie.
        self._orig_process_file = watcher.process_file
        self.processed = []

        def fake_process_file(path, watch_base):
            self.processed.append(path.relative_to(watch_base))
            return True

        watcher.process_file = fake_process_file

    def tearDown(self):
        watcher.WATCH_FOLDER  = self._orig_watch_folder
        watcher.process_file  = self._orig_process_file
        shutil.rmtree(self.root, ignore_errors=True)

    def test_apple_double_heic_is_never_selected(self):
        converted = watcher.scan_folder()
        self.assertEqual(converted, 1)
        self.assertEqual(self.processed, [Path("IMG.HEIC")])

    def test_apple_double_in_subfolder_is_never_selected(self):
        (self.watch / "Album" / "IMG2.HEIC").write_bytes(b"fake heic bytes")
        watcher.scan_folder()
        self.assertNotIn(Path("Album/._IMG_0200.HEIC"), self.processed)
        self.assertIn(Path("Album/IMG2.HEIC"), self.processed)


class TestProcessFileIgnoresAppleDouble(unittest.TestCase):
    """process_file() sám o sebe musí AppleDouble súbor odmietnuť skôr, než
    sa čokoľvek pokúsi otvoriť ako obrázok, a nesmie sa ho ani dotknúť."""

    def setUp(self):
        self.root  = Path(tempfile.mkdtemp(prefix="snapframe-watcher-test-"))
        self.watch = self.root / "upload"
        self.watch.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_apple_double_file_is_left_untouched(self):
        src = self.watch / "._IMG_0137.HEIC"
        src.write_bytes(b"fake apple double bytes")
        result = watcher.process_file(src, self.watch)
        self.assertFalse(result)
        self.assertTrue(src.exists(), "AppleDouble súbor sa nesmel zmazať")
        self.assertEqual(src.read_bytes(), b"fake apple double bytes")


if __name__ == "__main__":
    unittest.main()
