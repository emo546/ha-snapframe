#!/usr/bin/env python3
"""
HEIC -> JPG watcher v2.
Rekurzívne sleduje WATCH_FOLDER vrátane podpriečinkov.
Zachováva štruktúru podpriečinkov v OUTPUT_FOLDER.
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path

from PIL import Image, ImageOps
import pillow_heif

import state

pillow_heif.register_heif_opener()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("ha-snapframe")

WATCH_FOLDER           = os.environ.get("WATCH_FOLDER",  "/sambamount/upload")
OUTPUT_FOLDER          = os.environ.get("OUTPUT_FOLDER", "/sambamount/converted")
DELETE_ORIGINAL        = os.environ.get("DELETE_ORIGINAL", "true").lower() == "true"
JPG_QUALITY            = int(os.environ.get("JPG_QUALITY", "92"))
STABLE_WAIT_SECONDS    = 5
SCAN_INTERVAL_SECONDS  = int(os.environ.get("SCAN_INTERVAL_SECONDS", str(12 * 60 * 60)))


def is_file_stable(path: Path, wait_seconds: int = STABLE_WAIT_SECONDS) -> bool:
    try:
        size1 = path.stat().st_size
    except FileNotFoundError:
        return False
    time.sleep(wait_seconds)
    try:
        size2 = path.stat().st_size
    except FileNotFoundError:
        return False
    return size1 == size2 and size1 > 0


def convert_heic_to_jpg(src: Path, output_folder: Path, quality: int) -> Path:
    img  = Image.open(src)
    exif = img.info.get("exif")

    dest_name = src.stem + ".jpg"
    dest      = output_folder / dest_name

    counter = 1
    while dest.exists():
        dest = output_folder / "{}_{}.jpg".format(src.stem, counter)  # OPRAVENÉ: bez medzery
        counter += 1

    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    save_kwargs = {"quality": quality, "optimize": True}
    if exif:
        save_kwargs["exif"] = exif

    img.save(dest, "JPEG", **save_kwargs)
    return dest


def process_file(path: Path, watch_base: Path) -> bool:
    """Spracuje jeden HEIC súbor. Vráti True ak úspešne skonvertovaný."""
    if path.suffix.lower() not in (".heic", ".heif"):
        return False

    log.info("Nájdený HEIC: {}".format(path.relative_to(watch_base)))

    if not is_file_stable(path):
        log.warning("Súbor {} sa ešte mení, preskakujem".format(path.name))
        return False

    rel           = path.relative_to(watch_base)
    output_subdir = Path(OUTPUT_FOLDER) / rel.parent
    output_subdir.mkdir(parents=True, exist_ok=True)

    try:
        dest = convert_heic_to_jpg(path, output_subdir, JPG_QUALITY)
        log.info("Skonvertované: {} -> {}".format(rel, dest.relative_to(Path(OUTPUT_FOLDER))))
    except Exception as e:
        log.error("Chyba pri konverzii {}: {}".format(path.name, e))
        return False

    if DELETE_ORIGINAL:
        try:
            path.unlink()
            log.info("Originál zmazaný: {}".format(path.name))
        except Exception as e:
            log.error("Nepodarilo sa zmazať originál {}: {}".format(path.name, e))

    return True


def scan_folder() -> int:
    """Rekurzívne prejdi WATCH_FOLDER, spracuj HEIC súbory. Vráti počet skonvertovaných."""
    folder = Path(WATCH_FOLDER)
    if not folder.exists():
        log.warning("Priečinok {} NEEXISTUJE".format(WATCH_FOLDER))
        return 0

    all_heic = [
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in (".heic", ".heif")
    ]

    if not all_heic:
        log.info("Žiadne nové HEIC/HEIF súbory")
        return 0

    log.info("Nájdených {} HEIC/HEIF súborov".format(len(all_heic)))
    converted = 0
    for f in all_heic:
        if process_file(f, folder):
            converted += 1
    return converted


def main():
    log.info("Spúšťam HEIC watcher v2")
    log.info("Sledujem (rekurzívne): {}".format(WATCH_FOLDER))
    log.info("Výstup: {}".format(OUTPUT_FOLDER))
    log.info("Mazať originály: {}".format(DELETE_ORIGINAL))
    log.info("JPG kvalita: {}".format(JPG_QUALITY))
    log.info("Interval: {} s ({:.1f} h)".format(SCAN_INTERVAL_SECONDS, SCAN_INTERVAL_SECONDS / 3600))

    Path(WATCH_FOLDER).mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)

    try:
        import webserver
        web_thread = threading.Thread(target=webserver.run_web_server, daemon=True)
        web_thread.start()
        log.info("Web server vlákno spustené")
    except Exception as e:
        log.error("Nepodarilo sa spustiť web server: {}".format(e))

    while True:
        log.info("Kontrolujem priečinok...")
        converted = scan_folder()
        next_scan = time.time() + SCAN_INTERVAL_SECONDS
        state.update_after_scan(converted, next_scan)
        log.info("Scan hotový, skonvertovaných: {}, ďalší scan o {:.1f} h".format(
            converted, SCAN_INTERVAL_SECONDS / 3600))

        # Pregeneruj chýbajúce thumbnaile na pozadí (neblokuje scan ani web server)
        try:
            import webserver as _ws
            thumb_thread = threading.Thread(target=_ws.pregenerate_thumbs, daemon=True)
            thumb_thread.start()
        except Exception as e:
            log.warning("Pregenerácia thumbnailov zlyhala: {}".format(e))

        # Čakaj na interval, ale reaguj na manuálny /scan trigger každých 5 s
        deadline = time.time() + SCAN_INTERVAL_SECONDS
        while time.time() < deadline:
            if state.consume_scan_request():
                log.info("Manuálny scan vyžiadaný cez web")
                break
            time.sleep(5)


if __name__ == "__main__":
    main()
