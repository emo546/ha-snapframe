#!/usr/bin/env python3
"""
SnapFrame – webový server v2.9
Novinky v2.6: multi-language (SK/EN/DE), sleep schedule (čierna obrazovka v noci)
Novinky v2.7: nastavenia v appke – voliteľná hviezdna obloha (namiesto čiernej) počas sleep režimu
Novinky v2.8: weather mode – pohybovým senzorom (cez HA automatizáciu) spúšťaná obrazovka
              s aktuálnym počasím a predpoveďou, vkladaná periodicky medzi fotky
Novinky v2.9: weather mode – hodinová predpoveď na najbližších ~12 h (pás s časom,
              ikonou a teplotou); min/max sa dopočíta z hodinovej predpovede
"""

import os
import re
import json as json_module
import logging
import random as random_module
import time
import urllib.request
from collections import OrderedDict
from pathlib import Path
from datetime import datetime

from flask import Flask, send_from_directory, jsonify, Response, request
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS

log = logging.getLogger("snapframe.web")

# ── Config ────────────────────────────────────────────────────────────────────

def _env_int(key, default):
    try:
        return int(os.environ.get(key, ""))
    except (ValueError, TypeError):
        return default

def _env_str(key, default=""):
    v = os.environ.get(key, "")
    return default if v in ("null", "", None) else v

OUTPUT_FOLDER   = _env_str("OUTPUT_FOLDER",  "/sambamount/converted")
SLIDESHOW_SECS  = _env_int("SLIDESHOW_SECONDS", 30)
WEB_PORT        = _env_int("WEB_PORT",  8099)
JPG_QUALITY     = _env_int("JPG_QUALITY",    92)
THUMB_QUALITY   = _env_int("THUMB_QUALITY",  82)
THUMB_MAX_PX    = _env_int("THUMB_MAX_PX",   1024)
BASIC_AUTH_USER = _env_str("BASIC_AUTH_USER")
BASIC_AUTH_PASS = _env_str("BASIC_AUTH_PASSWORD")
LANGUAGE        = _env_str("LANGUAGE", "sk")          # sk | en | de
SLEEP_START     = _env_str("SLEEP_START", "")         # "23:00" alebo ""
SLEEP_END       = _env_str("SLEEP_END",   "")         # "07:00" alebo ""
WEATHER_PHOTO_INTERVAL   = _env_int("WEATHER_PHOTO_INTERVAL", 8)      # fotiek medzi weather slidmi
WEATHER_MODE_DURATION_MIN = _env_int("WEATHER_MODE_DURATION_MIN", 120)  # min trvania po /weather-mode/on

GEOCACHE_FILE = "/data/geocode_cache.json"
ALLOWED_EXT   = (".jpg", ".jpeg", ".png")

app = Flask(__name__)

# ── Zdieľaný stav ─────────────────────────────────────────────────────────────
try:
    import state as _state
    _has_state = True
except ImportError:
    _has_state = False

# ── LRU Cache (250 položiek) ──────────────────────────────────────────────────
class _LRUCache:
    def __init__(self, maxsize=250):
        self._cache   = OrderedDict()
        self._maxsize = maxsize

    def get(self, key):
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def __contains__(self, key):
        return key in self._cache

_exif_cache    = _LRUCache(maxsize=250)
_geocode_cache = {}

# ── Preklady ──────────────────────────────────────────────────────────────────
TRANSLATIONS = {
    "sk": {
        "app_title":            "Fotorámik",
        "app_subtitle":         "FOTO RÁMIK",
        "scan_btn":             "\u21bb Skenuj teraz",
        "scan_started":         "\u2713 Spusten\u00e9",
        "order_label":          "Poradie fotiek",
        "order_date":           "Chronologicky",
        "order_random":         "N\u00e1hodne",
        "all_photos":           "V\u0161etko",
        "loading_albums":       "Na\u010d\u00edt\u00e1vam albumy\u2026",
        "no_albums":            "\u017diadne albumy (podprie\u010dinky)",
        "upload_toggle":        "\u2191 Nahr\u00e1\u0165 fotky",
        "upload_album_label":   "Cie\u013eov\u00fd album",
        "upload_root":          "Kore\u0148ov\u00fd prie\u010dinok",
        "upload_new_option":    "\u2014 Nov\u00fd album\u2026 \u2014",
        "upload_new_ph":        "N\u00e1zov nov\u00e9ho albumu",
        "upload_files_label":   "S\u00fabory (HEIC, JPG, PNG)",
        "upload_select":        "Vybra\u0165 s\u00fabory\u2026",
        "upload_selected":      "{0} s\u00fabor(y) vybrat\u00fd(ch)",
        "upload_go":            "Nahr\u00e1\u0165",
        "upload_err_files":     "Najprv vyber s\u00fabory.",
        "upload_err_name":      "Zadaj n\u00e1zov nov\u00e9ho albumu.",
        "upload_progress":      "Nahr\u00e1vam {0} / {1}: {2}",
        "upload_done":          "\u2713 {0} fotiek nahrat\u00fdch",
        "upload_errors":        "({0} ch\u00fdb)",
        "upload_gps_hint":      "Pozn\u00e1mka: iOS/Safari pri v\u00fdbere fotiek cez tento formul\u00e1r m\u00f4\u017ee z d\u00f4vodu ochrany s\u00fakromia oreza\u0165 presn\u00fa GPS polohu (ostane len \u0161t\u00e1t/kraj). Pre presn\u00fa polohu nahr\u00e1vaj fotky cez SMB zdie\u013eanie alebo AirDrop/S\u00fabory.",
        "delete_title":         "Odstr\u00e1ni\u0165 t\u00fato fotku?",
        "delete_sub":           "Fotka bude presunut\u00e1 do ko\u0161a",
        "delete_yes":           "Odstr\u00e1ni\u0165",
        "delete_no":            "Zru\u0161i\u0165",
        "no_photos":            "\u017diadne fotky v tomto albume",
        "settings_title":       "Nastavenia",
        "settings_sleep_label": "No\u010dn\u00fd re\u017eim (obrazovka)",
        "theme_black":          "\u010cierna",
        "theme_stars":          "Hviezdna obloha",
        "settings_close":       "Hotovo",
        "weather_high":         "Max",
        "weather_low":          "Min",
        "weather_humidity":     "Vlhkos\u0165",
    },
    "en": {
        "app_title":            "SnapFrame",
        "app_subtitle":         "PHOTO FRAME",
        "scan_btn":             "\u21bb Scan now",
        "scan_started":         "\u2713 Started",
        "order_label":          "Photo order",
        "order_date":           "Chronological",
        "order_random":         "Random",
        "all_photos":           "All photos",
        "loading_albums":       "Loading albums\u2026",
        "no_albums":            "No albums (subfolders)",
        "upload_toggle":        "\u2191 Upload photos",
        "upload_album_label":   "Target album",
        "upload_root":          "Root folder",
        "upload_new_option":    "\u2014 New album\u2026 \u2014",
        "upload_new_ph":        "New album name",
        "upload_files_label":   "Files (HEIC, JPG, PNG)",
        "upload_select":        "Select files\u2026",
        "upload_selected":      "{0} file(s) selected",
        "upload_go":            "Upload",
        "upload_err_files":     "Please select files first.",
        "upload_err_name":      "Please enter an album name.",
        "upload_progress":      "Uploading {0} / {1}: {2}",
        "upload_done":          "\u2713 {0} photos uploaded",
        "upload_errors":        "({0} errors)",
        "upload_gps_hint":      "Note: iOS/Safari may strip the precise GPS location when picking photos through this form, for privacy reasons (only the country/region will be shown). For full location data, upload via SMB share or AirDrop/Files instead.",
        "delete_title":         "Remove this photo?",
        "delete_sub":           "Photo will be moved to trash",
        "delete_yes":           "Remove",
        "delete_no":            "Cancel",
        "no_photos":            "No photos in this album",
        "settings_title":       "Settings",
        "settings_sleep_label": "Night mode (screen)",
        "theme_black":          "Black",
        "theme_stars":          "Starry sky",
        "settings_close":       "Done",
        "weather_high":         "High",
        "weather_low":          "Low",
        "weather_humidity":     "Humidity",
    },
    "de": {
        "app_title":            "SnapFrame",
        "app_subtitle":         "FOTO RAHMEN",
        "scan_btn":             "\u21bb Jetzt scannen",
        "scan_started":         "\u2713 Gestartet",
        "order_label":          "Reihenfolge",
        "order_date":           "Chronologisch",
        "order_random":         "Zuf\u00e4llig",
        "all_photos":           "Alle Fotos",
        "loading_albums":       "Alben werden geladen\u2026",
        "no_albums":            "Keine Alben (Unterordner)",
        "upload_toggle":        "\u2191 Fotos hochladen",
        "upload_album_label":   "Zielalbum",
        "upload_root":          "Stammordner",
        "upload_new_option":    "\u2014 Neues Album\u2026 \u2014",
        "upload_new_ph":        "Name des neuen Albums",
        "upload_files_label":   "Dateien (HEIC, JPG, PNG)",
        "upload_select":        "Dateien ausw\u00e4hlen\u2026",
        "upload_selected":      "{0} Datei(en) ausgew\u00e4hlt",
        "upload_go":            "Hochladen",
        "upload_err_files":     "Bitte zuerst Dateien ausw\u00e4hlen.",
        "upload_err_name":      "Bitte Albumname eingeben.",
        "upload_progress":      "Lade hoch {0} / {1}: {2}",
        "upload_done":          "\u2713 {0} Fotos hochgeladen",
        "upload_errors":        "({0} Fehler)",
        "upload_gps_hint":      "Hinweis: iOS/Safari entfernt beim Ausw\u00e4hlen von Fotos \u00fcber dieses Formular aus Datenschutzgr\u00fcnden m\u00f6glicherweise die genaue GPS-Position (es bleibt nur Land/Region). F\u00fcr die volle Standortgenauigkeit Fotos \u00fcber SMB-Freigabe oder AirDrop/Dateien hochladen.",
        "delete_title":         "Dieses Foto entfernen?",
        "delete_sub":           "Foto wird in den Papierkorb verschoben",
        "delete_yes":           "Entfernen",
        "delete_no":            "Abbrechen",
        "no_photos":            "Keine Fotos in diesem Album",
        "settings_title":       "Einstellungen",
        "settings_sleep_label": "Nachtmodus (Bildschirm)",
        "theme_black":          "Schwarz",
        "theme_stars":          "Sternenhimmel",
        "settings_close":       "Fertig",
        "weather_high":         "Hoch",
        "weather_low":          "Tief",
        "weather_humidity":     "Feuchtigkeit",
    },
}

MONTHS = {
    "sk": ["január","február","marec","apríl","máj","jún",
           "júl","august","september","október","november","december"],
    "en": ["January","February","March","April","May","June",
           "July","August","September","October","November","December"],
    "de": ["Januar","Februar","März","April","Mai","Juni",
           "Juli","August","September","Oktober","November","Dezember"],
}

GEOCODE_LANG = {"sk": "sk,cs,en", "en": "en", "de": "de,en"}

# Preklady Home Assistant weather podmienok (viď https://www.home-assistant.io/integrations/weather/)
WEATHER_CONDITIONS = {
    "sk": {
        "clear-night":     "Jasná obloha",
        "cloudy":          "Zamračené",
        "exceptional":     "Výnimočné počasie",
        "fog":             "Hmla",
        "hail":            "Krupobitie",
        "lightning":       "Búrka",
        "lightning-rainy": "Búrka s dažďom",
        "partlycloudy":    "Polojasno",
        "pouring":         "Vytrvalý dážď",
        "rainy":           "Dážď",
        "snowy":           "Sneženie",
        "snowy-rainy":     "Sneh s dažďom",
        "sunny":           "Jasno",
        "windy":           "Veterno",
        "windy-variant":   "Veterno a oblačno",
    },
    "en": {
        "clear-night":     "Clear night",
        "cloudy":          "Cloudy",
        "exceptional":     "Exceptional",
        "fog":             "Fog",
        "hail":            "Hail",
        "lightning":       "Thunderstorm",
        "lightning-rainy": "Thunderstorm with rain",
        "partlycloudy":    "Partly cloudy",
        "pouring":         "Heavy rain",
        "rainy":           "Rainy",
        "snowy":           "Snowy",
        "snowy-rainy":     "Snow and rain",
        "sunny":           "Sunny",
        "windy":           "Windy",
        "windy-variant":   "Windy and cloudy",
    },
    "de": {
        "clear-night":     "Klare Nacht",
        "cloudy":          "Bewölkt",
        "exceptional":     "Außergewöhnlich",
        "fog":             "Nebel",
        "hail":            "Hagel",
        "lightning":       "Gewitter",
        "lightning-rainy": "Gewitter mit Regen",
        "partlycloudy":    "Teilweise bewölkt",
        "pouring":         "Starkregen",
        "rainy":           "Regnerisch",
        "snowy":           "Schneefall",
        "snowy-rainy":     "Schneeregen",
        "sunny":           "Sonnig",
        "windy":           "Windig",
        "windy-variant":   "Windig und bewölkt",
    },
}

COUNTRY_CODE_SK = {
    "SK":"Slovensko","CZ":"Česko","HU":"Maďarsko","PL":"Poľsko",
    "AT":"Rakúsko","DE":"Nemecko","IT":"Taliansko","FR":"Francúzsko",
    "ES":"Španielsko","PT":"Portugalsko","GR":"Grécko","HR":"Chorvátsko",
    "SI":"Slovinsko","RS":"Srbsko","BA":"Bosna a Hercegovina",
    "ME":"Čierna Hora","MK":"Severné Macedónsko","AL":"Albánsko",
    "RO":"Rumunsko","BG":"Bulharsko","TR":"Turecko","CH":"Švajčiarsko",
    "NL":"Holandsko","BE":"Belgicko","LU":"Luxembursko","DK":"Dánsko",
    "SE":"Švédsko","NO":"Nórsko","FI":"Fínsko","IE":"Írsko",
    "GB":"Spojené kráľovstvo","IS":"Island","MT":"Malta","CY":"Cyprus",
    "AD":"Andorra","MC":"Monako","SM":"San Maríno","LI":"Lichtenštajnsko",
    "UA":"Ukrajina","BY":"Bielorusko","RU":"Rusko","MD":"Moldavsko",
    "GE":"Gruzínsko","AM":"Arménsko","AZ":"Azerbajdžan",
    "LT":"Litva","LV":"Lotyšsko","EE":"Estónsko",
    "US":"Spojené štáty","CA":"Kanada","MX":"Mexiko","BR":"Brazília",
    "AR":"Argentína","CL":"Čile","CO":"Kolumbia","PE":"Peru","CU":"Kuba",
    "MA":"Maroko","DZ":"Alžírsko","TN":"Tunisko","EG":"Egypt",
    "ZA":"Južná Afrika","KE":"Keňa","IL":"Izrael",
    "AE":"Spojené arabské emiráty","TH":"Thajsko","VN":"Vietnam",
    "JP":"Japonsko","CN":"Čína","IN":"India","ID":"Indonézia",
    "PH":"Filipíny","AU":"Austrália",
}

# ── Geocoding cache ───────────────────────────────────────────────────────────

def _load_geocode_cache():
    global _geocode_cache
    try:
        with open(GEOCACHE_FILE, "r", encoding="utf-8") as f:
            raw = json_module.load(f)
        for k, v in raw.items():
            parts = k.split(",")
            if len(parts) == 3:
                _geocode_cache[(float(parts[0]), float(parts[1]), parts[2])] = v
        log.info("Geocache: načítaných {} lokácií".format(len(_geocode_cache)))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("Geocache načítanie zlyhalo: {}".format(e))

def _save_geocode_cache():
    try:
        raw = {"{},{},{}".format(k[0], k[1], k[2]): v for k, v in _geocode_cache.items()}
        with open(GEOCACHE_FILE, "w", encoding="utf-8") as f:
            json_module.dump(raw, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("Geocache uloženie zlyhalo: {}".format(e))

# ── EXIF helpers ──────────────────────────────────────────────────────────────

def _load_exif(path: Path):
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    cache_key = (str(path), mtime)
    cached = _exif_cache.get(cache_key)
    if cached is not None:
        return cached
    result = {"date": None, "gps": None}
    try:
        img  = Image.open(path)
        exif = img.getexif()
        if exif:
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
                    try:
                        result["date"] = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                        break
                    except ValueError:
                        pass
            gps_ifd = exif.get_ifd(0x8825)
            if gps_ifd:
                lat_ref = gps_ifd.get(1); lat = gps_ifd.get(2)
                lon_ref = gps_ifd.get(3); lon = gps_ifd.get(4)
                if all([lat_ref, lat, lon_ref, lon]):
                    def to_deg(val):
                        d, m, s = val
                        return float(d) + float(m) / 60.0 + float(s) / 3600.0
                    lat_deg = to_deg(lat); lon_deg = to_deg(lon)
                    if lat_ref == "S": lat_deg = -lat_deg
                    if lon_ref == "W": lon_deg = -lon_deg
                    result["gps"] = (lat_deg, lon_deg)
    except Exception as e:
        log.debug("EXIF chyba {}: {}".format(path.name, e))
    _exif_cache.set(cache_key, result)
    return result

def get_exif_date(path: Path):
    return _load_exif(path).get("date")

def get_gps_coords(path: Path):
    return _load_exif(path).get("gps")

def reverse_geocode(lat, lon, lang):
    key = (round(lat, 2), round(lon, 2), lang)
    if key in _geocode_cache:
        return _geocode_cache[key]
    result = ""
    try:
        accept_lang = GEOCODE_LANG.get(lang, "en")
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            "?format=json&lat={}&lon={}&zoom=10&accept-language={}".format(lat, lon, accept_lang)
        )
        req = urllib.request.Request(url, headers={"User-Agent": "SnapFrame/2.6"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json_module.loads(resp.read().decode("utf-8"))
        address = data.get("address", {})
        place   = (address.get("city") or address.get("town") or
                   address.get("village") or address.get("county") or "")
        if lang == "sk":
            cc      = address.get("country_code", "").upper()
            country = COUNTRY_CODE_SK.get(cc, address.get("country", ""))
        else:
            country = address.get("country", "")
        result = "{}, {}".format(place, country) if place and country else (place or country or "")
    except Exception as e:
        log.debug("Geocoding chyba ({}, {}): {}".format(lat, lon, e))
    _geocode_cache[key] = result
    _save_geocode_cache()
    return result

# ── Foto helpers ──────────────────────────────────────────────────────────────

def list_albums():
    folder = Path(OUTPUT_FOLDER)
    if not folder.exists():
        return []
    HIDDEN = {"_kos", "_thumbs"}
    result = []
    for d in sorted(folder.iterdir()):
        if d.is_dir() and d.name not in HIDDEN:
            count = sum(1 for f in d.iterdir()
                        if f.is_file() and f.suffix.lower() in ALLOWED_EXT)
            result.append({"name": d.name, "count": count})
    return result

def list_photos(album=""):
    folder = Path(OUTPUT_FOLDER)
    if not folder.exists():
        return []
    if album and album != "all":
        search = folder / album
        if not search.is_dir():
            return []
        files = [f for f in search.iterdir()
                 if f.is_file() and f.suffix.lower() in ALLOWED_EXT]
    else:
        HIDDEN = {"_kos", "_thumbs"}
        files  = [f for f in folder.rglob("*")
                  if f.is_file() and f.suffix.lower() in ALLOWED_EXT
                  and not any(p in HIDDEN for p in f.relative_to(folder).parts)]
    def sort_key(f):
        d = get_exif_date(f)
        return d.timestamp() if d is not None else f.stat().st_mtime
    files.sort(key=sort_key)
    return [str(f.relative_to(folder)) for f in files]

# ── Thumbnail helper ──────────────────────────────────────────────────────────

def _get_or_create_thumb(filename: str):
    src        = Path(OUTPUT_FOLDER) / filename
    if not src.is_file():
        return None
    thumb_path = Path(OUTPUT_FOLDER) / "_thumbs" / filename
    try:
        if thumb_path.exists() and thumb_path.stat().st_mtime >= src.stat().st_mtime:
            return (str(thumb_path.parent), thumb_path.name)
    except OSError:
        pass
    try:
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(src)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)
    except Exception as e:
        log.warning("Thumbnail chyba {}: {}".format(filename, e))
        if src.is_file():
            return (OUTPUT_FOLDER, filename)
        return None
    return (str(thumb_path.parent), thumb_path.name)

# ── Autentifikácia ────────────────────────────────────────────────────────────

@app.before_request
def check_auth():
    if not BASIC_AUTH_USER:
        return
    auth = request.authorization
    if not auth or auth.username != BASIC_AUTH_USER or auth.password != BASIC_AUTH_PASS:
        return Response("Unauthorized", 401,
                        {"WWW-Authenticate": 'Basic realm="SnapFrame"'})

# ── Upload helpers ────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w\-_.()\s]", "_", name, flags=re.UNICODE)
    return name.strip() or "upload"

def _format_duration(seconds: int) -> str:
    if seconds < 60:   return "{} s".format(seconds)
    if seconds < 3600: return "{} min".format(seconds // 60)
    if seconds < 86400: return "{:.1f} h".format(seconds / 3600)
    return "{:.1f} d".format(seconds / 86400)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/albums")
def albums_route():
    return jsonify({"albums": list_albums()})

@app.route("/photos")
def photos_route():
    album = request.args.get("album", "")
    order = request.args.get("order", "date")
    lst   = list_photos(album)
    if order == "random":
        random_module.shuffle(lst)
    return jsonify({"photos": lst})

@app.route("/thumb/<path:filename>")
def thumb(filename):
    result = _get_or_create_thumb(filename)
    if result is None:
        return ("not found", 404)
    return send_from_directory(result[0], result[1])

@app.route("/album-cover/<path:album>")
def album_cover(album):
    photos = list_photos(album)
    if not photos:
        return ("", 404)
    result = _get_or_create_thumb(photos[0])
    if result is None:
        return ("", 404)
    return send_from_directory(result[0], result[1])

@app.route("/photo/<path:filename>")
def photo(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

@app.route("/exif/<path:filename>")
def exif_route(filename):
    path      = Path(OUTPUT_FOLDER) / filename
    date_str  = ""
    loc_str   = ""
    lang      = LANGUAGE if LANGUAGE in MONTHS else "sk"
    exif_date = get_exif_date(path)
    if exif_date is None and path.exists():
        exif_date = datetime.fromtimestamp(path.stat().st_mtime)
    if exif_date:
        date_str = "{} {}".format(MONTHS[lang][exif_date.month - 1], exif_date.year)
    coords = get_gps_coords(path)
    if coords:
        loc_str = reverse_geocode(coords[0], coords[1], lang)
    return jsonify({"date": date_str, "location": loc_str})

@app.route("/delete/<path:filename>", methods=["POST"])
def delete_photo(filename):
    src = Path(OUTPUT_FOLDER) / filename
    if not src.is_file():
        return jsonify({"ok": False, "error": "not found"}), 404
    kos_dir = Path(OUTPUT_FOLDER) / "_kos" / Path(filename).parent
    kos_dir.mkdir(parents=True, exist_ok=True)
    dest = kos_dir / src.name
    c = 1
    while dest.exists():
        dest = kos_dir / "{}_{}.{}".format(src.stem, c, src.suffix.lstrip("."))
        c += 1
    src.rename(dest)
    thumb_p = Path(OUTPUT_FOLDER) / "_thumbs" / filename
    if thumb_p.exists():
        try: thumb_p.unlink()
        except Exception: pass
    return jsonify({"ok": True})

@app.route("/upload", methods=["POST"])
def upload_file():
    f     = request.files.get("file")
    album = request.form.get("album", "").strip()
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "no file"}), 400
    original_name = _safe_filename(f.filename)
    ext = Path(original_name).suffix.lower()
    target_dir = (Path(OUTPUT_FOLDER) / album) if album else Path(OUTPUT_FOLDER)
    target_dir.mkdir(parents=True, exist_ok=True)
    if ext in (".heic", ".heif"):
        try:
            img  = Image.open(f.stream)
            exif = img.info.get("exif")
            stem = Path(original_name).stem
            dest = target_dir / (stem + ".jpg")
            c = 1
            while dest.exists():
                dest = target_dir / "{}_{}.jpg".format(stem, c); c += 1
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB": img = img.convert("RGB")
            kw = {"quality": JPG_QUALITY, "optimize": True}
            if exif: kw["exif"] = exif
            img.save(dest, "JPEG", **kw)
            return jsonify({"ok": True, "saved": str(dest.relative_to(Path(OUTPUT_FOLDER)))})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    elif ext in (".jpg", ".jpeg", ".png"):
        dest = target_dir / original_name
        c = 1
        while dest.exists():
            dest = target_dir / "{}_{}.{}".format(Path(original_name).stem, c, ext.lstrip("."))
            c += 1
        f.save(str(dest))
        return jsonify({"ok": True, "saved": str(dest.relative_to(Path(OUTPUT_FOLDER)))})
    else:
        return jsonify({"ok": False, "error": "unsupported format"}), 400

@app.route("/scan", methods=["POST"])
def trigger_scan():
    if _has_state:
        _state.request_scan()
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 503

@app.route("/status")
def status_route():
    if not _has_state:
        return jsonify({"error": "state unavailable"}), 503
    s   = _state.get_status()
    now = time.time()
    out = {
        "converted_total": s["converted_total"],
        "scan_pending":    s["scan_pending"],
        "last_scan": None, "last_scan_ago": None,
        "next_scan": None, "next_scan_in":  None,
    }
    if s["last_scan_time"]:
        out["last_scan"]     = datetime.fromtimestamp(s["last_scan_time"]).strftime("%Y-%m-%d %H:%M:%S")
        out["last_scan_ago"] = _format_duration(int(now - s["last_scan_time"]))
    if s["next_scan_time"]:
        out["next_scan"]    = datetime.fromtimestamp(s["next_scan_time"]).strftime("%Y-%m-%d %H:%M:%S")
        out["next_scan_in"] = _format_duration(max(0, int(s["next_scan_time"] - now)))
    ts = _state.get_thumb_status()
    out["thumbs"] = ts
    out["thumbs"]["percent"] = int(100 * ts["done"] / ts["total"]) if ts["running"] and ts["total"] > 0 else (100 if not ts["running"] else 0)
    return jsonify(out)

# ── Weather mode (spúšťané pohybovým senzorom cez HA automatizáciu) ───────────

def _hour_label(dt_str: str) -> str:
    """Z ISO datetime (napr. '2026-07-13T14:00:00+00:00') urobí 'HH:MM'."""
    s = str(dt_str or "")
    try:
        clean = s.replace("Z", "+00:00")
        return datetime.fromisoformat(clean).strftime("%H:%M")
    except (ValueError, TypeError):
        # Fallback: skús vyseknúť hodinu z reťazca "....THH:MM..."
        if "T" in s and len(s) >= 16:
            return s[11:16]
        return ""

def _parse_hourly(raw_list, max_items=12):
    """Spracuj zoznam hodinových predpovedí z HA weather.get_forecasts."""
    if not isinstance(raw_list, (list, tuple)):
        return []
    out = []
    for item in raw_list[:max_items]:
        if not isinstance(item, dict):
            continue
        try:
            temp = round(float(item.get("temperature")), 1)
        except (TypeError, ValueError):
            temp = None
        out.append({
            "time":      _hour_label(item.get("datetime")),
            "temperature": temp,
            "condition": str(item.get("condition") or "")[:40],
        })
    return out

def _parse_weather_payload(raw: dict) -> dict:
    def _num(key):
        try:
            return round(float(raw.get(key)), 1)
        except (TypeError, ValueError):
            return None
    hourly = _parse_hourly(raw.get("hourly"))
    forecast_high = _num("forecast_high")
    forecast_low  = _num("forecast_low")
    # Ak min/max nie sú v payloade, dopočítaj ich z hodinovej predpovede na najbližších 12 h
    hourly_temps = [h["temperature"] for h in hourly if h["temperature"] is not None]
    if forecast_high is None and hourly_temps:
        forecast_high = round(max(hourly_temps), 1)
    if forecast_low is None and hourly_temps:
        forecast_low = round(min(hourly_temps), 1)
    data = {
        "temperature":    _num("temperature"),
        "forecast_high":  forecast_high,
        "forecast_low":   forecast_low,
        "humidity":       _num("humidity"),
        "condition":      str(raw.get("condition") or "")[:40],
        "unit":           str(raw.get("unit") or "°C")[:8],
        "hourly":         hourly,
    }
    return data

@app.route("/weather-mode/on", methods=["POST"])
def weather_mode_on_route():
    if not _has_state:
        return jsonify({"ok": False}), 503
    _state.weather_mode_on(WEATHER_MODE_DURATION_MIN * 60)
    return jsonify({"ok": True, "duration_minutes": WEATHER_MODE_DURATION_MIN})

@app.route("/weather-mode/off", methods=["POST"])
def weather_mode_off_route():
    if not _has_state:
        return jsonify({"ok": False}), 503
    _state.weather_mode_off()
    return jsonify({"ok": True})

@app.route("/weather-update", methods=["POST"])
def weather_update_route():
    if not _has_state:
        return jsonify({"ok": False}), 503
    raw = request.get_json(silent=True)
    if raw is None:
        raw = request.form.to_dict()
    if not raw:
        return jsonify({"ok": False, "error": "no data"}), 400
    _state.set_weather_data(_parse_weather_payload(raw))
    return jsonify({"ok": True})

@app.route("/weather")
def weather_route():
    if not _has_state:
        return jsonify({"active": False, "data": None})
    lang = LANGUAGE if LANGUAGE in TRANSLATIONS else "sk"
    status = _state.get_weather_status()
    status["interval"] = WEATHER_PHOTO_INTERVAL
    if status.get("data"):
        cond = status["data"].get("condition", "")
        status["data"]["condition_label"] = WEATHER_CONDITIONS.get(lang, {}).get(cond, cond)
    return jsonify(status)

# ── HTML ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    html = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<title>SnapFrame</title>
<style>
html, body {
  margin: 0; padding: 0; width: 100%; height: 100%;
  background: #0c0c0c;
  font-family: -apple-system, Helvetica, Arial, sans-serif;
  color: #eee; overflow: hidden;
}
/* ===== VÝBERNÁ OBRAZOVKA ===== */
#screen-select {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  overflow-y: auto; -webkit-overflow-scrolling: touch;
  padding: 48px 24px 48px; -webkit-box-sizing: border-box;
  box-sizing: border-box; text-align: center;
}
.sel-title {
  font-size: 26px; font-weight: 200; letter-spacing: 8px;
  text-transform: uppercase; color: #fff; margin-bottom: 4px;
}
.sel-subtitle {
  font-size: 13px; color: #444; letter-spacing: 2px; margin-bottom: 18px;
}
.top-actions { margin-bottom: 32px; }
.scan-btn {
  background: transparent; border: 1px solid #2a2a2a; border-radius: 6px;
  color: #555; font-size: 12px; letter-spacing: 1px; padding: 7px 16px;
  cursor: pointer; outline: none; -webkit-tap-highlight-color: transparent;
  -webkit-transition: color .15s, border-color .15s; transition: color .15s, border-color .15s;
}
.scan-btn.done { color: #4caf50; border-color: #4caf50; }
.order-label {
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: #555; margin-bottom: 10px;
}
.order-row {
  display: inline-block; border: 1px solid #2a2a2a; border-radius: 8px;
  overflow: hidden; margin-bottom: 40px;
}
.order-btn {
  display: inline-block; padding: 10px 24px; background: transparent;
  border: none; color: #666; font-size: 14px; cursor: pointer; outline: none;
  -webkit-tap-highlight-color: transparent;
  -webkit-transition: background .15s, color .15s; transition: background .15s, color .15s;
}
.order-btn.active { background: #222; color: #fff; }
.album-list {
  text-align: left; max-width: 460px; margin: 0 auto 32px;
}
.album-btn {
  display: block; width: 100%; padding: 15px 18px; margin-bottom: 10px;
  background: #161616; border: 1px solid #242424; border-radius: 10px;
  color: #ddd; font-size: 16px; text-align: left; cursor: pointer; outline: none;
  position: relative; overflow: hidden; -webkit-box-sizing: border-box;
  box-sizing: border-box; -webkit-tap-highlight-color: transparent;
  -webkit-transition: background .15s; transition: background .15s;
  background-size: cover; background-position: center;
}
.album-btn:active { background-color: #222; }
.album-btn.all-btn { border-color: #333; color: #fff; }
.album-btn-overlay {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.62);
}
.album-btn-inner { position: relative; z-index: 1; }
.album-icon { margin-right: 10px; opacity: 0.6; }
.all-icon   { opacity: 0.9; }
.album-count { float: right; color: #999; font-size: 13px; margin-top: 2px; }
.sel-empty { color: #444; font-size: 14px; padding: 20px 0; text-align: center; }
/* ===== UPLOAD ===== */
.upload-toggle {
  background: transparent; border: 1px solid #222; border-radius: 8px;
  color: #555; font-size: 13px; letter-spacing: 1px; padding: 10px 22px;
  cursor: pointer; outline: none; -webkit-tap-highlight-color: transparent;
  margin-bottom: 16px; display: block; width: 100%; max-width: 460px;
  margin-left: auto; margin-right: auto; text-align: center;
  -webkit-box-sizing: border-box; box-sizing: border-box;
}
#upload-section {
  display: none; max-width: 460px; margin: 0 auto 32px;
  background: #111; border: 1px solid #222; border-radius: 12px;
  padding: 20px 18px; text-align: left;
}
.upload-label {
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: #555; margin-bottom: 8px; display: block;
}
.upload-select {
  width: 100%; background: #1c1c1c; border: 1px solid #2c2c2c;
  border-radius: 7px; color: #ccc; font-size: 14px; padding: 10px 12px;
  -webkit-box-sizing: border-box; box-sizing: border-box;
  margin-bottom: 16px; outline: none; -webkit-appearance: none;
}
.upload-file-btn {
  display: block; width: 100%; padding: 12px; background: #1c1c1c;
  border: 1px dashed #333; border-radius: 8px; color: #777;
  font-size: 14px; text-align: center; cursor: pointer;
  -webkit-box-sizing: border-box; box-sizing: border-box;
  margin-bottom: 14px; -webkit-tap-highlight-color: transparent; outline: none;
}
.upload-file-btn.has-files { border-color: #555; color: #bbb; }
#upload-files { display: none; }
.upload-go-btn {
  display: block; width: 100%; padding: 13px;
  background: #1a3a2a; border: 1px solid #2a5a3a; border-radius: 8px;
  color: #5dba7e; font-size: 15px; text-align: center; cursor: pointer;
  outline: none; -webkit-tap-highlight-color: transparent;
  -webkit-box-sizing: border-box; box-sizing: border-box;
  -webkit-transition: background .15s; transition: background .15s;
}
.upload-go-btn:disabled { opacity: 0.4; }
.upload-status {
  margin-top: 12px; font-size: 13px; color: #666; min-height: 20px; text-align: center;
}
.upload-status.ok  { color: #5dba7e; }
.upload-status.err { color: #c0392b; }
.upload-gps-hint {
  font-size: 11px; line-height: 1.5; color: #4a4a4a;
  margin: -4px 0 14px;
}
/* ===== SLIDESHOW ===== */
#screen-slideshow {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  background: #000; display: none;
}
.photo {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  background-position: center center; background-repeat: no-repeat;
  background-size: contain; opacity: 0;
  -webkit-transition: opacity 1.5s ease-in-out, -webkit-transform 1.8s ease-in-out;
  transition: opacity 1.5s ease-in-out, transform 1.8s ease-in-out;
}
.photo.fade-start      { -webkit-transform: scale(1);       transform: scale(1); }
.photo.fade-end        { -webkit-transform: scale(1);       transform: scale(1); }
.photo.zoomin-start    { -webkit-transform: scale(1.0);     transform: scale(1.0); }
.photo.zoomin-end      { -webkit-transform: scale(1.12);    transform: scale(1.12); }
.photo.zoomout-start   { -webkit-transform: scale(1.12);    transform: scale(1.12); }
.photo.zoomout-end     { -webkit-transform: scale(1.0);     transform: scale(1.0); }
.photo.slideleft-start { -webkit-transform: translateX(4%); transform: translateX(4%); }
.photo.slideleft-end   { -webkit-transform: translateX(0);  transform: translateX(0); }
.photo.slideup-start   { -webkit-transform: translateY(4%); transform: translateY(4%); }
.photo.slideup-end     { -webkit-transform: translateY(0);  transform: translateY(0); }
.photo.visible { opacity: 1; }
#photo-counter {
  position: absolute; top: 14px; right: 18px; z-index: 90;
  color: rgba(255,255,255,0.32); font-size: 13px; letter-spacing: 1px;
  pointer-events: none; text-shadow: 0 1px 4px rgba(0,0,0,0.8);
}
#overlay {
  position: absolute; bottom: 18px; left: 18px; right: 18px;
  z-index: 90; pointer-events: none;
}
#overlay-date {
  font-size: 26px; font-weight: 300; line-height: 1.1; letter-spacing: 1px;
  color: rgba(255,255,255,0.80); margin-bottom: 5px;
  text-shadow: 0 2px 10px rgba(0,0,0,0.95), 0 0 24px rgba(0,0,0,0.8);
}
#overlay-location {
  font-size: 36px; font-weight: 200; line-height: 1.1;
  color: rgba(255,255,255,0.93);
  text-shadow: 0 2px 10px rgba(0,0,0,0.95), 0 0 24px rgba(0,0,0,0.8);
}
/* ===== WEATHER SLIDE ===== */
#weather-slide {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0; z-index: 80;
  background: radial-gradient(ellipse at 50% 30%, #16233d 0%, #060810 75%);
  display: none; -webkit-flex-direction: column; flex-direction: column;
  align-items: center; justify-content: center; text-align: center;
  opacity: 0; -webkit-transition: opacity 1s ease-in-out; transition: opacity 1s ease-in-out;
}
#weather-slide.visible { display: -webkit-flex; display: flex; opacity: 1; }
.weather-icon {
  font-size: 92px; line-height: 1; margin-bottom: 4px;
  filter: drop-shadow(0 6px 20px rgba(0,0,0,0.55));
  -webkit-filter: drop-shadow(0 6px 20px rgba(0,0,0,0.55));
}
.weather-temp {
  font-size: 82px; font-weight: 200; letter-spacing: -2px;
  color: #fff; line-height: 1;
}
.weather-cond {
  font-size: 20px; font-weight: 300; letter-spacing: 1px;
  color: rgba(255,255,255,0.62); margin-top: 10px;
}
.weather-range {
  margin-top: 22px; display: -webkit-flex; display: flex; gap: 32px;
  font-size: 15px; letter-spacing: 1px; text-transform: uppercase;
  color: rgba(255,255,255,0.4);
}
.weather-range .val { color: #fff; font-size: 18px; text-transform: none; margin-left: 6px; letter-spacing: 0; }
.weather-hourly {
  margin-top: 34px; display: -webkit-flex; display: flex;
  -webkit-flex-wrap: nowrap; flex-wrap: nowrap; gap: 4px;
  max-width: 94%; overflow: hidden;
}
.weather-hour {
  display: -webkit-flex; display: flex; -webkit-flex-direction: column; flex-direction: column;
  align-items: center; -webkit-flex: 1 1 0; flex: 1 1 0; min-width: 0;
  padding: 12px 4px 11px; border-radius: 12px;
  background: rgba(255,255,255,0.05);
}
.weather-hour .wh-time {
  font-size: 12px; letter-spacing: 0.5px; color: rgba(255,255,255,0.45);
}
.weather-hour .wh-ico  { font-size: 26px; line-height: 1; margin: 7px 0 6px; }
.weather-hour .wh-temp { font-size: 17px; font-weight: 300; color: #fff; }
.weather-date {
  position: absolute; bottom: 26px; left: 0; right: 0; text-align: center;
  font-size: 13px; letter-spacing: 2px; text-transform: uppercase;
  color: rgba(255,255,255,0.26);
}
/* ===== SETTINGS ===== */
.settings-btn {
  position: absolute; top: 18px; right: 18px; z-index: 60;
  width: 38px; height: 38px; border-radius: 50%;
  background: rgba(255,255,255,0.04); border: 1px solid #222;
  color: #555; font-size: 17px; cursor: pointer; outline: none;
  display: -webkit-flex; display: flex; align-items: center; justify-content: center;
  -webkit-tap-highlight-color: transparent;
  -webkit-transition: background .15s, color .15s, border-color .15s;
  transition: background .15s, color .15s, border-color .15s;
}
.settings-btn:active { background: rgba(255,255,255,0.09); color: #999; }
#settings-dialog {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  z-index: 300; background: rgba(0,0,0,0.72); display: none;
}
.settings-box {
  position: absolute; top: 50%; left: 50%;
  -webkit-transform: translate(-50%, -50%); transform: translate(-50%, -50%);
  background: #161616; border: 1px solid #262626; border-radius: 16px;
  padding: 26px 24px 22px; text-align: left; width: 86%; max-width: 380px;
  -webkit-box-sizing: border-box; box-sizing: border-box;
}
.settings-title {
  font-size: 12px; letter-spacing: 2px; text-transform: uppercase;
  color: #666; margin-bottom: 20px; text-align: center;
}
.settings-group { margin-bottom: 22px; }
.settings-group:last-of-type { margin-bottom: 26px; }
.settings-label {
  font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #555; margin-bottom: 10px;
}
.theme-options { display: -webkit-flex; display: flex; gap: 10px; }
.theme-opt {
  -webkit-flex: 1; flex: 1; background: #1c1c1c; border: 1.5px solid #292929;
  border-radius: 12px; padding: 14px 10px 12px; text-align: center;
  cursor: pointer; -webkit-tap-highlight-color: transparent;
  -webkit-transition: border-color .15s, background .15s; transition: border-color .15s, background .15s;
}
.theme-opt.active { border-color: #4a7fd6; background: #1a2333; }
.theme-preview {
  width: 100%; height: 46px; border-radius: 7px; margin-bottom: 8px;
  position: relative; overflow: hidden; background: #050505;
}
.theme-preview.stars-preview {
  background: radial-gradient(ellipse at 50% 20%, #10162a 0%, #050608 70%);
}
.theme-preview .tp-dot {
  position: absolute; border-radius: 50%; background: #fff;
}
.theme-opt-label { font-size: 12px; color: #999; }
.theme-opt.active .theme-opt-label { color: #dce6fb; }
.settings-close {
  display: block; width: 100%; padding: 12px;
  background: #202020; border: 1px solid #2c2c2c; border-radius: 9px;
  color: #ccc; font-size: 15px; text-align: center; cursor: pointer;
  outline: none; -webkit-tap-highlight-color: transparent;
  -webkit-box-sizing: border-box; box-sizing: border-box;
}
/* ===== SLEEP ===== */
#screen-sleep {
  display: none; position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: #000; z-index: 500; overflow: hidden;
}
#screen-sleep.theme-black { background: #000; }
#screen-sleep.theme-stars {
  background: radial-gradient(ellipse at 50% 15%, #0b1224 0%, #04050a 60%, #020204 100%);
}
#starfield-svg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
.sf-star { fill: #fff; }
.sf-star.twinkle { -webkit-animation: sfTwinkle linear infinite; animation: sfTwinkle linear infinite; }
@-webkit-keyframes sfTwinkle {
  0%, 100% { opacity: var(--sf-min, 0.25); }
  50%      { opacity: var(--sf-max, 1); }
}
@keyframes sfTwinkle {
  0%, 100% { opacity: var(--sf-min, 0.25); }
  50%      { opacity: var(--sf-max, 1); }
}
.sf-meteor {
  position: absolute; width: 2px; height: 2px; border-radius: 50%;
  background: #fff; opacity: 0;
  -webkit-animation: sfMeteor 3.2s ease-in forwards;
  animation: sfMeteor 3.2s ease-in forwards;
}
.sf-meteor::before {
  content: ""; position: absolute; top: 1px; right: 1px;
  width: 90px; height: 1.5px; border-radius: 2px;
  background: linear-gradient(to left, rgba(255,255,255,0.9), rgba(255,255,255,0));
  -webkit-transform-origin: right center; transform-origin: right center;
  -webkit-transform: rotate(215deg); transform: rotate(215deg);
}
@-webkit-keyframes sfMeteor {
  0%   { opacity: 0; -webkit-transform: translate(0,0); transform: translate(0,0); }
  8%   { opacity: 1; }
  75%  { opacity: 1; }
  100% { opacity: 0; -webkit-transform: translate(-260px, 190px); transform: translate(-260px, 190px); }
}
@keyframes sfMeteor {
  0%   { opacity: 0; transform: translate(0,0); }
  8%   { opacity: 1; }
  75%  { opacity: 1; }
  100% { opacity: 0; transform: translate(-260px, 190px); }
}
/* ===== DELETE DIALOG ===== */
#delete-dialog {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  z-index: 200; background: rgba(0,0,0,0.68); display: none;
}
.del-box {
  position: absolute; top: 50%; left: 50%;
  -webkit-transform: translate(-50%, -50%); transform: translate(-50%, -50%);
  background: #1c1c1e; border-radius: 14px;
  padding: 30px 26px 24px; text-align: center; min-width: 270px; max-width: 340px;
}
.del-title { font-size: 17px; color: #fff; margin-bottom: 8px; }
.del-sub   { font-size: 13px; color: #888; margin-bottom: 26px; }
.del-yes {
  background: #c0392b; color: #fff; border: none; border-radius: 9px;
  padding: 12px 28px; font-size: 16px; margin-right: 10px;
  cursor: pointer; outline: none; -webkit-tap-highlight-color: transparent;
}
.del-no {
  background: #2c2c2e; color: #ccc; border: none; border-radius: 9px;
  padding: 12px 28px; font-size: 16px;
  cursor: pointer; outline: none; -webkit-tap-highlight-color: transparent;
}
#ss-msg {
  position: absolute; top: 50%; left: 0; right: 0; text-align: center;
  color: #444; font-size: 17px;
  -webkit-transform: translateY(-50%); transform: translateY(-50%); display: none;
}
</style>
</head>
<body>

<!-- SLEEP OVERLAY -->
<div id="screen-sleep">
  <svg id="starfield-svg" xmlns="http://www.w3.org/2000/svg"></svg>
</div>

<!-- SETTINGS DIALOG -->
<div id="settings-dialog" onclick="if(event.target===this){closeSettings();}">
  <div class="settings-box">
    <div class="settings-title" id="t-settings-title"></div>
    <div class="settings-group">
      <div class="settings-label" id="t-settings-sleep-label"></div>
      <div class="theme-options">
        <div class="theme-opt" id="theme-opt-black" onclick="chooseSleepTheme('black')">
          <div class="theme-preview"></div>
          <div class="theme-opt-label" id="t-theme-black"></div>
        </div>
        <div class="theme-opt" id="theme-opt-stars" onclick="chooseSleepTheme('stars')">
          <div class="theme-preview stars-preview">
            <div class="tp-dot" style="width:2px;height:2px;top:10px;left:14px;opacity:.9"></div>
            <div class="tp-dot" style="width:1.5px;height:1.5px;top:22px;left:34px;opacity:.6"></div>
            <div class="tp-dot" style="width:1.5px;height:1.5px;top:8px;left:58px;opacity:.7"></div>
            <div class="tp-dot" style="width:2px;height:2px;top:28px;left:78px;opacity:.85"></div>
            <div class="tp-dot" style="width:1px;height:1px;top:16px;left:96px;opacity:.5"></div>
            <div class="tp-dot" style="width:1.5px;height:1.5px;top:32px;left:120px;opacity:.6"></div>
          </div>
          <div class="theme-opt-label" id="t-theme-stars"></div>
        </div>
      </div>
    </div>
    <button class="settings-close" id="t-settings-close" onclick="closeSettings()"></button>
  </div>
</div>

<!-- VÝBERNÁ OBRAZOVKA -->
<div id="screen-select">
  <button class="settings-btn" onclick="openSettings()">&#9881;</button>
  <div class="sel-title" id="t-app-title"></div>
  <div class="sel-subtitle" id="t-app-subtitle"></div>
  <div class="top-actions">
    <button id="scan-btn" class="scan-btn" onclick="triggerScan()"></button>
  </div>
  <div class="order-label" id="t-order-label"></div>
  <div class="order-row">
    <button class="order-btn active" id="btn-order-date" onclick="setOrder('date')"></button>
    <button class="order-btn"        id="btn-order-rand" onclick="setOrder('random')"></button>
  </div>
  <div class="album-list" id="album-list"></div>
  <button class="upload-toggle" onclick="toggleUpload()" id="t-upload-toggle"></button>
  <div id="upload-section">
    <label class="upload-label" id="t-upload-album-label"></label>
    <select id="upload-album" class="upload-select" onchange="onAlbumChange(this)">
      <option value="" id="t-upload-root"></option>
      <option value="__new__" id="t-upload-new-option"></option>
    </select>
    <input type="text" id="upload-new-album" class="upload-select"
           style="display:none;margin-top:-6px" oninput="onNewAlbumInput(this)">
    <label class="upload-label" id="t-upload-files-label"></label>
    <button class="upload-file-btn" id="upload-file-btn"
            onclick="document.getElementById('upload-files').click()"></button>
    <input type="file" id="upload-files" multiple
           accept=".heic,.heif,.jpg,.jpeg,.png,image/*"
           onchange="onFilesSelected(this)">
    <div class="upload-gps-hint" id="t-upload-gps-hint"></div>
    <button class="upload-go-btn" id="upload-go-btn" onclick="startUpload()"></button>
    <div class="upload-status" id="upload-status"></div>
  </div>
</div>

<!-- SLIDESHOW -->
<div id="screen-slideshow">
  <div class="photo" id="photoA"></div>
  <div class="photo" id="photoB"></div>
  <div id="photo-counter"></div>
  <div id="overlay">
    <div id="overlay-date"></div>
    <div id="overlay-location"></div>
  </div>
  <div id="weather-slide">
    <div class="weather-icon" id="weather-icon"></div>
    <div class="weather-temp" id="weather-temp"></div>
    <div class="weather-cond" id="weather-cond"></div>
    <div class="weather-range" id="weather-range"></div>
    <div class="weather-hourly" id="weather-hourly"></div>
    <div class="weather-date" id="weather-date"></div>
  </div>
  <div id="ss-msg"></div>
  <div id="delete-dialog">
    <div class="del-box">
      <div class="del-title" id="t-del-title"></div>
      <div class="del-sub"   id="t-del-sub"></div>
      <button class="del-yes" id="t-del-yes" onclick="confirmDelete()"></button>
      <button class="del-no"  id="t-del-no"  onclick="hideDeleteDialog()"></button>
    </div>
  </div>
</div>

<script>
// ── Injektované serverom ──────────────────────────────────────────────────────
var TR               = __SNAPFRAME_TR__;
var SLIDESHOW_SECS   = __SLIDESHOW_SECS__;
var SLEEP_START      = "__SLEEP_START__";
var SLEEP_END        = "__SLEEP_END__";
var WEATHER_INTERVAL = __WEATHER_INTERVAL__;

// ── i18n helpers ──────────────────────────────────────────────────────────────
function tr(k)       { return TR[k] || k; }
function trf(k, arr) {
  var s = TR[k] || k;
  for (var i = 0; i < arr.length; i++) { s = s.replace("{" + i + "}", arr[i]); }
  return s;
}

// ── Naplň preložené texty do DOM ──────────────────────────────────────────────
function applyTranslations() {
  document.getElementById("t-app-title").textContent     = tr("app_title");
  document.getElementById("t-app-subtitle").textContent  = tr("app_subtitle");
  document.getElementById("scan-btn").textContent        = tr("scan_btn");
  document.getElementById("t-order-label").textContent   = tr("order_label");
  document.getElementById("btn-order-date").textContent  = tr("order_date");
  document.getElementById("btn-order-rand").textContent  = tr("order_random");
  document.getElementById("t-upload-toggle").textContent = tr("upload_toggle");
  document.getElementById("t-upload-album-label").textContent = tr("upload_album_label");
  document.getElementById("t-upload-root").textContent   = tr("upload_root");
  document.getElementById("t-upload-new-option").textContent  = tr("upload_new_option");
  document.getElementById("upload-new-album").placeholder     = tr("upload_new_ph");
  document.getElementById("t-upload-files-label").textContent = tr("upload_files_label");
  document.getElementById("upload-file-btn").textContent = tr("upload_select");
  document.getElementById("t-upload-gps-hint").textContent = tr("upload_gps_hint");
  document.getElementById("upload-go-btn").textContent   = tr("upload_go");
  document.getElementById("ss-msg").textContent          = tr("no_photos");
  document.getElementById("t-del-title").textContent     = tr("delete_title");
  document.getElementById("t-del-sub").textContent       = tr("delete_sub");
  document.getElementById("t-del-yes").textContent       = tr("delete_yes");
  document.getElementById("t-del-no").textContent        = tr("delete_no");
  document.getElementById("t-settings-title").textContent       = tr("settings_title");
  document.getElementById("t-settings-sleep-label").textContent = tr("settings_sleep_label");
  document.getElementById("t-theme-black").textContent          = tr("theme_black");
  document.getElementById("t-theme-stars").textContent          = tr("theme_stars");
  document.getElementById("t-settings-close").textContent       = tr("settings_close");
}

// ── Settings (sleep theme) ──────────────────────────────────────────────────
var SLEEP_THEME_KEY = "snapframe_sleep_theme";
var sleepTheme = "black";
try {
  var _saved = localStorage.getItem(SLEEP_THEME_KEY);
  if (_saved === "black" || _saved === "stars") { sleepTheme = _saved; }
} catch (e) {}

function openSettings() {
  document.getElementById("settings-dialog").style.display = "block";
  _refreshThemeUI();
}
function closeSettings() {
  document.getElementById("settings-dialog").style.display = "none";
}
function _refreshThemeUI() {
  document.getElementById("theme-opt-black").className = "theme-opt" + (sleepTheme === "black" ? " active" : "");
  document.getElementById("theme-opt-stars").className = "theme-opt" + (sleepTheme === "stars" ? " active" : "");
}
function chooseSleepTheme(theme) {
  sleepTheme = theme;
  try { localStorage.setItem(SLEEP_THEME_KEY, theme); } catch (e) {}
  _refreshThemeUI();
  var el = document.getElementById("screen-sleep");
  el.className = "theme-" + theme;
  if (theme === "stars" && !_starsBuilt) { buildStarfield(); }
}

// ── Star field ────────────────────────────────────────────────────────────────
var _starsBuilt = false;
var _meteorInterval = null;

function buildStarfield() {
  var svg = document.getElementById("starfield-svg");
  if (!svg) { return; }
  var w = window.innerWidth, h = window.innerHeight;
  svg.setAttribute("viewBox", "0 0 " + w + " " + h);
  var ns = "http://www.w3.org/2000/svg";
  var frag = document.createDocumentFragment();
  var count = Math.round((w * h) / 9000);
  count = Math.max(70, Math.min(180, count));
  for (var i = 0; i < count; i++) {
    var x = Math.random() * w;
    var y = Math.random() * h;
    var sizeRoll = Math.random();
    var r = sizeRoll > 0.94 ? (1.6 + Math.random() * 1.1)
          : sizeRoll > 0.75 ? (1.0 + Math.random() * 0.6)
          : (0.45 + Math.random() * 0.5);
    var circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", x.toFixed(1));
    circle.setAttribute("cy", y.toFixed(1));
    circle.setAttribute("r", r.toFixed(2));
    var willTwinkle = Math.random() < 0.55;
    var cls = "sf-star" + (willTwinkle ? " twinkle" : "");
    circle.setAttribute("class", cls);
    var baseOpacity = 0.35 + Math.random() * 0.5;
    if (willTwinkle) {
      var dur = (2.4 + Math.random() * 3.6).toFixed(2);
      var delay = (-1 * Math.random() * 6).toFixed(2);
      circle.style.webkitAnimationDuration = dur + "s";
      circle.style.animationDuration = dur + "s";
      circle.style.webkitAnimationDelay = delay + "s";
      circle.style.animationDelay = delay + "s";
      circle.style.setProperty("--sf-min", Math.max(0.12, baseOpacity - 0.35).toFixed(2));
      circle.style.setProperty("--sf-max", Math.min(1, baseOpacity + 0.4).toFixed(2));
    } else {
      circle.style.opacity = baseOpacity.toFixed(2);
    }
    frag.appendChild(circle);
  }
  svg.innerHTML = "";
  svg.appendChild(frag);
  _starsBuilt = true;
}

function _spawnMeteor() {
  var host = document.getElementById("screen-sleep");
  if (!host || sleepTheme !== "stars" || !_sleeping) { return; }
  var m = document.createElement("div");
  m.className = "sf-meteor";
  m.style.left = (20 + Math.random() * 55) + "%";
  m.style.top  = (5 + Math.random() * 25) + "%";
  host.appendChild(m);
  setTimeout(function() { if (m.parentNode) { m.parentNode.removeChild(m); } }, 3300);
}

function _startMeteorShowerLoop() {
  if (_meteorInterval) { clearInterval(_meteorInterval); }
  _meteorInterval = setInterval(function() {
    if (Math.random() < 0.55) { _spawnMeteor(); }
  }, 9000);
}
function _stopMeteorShowerLoop() {
  if (_meteorInterval) { clearInterval(_meteorInterval); _meteorInterval = null; }
}

// ── Sleep mode ────────────────────────────────────────────────────────────────
function _toMin(t) {
  var p = t.split(":"); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10);
}
var _sleeping = false;

function _startRefreshTimer() {
  refreshTimer = setInterval(function() {
    fetchPhotos(function(newList) {
      if (!newList.length) { return; }
      photos = newList;
      if (currentIndex >= photos.length) { currentIndex = photos.length - 1; }
    });
  }, 5 * 60 * 1000);
}

function checkSleep() {
  var el = document.getElementById("screen-sleep");
  if (!SLEEP_START || !SLEEP_END) { el.style.display = "none"; return; }
  var now = new Date();
  var cur = now.getHours() * 60 + now.getMinutes();
  var s   = _toMin(SLEEP_START);
  var e   = _toMin(SLEEP_END);
  var sleeping = (s < e) ? (cur >= s && cur < e) : (cur >= s || cur < e);
  if (sleeping === _sleeping) { return; }
  _sleeping = sleeping;
  if (sleeping) {
    el.className = "theme-" + sleepTheme;
    el.style.display = "block";
    if (sleepTheme === "stars") {
      if (!_starsBuilt) { buildStarfield(); }
      _startMeteorShowerLoop();
    }
    if (advanceTimer) { clearInterval(advanceTimer); advanceTimer = null; }
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  } else {
    el.style.display = "none";
    _stopMeteorShowerLoop();
    if (slideshowActive && photos.length > 0) {
      startAdvanceTimer();
      _startRefreshTimer();
    }
  }
}
setInterval(checkSleep, 60000);

// ── Helpers ───────────────────────────────────────────────────────────────────
function xhrGet(url, cb) {
  var xhr = new XMLHttpRequest();
  xhr.open("GET", url, true);
  xhr.onreadystatechange = function() {
    if (xhr.readyState === 4) {
      cb(xhr.status === 200 ? null : new Error("HTTP " + xhr.status), xhr.responseText);
    }
  };
  xhr.send();
}
function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function encodePath(p) {
  var parts = p.split("/"), out = [];
  for (var i = 0; i < parts.length; i++) { out.push(encodeURIComponent(parts[i])); }
  return out.join("/");
}

// ── Scan trigger ──────────────────────────────────────────────────────────────
function triggerScan() {
  var btn = document.getElementById("scan-btn");
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "/scan", true);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    btn.textContent = tr("scan_started");
    btn.className = "scan-btn done";
    setTimeout(function() {
      btn.textContent = tr("scan_btn");
      btn.className = "scan-btn";
    }, 3000);
  };
  xhr.send();
}

// ── Výberná obrazovka ─────────────────────────────────────────────────────────
var currentOrder = "date";
var albumNames   = [];

function setOrder(order) {
  currentOrder = order;
  document.getElementById("btn-order-date").className = (order === "date") ? "order-btn active" : "order-btn";
  document.getElementById("btn-order-rand").className = (order === "random") ? "order-btn active" : "order-btn";
}

function loadAlbums() {
  var listEl = document.getElementById("album-list");
  listEl.innerHTML = "<div class='sel-empty'>" + escHtml(tr("loading_albums")) + "</div>";
  xhrGet("/albums", function(err, text) {
    if (err) {
      listEl.innerHTML = "<div class='sel-empty'>" + escHtml(err.message) + "</div>";
      return;
    }
    var data;
    try { data = JSON.parse(text); } catch(e) { return; }
    var albums = data.albums || [];
    albumNames = [];
    for (var i = 0; i < albums.length; i++) { albumNames.push(albums[i].name); }
    var totalCount = 0;
    for (var i = 0; i < albums.length; i++) { totalCount += (albums[i].count || 0); }
    var html = "<button class='album-btn all-btn' onclick='startSlideshow(\"all\")'>"
             + "<div class='album-btn-overlay'></div><div class='album-btn-inner'>"
             + "<span class='album-icon all-icon'>&#9654;</span>"
             + escHtml(tr("all_photos"))
             + "<span class='album-count'>" + totalCount + "</span>"
             + "</div></button>";
    for (var i = 0; i < albums.length; i++) {
      html += "<button class='album-btn' id='album-btn-" + i + "' onclick='startSlideshowIdx(" + i + ")'>"
            + "<div class='album-btn-overlay'></div><div class='album-btn-inner'>"
            + "<span class='album-icon'>&#128193;</span>"
            + escHtml(albums[i].name)
            + "<span class='album-count'>" + (albums[i].count || 0) + "</span>"
            + "</div></button>";
    }
    if (albums.length === 0) {
      html += "<div class='sel-empty'>" + escHtml(tr("no_albums")) + "</div>";
    }
    listEl.innerHTML = html;
    loadAlbumCovers();
    populateUploadAlbums(albums);
  });
}

function loadAlbumCovers() {
  for (var i = 0; i < albumNames.length; i++) {
    (function(name, idx) {
      var btn = document.getElementById("album-btn-" + idx);
      if (!btn) { return; }
      var img = new Image();
      img.onload = function() {
        btn.style.backgroundImage = "url('/album-cover/" + encodeURIComponent(name) + "')";
      };
      img.src = "/album-cover/" + encodeURIComponent(name);
    })(albumNames[i], i);
  }
}

function startSlideshowIdx(i) { startSlideshow(albumNames[i]); }

function goBack() {
  if (advanceTimer) { clearInterval(advanceTimer); advanceTimer = null; }
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  photos = []; currentIndex = -1; activeIsA = true;
  var a = document.getElementById("photoA");
  var b = document.getElementById("photoB");
  a.style.backgroundImage = ""; a.className = "photo";
  b.style.backgroundImage = ""; b.className = "photo";
  document.getElementById("overlay-date").innerHTML     = "";
  document.getElementById("overlay-location").innerHTML = "";
  document.getElementById("photo-counter").innerHTML    = "";
  hideWeatherSlide();
  photosSinceWeather = 0;
  slideshowActive = false;
  document.getElementById("screen-slideshow").style.display = "none";
  document.getElementById("screen-select").style.display    = "";
  loadAlbums();
}

// ── Slideshow ─────────────────────────────────────────────────────────────────
var photos = [], currentIndex = -1, activeIsA = true;
var advanceTimer = null, refreshTimer = null, slideshowActive = false;
var currentAlbum = "";
var EFFECTS = ["fade", "zoomin", "zoomout", "slideleft", "slideup"];

function startSlideshow(album) {
  currentAlbum = album; slideshowActive = true;
  document.getElementById("screen-select").style.display    = "none";
  document.getElementById("screen-slideshow").style.display = "block";
  document.getElementById("ss-msg").style.display           = "none";
  fetchPhotosAndStart();
  _startRefreshTimer();
}

function fetchPhotos(cb) {
  xhrGet("/photos?album=" + encodeURIComponent(currentAlbum) + "&order=" + currentOrder,
    function(err, text) {
      if (err) { if (cb) { cb([]); } return; }
      try { if (cb) { cb(JSON.parse(text).photos || []); } }
      catch(e) { if (cb) { cb([]); } }
    });
}

function fetchPhotosAndStart() {
  fetchPhotos(function(list) {
    photos = list;
    if (!photos.length) {
      document.getElementById("ss-msg").style.display = "block"; return;
    }
    currentIndex = 0; activeIsA = true;
    showPhoto(0); startAdvanceTimer();
  });
}

function pickEffect() { return EFFECTS[Math.floor(Math.random() * EFFECTS.length)]; }

function showPhoto(index) {
  if (!photos.length) { return; }
  hideWeatherSlide();
  var idx      = ((index % photos.length) + photos.length) % photos.length;
  var filename = photos[idx];
  var url      = "/thumb/" + encodePath(filename);
  var nextEl   = activeIsA ? document.getElementById("photoB") : document.getElementById("photoA");
  var prevEl   = activeIsA ? document.getElementById("photoA") : document.getElementById("photoB");
  var effect   = pickEffect();
  nextEl.style.backgroundImage = "url(" + url + ")";
  nextEl.className = "photo " + effect + "-start";
  setTimeout(function() {
    nextEl.className = "photo visible " + effect + "-end";
    prevEl.className = "photo";
  }, 50);
  activeIsA = !activeIsA;
  document.getElementById("photo-counter").innerHTML = (idx + 1) + " / " + photos.length;
  loadExifOverlay(filename);
}

function loadExifOverlay(filename) {
  document.getElementById("overlay-date").innerHTML     = "";
  document.getElementById("overlay-location").innerHTML = "";
  xhrGet("/exif/" + encodePath(filename), function(err, text) {
    if (err) { return; }
    try {
      var data = JSON.parse(text);
      document.getElementById("overlay-date").innerHTML     = escHtml(data.date     || "");
      document.getElementById("overlay-location").innerHTML = escHtml(data.location || "");
    } catch(e) {}
  });
}

function advanceTick() {
  if (weatherModeActive && weatherData && photosSinceWeather >= WEATHER_INTERVAL) {
    photosSinceWeather = 0;
    showWeatherSlide();
    return;
  }
  photosSinceWeather++;
  currentIndex = (currentIndex + 1) % photos.length;
  showPhoto(currentIndex);
}

function startAdvanceTimer() {
  if (advanceTimer) { clearInterval(advanceTimer); }
  advanceTimer = setInterval(advanceTick, SLIDESHOW_SECS * 1000);
}

// ── Weather mode ──────────────────────────────────────────────────────────────
var weatherModeActive   = false;
var weatherData         = null;
var photosSinceWeather  = 0;

var WEATHER_EMOJI = {
  "sunny": "☀️", "clear-night": "🌙",
  "partlycloudy": "⛅", "cloudy": "☁️",
  "fog": "🌫️", "windy": "🌬️", "windy-variant": "🌬️",
  "rainy": "🌧️", "pouring": "🌧️",
  "lightning": "⛈️", "lightning-rainy": "⛈️",
  "hail": "🧊", "snowy": "❄️", "snowy-rainy": "🌨️",
  "exceptional": "⚠️"
};

function fetchWeatherStatus() {
  xhrGet("/weather", function(err, text) {
    if (err) { return; }
    try {
      var data = JSON.parse(text);
      weatherModeActive = !!data.active;
      weatherData = data.data || null;
    } catch (e) {}
  });
}
setInterval(fetchWeatherStatus, 60000);

function showWeatherSlide() {
  var d = weatherData;
  if (!d) { return; }
  document.getElementById("weather-icon").textContent = WEATHER_EMOJI[d.condition] || "🌡️";
  document.getElementById("weather-temp").textContent = (d.temperature != null) ? Math.round(d.temperature) + "°" : "--°";
  document.getElementById("weather-cond").textContent = d.condition_label || "";
  var parts = [];
  if (d.forecast_high != null) {
    parts.push(escHtml(tr("weather_high")) + " <span class=\"val\">" + Math.round(d.forecast_high) + "°</span>");
  }
  if (d.forecast_low != null) {
    parts.push(escHtml(tr("weather_low")) + " <span class=\"val\">" + Math.round(d.forecast_low) + "°</span>");
  }
  document.getElementById("weather-range").innerHTML = parts.join("");
  renderHourly(d.hourly);
  document.getElementById("weather-date").textContent = new Date().toLocaleDateString();
  document.getElementById("overlay-date").innerHTML     = "";
  document.getElementById("overlay-location").innerHTML = "";
  document.getElementById("photo-counter").innerHTML    = "";
  document.getElementById("weather-slide").className = "visible";
}

function renderHourly(hourly) {
  var host = document.getElementById("weather-hourly");
  if (!hourly || !hourly.length) { host.innerHTML = ""; host.style.display = "none"; return; }
  host.style.display = "";
  // Na úzkych obrazovkách zobraz max 6 stĺpcov (každú druhú hodinu), inak až 12
  var maxCols = (window.innerWidth < 640) ? 6 : 12;
  var list = hourly;
  if (list.length > maxCols) {
    var step = Math.ceil(list.length / maxCols);
    var sampled = [];
    for (var i = 0; i < list.length && sampled.length < maxCols; i += step) { sampled.push(list[i]); }
    list = sampled;
  }
  var html = "";
  for (var j = 0; j < list.length; j++) {
    var h = list[j];
    var ico  = WEATHER_EMOJI[h.condition] || "🌡️";
    var temp = (h.temperature != null) ? Math.round(h.temperature) + "°" : "--";
    html += "<div class=\"weather-hour\">"
          + "<div class=\"wh-time\">" + escHtml(h.time || "") + "</div>"
          + "<div class=\"wh-ico\">" + ico + "</div>"
          + "<div class=\"wh-temp\">" + escHtml(temp) + "</div>"
          + "</div>";
  }
  host.innerHTML = html;
}

function hideWeatherSlide() {
  document.getElementById("weather-slide").className = "";
}

// ── Swipe + dlhý tap ──────────────────────────────────────────────────────────
var swipeTouchStartX = 0, swipeTouchStartY = 0;
var longPressTimer = null, longPressFired = false;

document.addEventListener("touchstart", function(e) {
  swipeTouchStartX = e.touches[0].clientX;
  swipeTouchStartY = e.touches[0].clientY;
  longPressFired = false;
  if (slideshowActive) {
    longPressTimer = setTimeout(function() {
      longPressFired = true; showDeleteDialog();
    }, 750);
  }
}, false);

document.addEventListener("touchmove", function(e) {
  if (!longPressTimer) { return; }
  if (Math.abs(e.touches[0].clientX - swipeTouchStartX) > 10 ||
      Math.abs(e.touches[0].clientY - swipeTouchStartY) > 10) {
    clearTimeout(longPressTimer); longPressTimer = null;
  }
}, false);

document.addEventListener("touchend", function(e) {
  if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
  if (longPressFired || !slideshowActive) { return; }
  var dx = e.changedTouches[0].clientX - swipeTouchStartX;
  var dy = e.changedTouches[0].clientY - swipeTouchStartY;
  if (Math.abs(dy) > 80 && Math.abs(dx) < 80) { goBack(); return; }
  if (dx > 80 && Math.abs(dy) < 60) {
    if (advanceTimer) { clearInterval(advanceTimer); }
    currentIndex = ((currentIndex - 1) + photos.length) % photos.length;
    showPhoto(currentIndex); startAdvanceTimer(); return;
  }
  if (dx < -80 && Math.abs(dy) < 60) {
    if (advanceTimer) { clearInterval(advanceTimer); }
    currentIndex = (currentIndex + 1) % photos.length;
    showPhoto(currentIndex); startAdvanceTimer();
  }
}, false);

// ── Mazanie ───────────────────────────────────────────────────────────────────
function showDeleteDialog()  { document.getElementById("delete-dialog").style.display = "block"; }
function hideDeleteDialog()  { document.getElementById("delete-dialog").style.display = "none"; }

function confirmDelete() {
  hideDeleteDialog();
  if (!photos.length) { return; }
  var filename = photos[currentIndex];
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "/delete/" + encodePath(filename), true);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4 || xhr.status !== 200) { return; }
    photos.splice(currentIndex, 1);
    if (!photos.length) {
      document.getElementById("photoA").className = "photo";
      document.getElementById("photoB").className = "photo";
      document.getElementById("photo-counter").innerHTML = "";
      document.getElementById("ss-msg").style.display = "block"; return;
    }
    currentIndex = currentIndex % photos.length;
    document.getElementById("photoA").className = "photo";
    document.getElementById("photoB").className = "photo";
    activeIsA = true; showPhoto(currentIndex);
  };
  xhr.send();
}

// ── Upload ────────────────────────────────────────────────────────────────────
function toggleUpload() {
  var sec = document.getElementById("upload-section");
  sec.style.display = (sec.style.display === "none" || !sec.style.display) ? "block" : "none";
}

function populateUploadAlbums(albums) {
  var sel = document.getElementById("upload-album");
  while (sel.options.length > 2) { sel.remove(1); }
  for (var i = 0; i < albums.length; i++) {
    var opt = document.createElement("option");
    opt.value = albums[i].name; opt.textContent = albums[i].name;
    sel.insertBefore(opt, sel.options[sel.options.length - 1]);
  }
}

function onAlbumChange(sel) {
  var newInput = document.getElementById("upload-new-album");
  if (sel.value === "__new__") {
    newInput.style.display = "block"; newInput.focus();
  } else {
    newInput.style.display = "none"; newInput.value = "";
  }
}

function onNewAlbumInput(input) {
  var v = "", s = input.value;
  for (var i = 0; i < s.length; i++) {
    var c = s[i];
    if (c !== "/" && c !== "\\") { v += c; }
  }
  input.value = v;
}

function _getTargetAlbum() {
  var sel = document.getElementById("upload-album");
  if (sel.value === "__new__") {
    return document.getElementById("upload-new-album").value.trim();
  }
  return sel.value;
}

function onFilesSelected(input) {
  var btn = document.getElementById("upload-file-btn");
  if (input.files && input.files.length > 0) {
    btn.className = "upload-file-btn has-files";
    btn.textContent = trf("upload_selected", [input.files.length]);
  } else {
    btn.className = "upload-file-btn";
    btn.textContent = tr("upload_select");
  }
  document.getElementById("upload-status").innerHTML = "";
  document.getElementById("upload-status").className = "upload-status";
}

function startUpload() {
  var input  = document.getElementById("upload-files");
  var status = document.getElementById("upload-status");
  if (!input.files || !input.files.length) {
    status.innerHTML = tr("upload_err_files"); status.className = "upload-status err"; return;
  }
  var album = _getTargetAlbum();
  if (document.getElementById("upload-album").value === "__new__" && !album) {
    status.innerHTML = tr("upload_err_name"); status.className = "upload-status err"; return;
  }
  document.getElementById("upload-go-btn").disabled = true;
  _uploadNext(input.files, 0, album, 0);
}

function _uploadNext(files, idx, album, errCount) {
  var status = document.getElementById("upload-status");
  if (idx >= files.length) {
    var msg = trf("upload_done", [files.length]);
    if (errCount > 0) { msg += " " + trf("upload_errors", [errCount]); }
    status.innerHTML = msg;
    status.className = "upload-status " + (errCount > 0 ? "err" : "ok");
    document.getElementById("upload-go-btn").disabled = false;
    document.getElementById("upload-files").value = "";
    document.getElementById("upload-file-btn").className   = "upload-file-btn";
    document.getElementById("upload-file-btn").textContent = tr("upload_select");
    loadAlbums(); return;
  }
  status.className = "upload-status";
  status.innerHTML = trf("upload_progress", [idx + 1, files.length, escHtml(files[idx].name)]);
  var fd = new FormData();
  fd.append("file", files[idx]); fd.append("album", album);
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "/upload", true);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    _uploadNext(files, idx + 1, album, errCount + (xhr.status === 200 ? 0 : 1));
  };
  xhr.send(fd);
}

// ── Štart ─────────────────────────────────────────────────────────────────────
applyTranslations();
checkSleep();
loadAlbums();
fetchWeatherStatus();
</script>
</body>
</html>"""
    lang = LANGUAGE if LANGUAGE in TRANSLATIONS else "sk"
    html = html.replace("__SNAPFRAME_TR__",  json_module.dumps(TRANSLATIONS[lang], ensure_ascii=False))
    html = html.replace("__SLIDESHOW_SECS__", str(SLIDESHOW_SECS))
    html = html.replace("__SLEEP_START__",    SLEEP_START)
    html = html.replace("__SLEEP_END__",      SLEEP_END)
    html = html.replace("__WEATHER_INTERVAL__", str(WEATHER_PHOTO_INTERVAL))
    return Response(html, mimetype="text/html; charset=utf-8")


# ── Thumbnail pregenerácia ────────────────────────────────────────────────────

def pregenerate_thumbs():
    HIDDEN = {"_kos", "_thumbs"}
    folder = Path(OUTPUT_FOLDER)
    if not folder.exists():
        return
    all_photos = [
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in ALLOWED_EXT
        and not any(p in HIDDEN for p in f.relative_to(folder).parts)
    ]
    total = len(all_photos)
    if not total:
        return
    log.info("Pregenerácia thumbnailov: {} fotiek".format(total))
    if _has_state:
        _state.thumb_start(total)
    done = 0; skipped = 0
    for src in all_photos:
        filename  = str(src.relative_to(folder))
        thumb_path = folder / "_thumbs" / filename
        try:
            if thumb_path.exists() and thumb_path.stat().st_mtime >= src.stat().st_mtime:
                skipped += 1; done += 1
                if _has_state: _state.thumb_progress(done)
                continue
        except OSError:
            pass
        _get_or_create_thumb(filename)
        done += 1
        if _has_state: _state.thumb_progress(done)
        if done % 50 == 0:
            log.info("Thumbnaile: {}/{} ({} preskočených)".format(done, total, skipped))
    if _has_state:
        _state.thumb_finish()
    log.info("Thumbnaile hotové: {}/{} ({} preskočených)".format(done, total, skipped))


def run_web_server():
    _load_geocode_cache()
    log.info("Spúšťam SnapFrame web server – port: {}, jazyk: {}, sleep: {} – {}".format(
        WEB_PORT, LANGUAGE, SLEEP_START or "off", SLEEP_END or "off"))
    log.info("Weather mode: interval {} fotiek, trvanie {} min po aktivácii".format(
        WEATHER_PHOTO_INTERVAL, WEATHER_MODE_DURATION_MIN))
    if BASIC_AUTH_USER:
        log.info("HTTP Basic Auth aktívna pre: {}".format(BASIC_AUTH_USER))
    from waitress import serve
    serve(app, host="0.0.0.0", port=WEB_PORT, threads=8)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_web_server()
