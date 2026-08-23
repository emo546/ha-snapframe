#!/usr/bin/env python3
"""
SnapFrame – webový server v2.10
Novinky v2.6: multi-language (SK/EN/DE), sleep schedule (čierna obrazovka v noci)
Novinky v2.7: nastavenia v appke – voliteľná hviezdna obloha (namiesto čiernej) počas sleep režimu
Novinky v2.8: weather mode – pohybovým senzorom (cez HA automatizáciu) spúšťaná obrazovka
              s aktuálnym počasím a predpoveďou, vkladaná periodicky medzi fotky
Novinky v2.9: weather mode – hodinová predpoveď na najbližších ~12 h (pás s časom,
              ikonou a teplotou); min/max sa dopočíta z hodinovej predpovede
Novinky v2.10: kalendár vývozu odpadu – termíny zvozov sa nastavia priamo v appke
              (pravidlá typu „každý druhý štvrtok“ / „prvý pondelok v mesiaci“ /
              konkrétne dátumy) a deň vopred sa na fotkách zobrazí pripomienka –
              buď štítok v rohu, alebo celoobrazovkový slide medzi fotkami
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
from datetime import date, datetime, timedelta

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
ANTHROPIC_API_KEY = _env_str("ANTHROPIC_API_KEY")   # nepovinné – záloha pre skeny/fotky harmonogramu

GEOCACHE_FILE = "/data/geocode_cache.json"
ALLOWED_EXT   = (".jpg", ".jpeg", ".png")

# HTML/CSS/JS rámu sú súbory, nie reťazce v tomto module – dajú sa lintovať
# a prehliadač na tablete si CSS/JS nakešuje (viď ASSET_VERSION nižšie).
ASSET_DIR = Path(os.environ.get("SNAPFRAME_ASSET_DIR", "/usr/share/snapframe"))

app = Flask(__name__,
            static_folder=str(ASSET_DIR / "static"),
            static_url_path="/static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 30 * 24 * 3600   # ?v=… rieši invalidáciu


def _asset_version() -> str:
    """Najnovší mtime assetov – mení ?v= po každom update add-onu."""
    try:
        newest = max(f.stat().st_mtime for f in ASSET_DIR.rglob("*") if f.is_file())
        return str(int(newest))
    except (OSError, ValueError):
        return "0"


ASSET_VERSION = _asset_version()
_index_cache = {"mtime": None, "html": ""}


def _read_index_html() -> str:
    path = ASSET_DIR / "index.html"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return "<h1>SnapFrame</h1><p>index.html chýba v {}</p>".format(ASSET_DIR)
    if _index_cache["mtime"] != mtime:
        _index_cache["html"]  = path.read_text(encoding="utf-8")
        _index_cache["mtime"] = mtime
    return _index_cache["html"]

# ── Zdieľaný stav ─────────────────────────────────────────────────────────────
try:
    import state as _state
    _has_state = True
except ImportError:
    _has_state = False

try:
    import waste_import as _waste_import
    _has_waste_import = True
except ImportError:               # pragma: no cover
    _has_waste_import = False

try:
    import waste as _waste
    _has_waste = True
except ImportError:               # pragma: no cover – modul je súčasťou image-u
    _has_waste = False
    log.warning("Modul waste.py sa nepodarilo načítať – kalendár odpadu je vypnutý")

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
        # — Kalendár vývozu odpadu —
        "waste_open_btn":       "Vývoz odpadu…",
        "waste_title":          "Vývoz odpadu",
        "waste_enabled_label":  "Pripomienka vývozu",
        "waste_on":             "Zapnuté",
        "waste_off":            "Vypnuté",
        "waste_display_label":  "Ako zobraziť pripomienku",
        "waste_mode_overlay":   "Štítok v rohu",
        "waste_mode_slide":     "Celá obrazovka",
        "waste_mode_both":      "Oboje",
        "waste_interval_label": "Celá obrazovka každých … fotiek",
        "waste_days_label":     "Upozorniť dní vopred",
        "waste_show_on_day":    "Pripomenúť aj v deň vývozu",
        "waste_start_hour":     "Pripomienku zobrazovať až od",
        "waste_rules_label":    "Zvozy",
        "waste_add_rule":       "+ Pridať zvoz",
        "waste_no_rules":       "Zatiaľ nie sú nastavené žiadne zvozy.",
        "waste_type_label":     "Druh odpadu",
        "waste_name_label":     "Vlastný názov (nepovinné)",
        "waste_recurrence":     "Opakovanie",
        "waste_kind_weekly":    "Každý N-tý týždeň",
        "waste_kind_monthly":   "Mesačne",
        "waste_kind_dates":     "Konkrétne dátumy",
        "waste_weekday":        "Deň v týždni",
        "waste_every_weeks":    "Každých … týždňov",
        "waste_anchor":         "Referenčný dátum (jeden zo zvozov)",
        "waste_anchor_hint":    "Podľa neho sa počíta, ktorý týždeň je „ten správny“.",
        "waste_monthly_by":     "Určiť podľa",
        "waste_by_weekday":     "Poradia v mesiaci",
        "waste_by_day":         "Čísla dňa",
        "waste_week_of_month":  "Ktorý týždeň",
        "waste_day_of_month":   "Deň v mesiaci",
        "waste_months":         "Len v mesiacoch (nepovinné)",
        "waste_dates_label":    "Dátumy vývozu",
        "waste_add_date":       "Pridať",
        "waste_valid_from":     "Platí od (nepovinné)",
        "waste_valid_to":       "Platí do (nepovinné)",
        "waste_skip_label":     "Výnimky – v tieto dni sa nevyváža",
        "waste_extra_label":    "Mimoriadne termíny navyše",
        "waste_save":           "Uložiť",
        "waste_cancel":         "Zrušiť",
        "waste_delete":         "Odstrániť",
        "waste_saved":          "✓ Uložené",
        "waste_save_err":       "Uloženie zlyhalo",
        "waste_preview":        "Najbližšie vývozy",
        "waste_preview_none":   "Žiadne naplánované vývozy",
        "waste_today":          "Dnes",
        "waste_tomorrow":       "Zajtra",
        "waste_in_days_few":    "O {0} dni",
        "waste_in_days_many":   "O {0} dní",
        "waste_headline":       "vývoz odpadu",
        "waste_hint":           "Nezabudni večer vyložiť kontajner na ulicu",
        "waste_hint_today":     "Kontajner má byť už na ulici",
        "waste_every_week":     "každý týždeň",
        "waste_every_n_weeks":  "každý {0}. týždeň",
        "waste_dates_one":      "{0} dátum",
        "waste_dates_few":      "{0} dátumy",
        "waste_dates_many":     "{0} dátumov",
        # — Import harmonogramu —
        "wimp_open":            "\u2191 Načítať z harmonogramu…",
        "wimp_title":           "Import harmonogramu",
        "wimp_intro":           "Nahraj PDF alebo fotku obecného rozpisu vývozu. Nič sa neuloží, kým nepotvrdíš.",
        "wimp_pick":            "Vybrať súbor…",
        "wimp_working":         "Spracúvam harmonogram…",
        "wimp_found":           "Nájdené rady vývozov ({0}) · rok {1}",
        "wimp_hint":            "Leták obce často obsahuje viac rozpisov naraz (napr. dvojtýždňový aj mesačný zvoz). Zaškrtni len tie, ktoré platia pre teba.",
        "wimp_use":             "Použiť",
        "wimp_add":             "Pridať vybraté zvozy",
        "wimp_none_selected":   "Vyber aspoň jeden rad.",
        "wimp_added":           "✓ Pridané: {0} zvozov",
        "wimp_err_format":      "Nepodporovaný formát. Nahraj PDF, JPG alebo PNG.",
        "wimp_err_large":       "Súbor je príliš veľký (max 12 MB).",
        "wimp_err_parse":       "V súbore sa nepodarilo nájsť kalendár vývozov.",
        "wimp_err_novision":    "Toto rozloženie parser nepozná. Rozpoznanie z fotky vieš zapnúť doplnením Anthropic API kľúča v konfigurácii add-onu.",
        "wimp_err_generic":     "Import zlyhal.",
        "wimp_via_pdf":         "načítané priamo z PDF",
        "wimp_via_vision":      "rozpoznané z obrázka",
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
        # — Waste collection calendar —
        "waste_open_btn":       "Waste collection…",
        "waste_title":          "Waste collection",
        "waste_enabled_label":  "Collection reminder",
        "waste_on":             "On",
        "waste_off":            "Off",
        "waste_display_label":  "How to show the reminder",
        "waste_mode_overlay":   "Corner badge",
        "waste_mode_slide":     "Full screen",
        "waste_mode_both":      "Both",
        "waste_interval_label": "Full screen every … photos",
        "waste_days_label":     "Remind days ahead",
        "waste_show_on_day":    "Also remind on collection day",
        "waste_start_hour":     "Show the reminder only from",
        "waste_rules_label":    "Collections",
        "waste_add_rule":       "+ Add collection",
        "waste_no_rules":       "No collections configured yet.",
        "waste_type_label":     "Waste type",
        "waste_name_label":     "Custom name (optional)",
        "waste_recurrence":     "Repeats",
        "waste_kind_weekly":    "Every N weeks",
        "waste_kind_monthly":   "Monthly",
        "waste_kind_dates":     "Specific dates",
        "waste_weekday":        "Day of week",
        "waste_every_weeks":    "Every … weeks",
        "waste_anchor":         "Reference date (one collection day)",
        "waste_anchor_hint":    "Used to work out which week is the “right” one.",
        "waste_monthly_by":     "Determined by",
        "waste_by_weekday":     "Position in month",
        "waste_by_day":         "Day number",
        "waste_week_of_month":  "Which week",
        "waste_day_of_month":   "Day of month",
        "waste_months":         "Only in months (optional)",
        "waste_dates_label":    "Collection dates",
        "waste_add_date":       "Add",
        "waste_valid_from":     "Valid from (optional)",
        "waste_valid_to":       "Valid until (optional)",
        "waste_skip_label":     "Exceptions – no collection on",
        "waste_extra_label":    "Extra one-off collections",
        "waste_save":           "Save",
        "waste_cancel":         "Cancel",
        "waste_delete":         "Delete",
        "waste_saved":          "✓ Saved",
        "waste_save_err":       "Saving failed",
        "waste_preview":        "Next collections",
        "waste_preview_none":   "No collections scheduled",
        "waste_today":          "Today",
        "waste_tomorrow":       "Tomorrow",
        "waste_in_days_few":    "In {0} days",
        "waste_in_days_many":   "In {0} days",
        "waste_headline":       "waste collection",
        "waste_hint":           "Remember to put the bin out tonight",
        "waste_hint_today":     "The bin should already be out",
        "waste_every_week":     "every week",
        "waste_every_n_weeks":  "every {0} weeks",
        "waste_dates_one":      "{0} date",
        "waste_dates_few":      "{0} dates",
        "waste_dates_many":     "{0} dates",
        # — Schedule import —
        "wimp_open":            "\u2191 Import from schedule…",
        "wimp_title":           "Import schedule",
        "wimp_intro":           "Upload the PDF or a photo of your municipal collection schedule. Nothing is saved until you confirm.",
        "wimp_pick":            "Choose file…",
        "wimp_working":         "Reading the schedule…",
        "wimp_found":           "Collection series found ({0}) · year {1}",
        "wimp_hint":            "Municipal leaflets often hold several schedules at once (e.g. a fortnightly and a monthly round). Tick only the ones that apply to you.",
        "wimp_use":             "Use",
        "wimp_add":             "Add selected collections",
        "wimp_none_selected":   "Select at least one series.",
        "wimp_added":           "✓ Added: {0} collections",
        "wimp_err_format":      "Unsupported format. Upload a PDF, JPG or PNG.",
        "wimp_err_large":       "File is too large (max 12 MB).",
        "wimp_err_parse":       "No collection calendar could be found in this file.",
        "wimp_err_novision":    "This layout isn't recognised by the parser. To enable reading from photos, add an Anthropic API key in the add-on configuration.",
        "wimp_err_generic":     "Import failed.",
        "wimp_via_pdf":         "read straight from the PDF",
        "wimp_via_vision":      "recognised from the image",
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
        # — Abfallkalender —
        "waste_open_btn":       "Abfuhrkalender…",
        "waste_title":          "Abfuhrkalender",
        "waste_enabled_label":  "Abfuhr-Erinnerung",
        "waste_on":             "Ein",
        "waste_off":            "Aus",
        "waste_display_label":  "Wie soll erinnert werden",
        "waste_mode_overlay":   "Schild in der Ecke",
        "waste_mode_slide":     "Vollbild",
        "waste_mode_both":      "Beides",
        "waste_interval_label": "Vollbild alle … Fotos",
        "waste_days_label":     "Tage im Voraus erinnern",
        "waste_show_on_day":    "Auch am Abfuhrtag erinnern",
        "waste_start_hour":     "Erinnerung erst ab",
        "waste_rules_label":    "Abfuhren",
        "waste_add_rule":       "+ Abfuhr hinzufügen",
        "waste_no_rules":       "Noch keine Abfuhren eingerichtet.",
        "waste_type_label":     "Abfallart",
        "waste_name_label":     "Eigener Name (optional)",
        "waste_recurrence":     "Wiederholung",
        "waste_kind_weekly":    "Alle N Wochen",
        "waste_kind_monthly":   "Monatlich",
        "waste_kind_dates":     "Bestimmte Daten",
        "waste_weekday":        "Wochentag",
        "waste_every_weeks":    "Alle … Wochen",
        "waste_anchor":         "Referenzdatum (ein Abfuhrtag)",
        "waste_anchor_hint":    "Damit wird berechnet, welche Woche die „richtige“ ist.",
        "waste_monthly_by":     "Festgelegt durch",
        "waste_by_weekday":     "Position im Monat",
        "waste_by_day":         "Tagesnummer",
        "waste_week_of_month":  "Welche Woche",
        "waste_day_of_month":   "Tag im Monat",
        "waste_months":         "Nur in Monaten (optional)",
        "waste_dates_label":    "Abfuhrtermine",
        "waste_add_date":       "Hinzufügen",
        "waste_valid_from":     "Gültig ab (optional)",
        "waste_valid_to":       "Gültig bis (optional)",
        "waste_skip_label":     "Ausnahmen – keine Abfuhr am",
        "waste_extra_label":    "Zusätzliche Sondertermine",
        "waste_save":           "Speichern",
        "waste_cancel":         "Abbrechen",
        "waste_delete":         "Löschen",
        "waste_saved":          "✓ Gespeichert",
        "waste_save_err":       "Speichern fehlgeschlagen",
        "waste_preview":        "Nächste Abfuhren",
        "waste_preview_none":   "Keine Abfuhren geplant",
        "waste_today":          "Heute",
        "waste_tomorrow":       "Morgen",
        "waste_in_days_few":    "In {0} Tagen",
        "waste_in_days_many":   "In {0} Tagen",
        "waste_headline":       "Abfuhr",
        "waste_hint":           "Denk daran, die Tonne heute Abend rauszustellen",
        "waste_hint_today":     "Die Tonne sollte schon draußen stehen",
        "waste_every_week":     "jede Woche",
        "waste_every_n_weeks":  "alle {0} Wochen",
        "waste_dates_one":      "{0} Termin",
        "waste_dates_few":      "{0} Termine",
        "waste_dates_many":     "{0} Termine",
        # — Kalenderimport —
        "wimp_open":            "\u2191 Aus Abfuhrkalender laden…",
        "wimp_title":           "Kalender importieren",
        "wimp_intro":           "Lade das PDF oder ein Foto des kommunalen Abfuhrkalenders hoch. Es wird nichts gespeichert, bis du bestätigst.",
        "wimp_pick":            "Datei wählen…",
        "wimp_working":         "Kalender wird gelesen…",
        "wimp_found":           "Gefundene Abfuhrreihen ({0}) · Jahr {1}",
        "wimp_hint":            "Kommunale Faltblätter enthalten oft mehrere Kalender gleichzeitig (z. B. 14-tägig und monatlich). Kreuze nur die an, die für dich gelten.",
        "wimp_use":             "Verwenden",
        "wimp_add":             "Ausgewählte Abfuhren hinzufügen",
        "wimp_none_selected":   "Wähle mindestens eine Reihe.",
        "wimp_added":           "✓ Hinzugefügt: {0} Abfuhren",
        "wimp_err_format":      "Format nicht unterstützt. Lade ein PDF, JPG oder PNG hoch.",
        "wimp_err_large":       "Datei ist zu groß (max. 12 MB).",
        "wimp_err_parse":       "In dieser Datei wurde kein Abfuhrkalender gefunden.",
        "wimp_err_novision":    "Dieses Layout kennt der Parser nicht. Für die Erkennung aus Fotos trage einen Anthropic-API-Schlüssel in der Add-on-Konfiguration ein.",
        "wimp_err_generic":     "Import fehlgeschlagen.",
        "wimp_via_pdf":         "direkt aus dem PDF gelesen",
        "wimp_via_vision":      "aus dem Bild erkannt",
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

WEEKDAYS = {
    "sk": ["Pondelok","Utorok","Streda","\u0160tvrtok","Piatok","Sobota","Nede\u013ea"],
    "en": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
    "de": ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"],
}

WEEKDAYS_SHORT = {
    "sk": ["Po","Ut","St","\u0160t","Pi","So","Ne"],
    "en": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
    "de": ["Mo","Di","Mi","Do","Fr","Sa","So"],
}

# Poradie t\u00fd\u017ed\u0148a v mesiaci (1..5 a -1 = posledn\u00fd) pre popis pravidla
WEEK_ORDINALS = {
    "sk": {"1": "prv\u00fd", "2": "druh\u00fd", "3": "tret\u00ed", "4": "\u0161tvrt\u00fd", "5": "piaty", "-1": "posledn\u00fd"},
    "en": {"1": "first", "2": "second", "3": "third", "4": "fourth", "5": "fifth", "-1": "last"},
    "de": {"1": "erster", "2": "zweiter", "3": "dritter", "4": "vierter", "5": "f\u00fcnfter", "-1": "letzter"},
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

# ── Kalendár vývozu odpadu ─────────────────────────────────────

def _waste_lang():
    return LANGUAGE if LANGUAGE in TRANSLATIONS else "sk"

@app.route("/waste/config")
def waste_config_route():
    """Celá konfigurácia + katalóg druhov odpadu – pre editor v appke."""
    if not _has_waste:
        return jsonify({"ok": False, "error": "unavailable"}), 503
    lang = _waste_lang()
    return jsonify({
        "ok":      True,
        "config":  _waste.load_config(),
        "types":   _waste.type_catalog(lang),
        "max_rules": _waste.MAX_RULES,
    })

@app.route("/waste/config", methods=["POST"])
def waste_config_save_route():
    if not _has_waste:
        return jsonify({"ok": False, "error": "unavailable"}), 503
    raw = request.get_json(silent=True)
    if raw is None:
        return jsonify({"ok": False, "error": "no data"}), 400
    try:
        cfg = _waste.save_config(raw)
    except Exception as e:
        log.error("Uloženie kalendára odpadu zlyhalo: {}".format(e))
        return jsonify({"ok": False, "error": "save failed"}), 500
    log.info("Kalendár odpadu uložený: {} pravidiel, režim {}, {}".format(
        len(cfg["rules"]), cfg["mode"], "zapnutý" if cfg["enabled"] else "vypnutý"))
    return jsonify({"ok": True, "config": cfg})

@app.route("/waste/status")
def waste_status_route():
    """Čo sa vyváža v najbližších dňoch.

    Zámerne posielame surový zoznam termínov a nie hotovú hlášku „zajtra sa
    vyváža…“ – čo je „dnešok“ si rozhodne prehliadač na tablete, ktorý má
    na rozdiel od kontajnera add-onu spoľahlivo správnu lokálnu časovú zónu.
    Okno začína 2 dni v minulosti, aby posun TZ nikdy neodrežal dnešný termín.
    """
    if not _has_waste:
        return jsonify({"enabled": False, "upcoming": []})
    cfg  = _waste.load_config()
    lang = _waste_lang()
    return jsonify({
        "enabled":        cfg["enabled"],
        "mode":           cfg["mode"],
        "photo_interval": cfg["photo_interval"],
        "days_before":    cfg["days_before"],
        "show_on_day":    cfg["show_on_day"],
        "start_hour":     cfg["start_hour"],
        "upcoming":       _waste.occurrences(cfg, date.today() - timedelta(days=2),
                                             _waste.UPCOMING_DAYS, lang),
    })

@app.route("/waste/next")
def waste_next_route():
    """Najbližší vývoz – pre REST senzor / automatizácie v Home Assistante."""
    if not _has_waste:
        return jsonify({"ok": False, "error": "unavailable"}), 503
    cfg = _waste.load_config()
    nxt = _waste.next_collection(cfg, date.today(), _waste_lang())
    if not nxt:
        return jsonify({"ok": True, "state": "", "date": "", "days_until": None,
                        "types": [], "text": ""})
    labels = [t["label"] for t in nxt["types"]]
    return jsonify({
        "ok":         True,
        "state":      nxt["date"],
        "date":       nxt["date"],
        "days_until": nxt["days_until"],
        "types":      nxt["types"],
        "text":       ", ".join(labels),
    })

@app.route("/waste/import", methods=["POST"])
def waste_import_route():
    """Vytiahni termíny z nahratého harmonogramu. Nič neukladá – iba vráti návrh.

    Rozpoznanie sa NIKDY neuloží automaticky: zle prečítaný termín znamená
    zmeškaný kontajner, čo je práve to, čomu má celá funkcia zabrániť.
    Používateľ preto najprv v appke potvrdí, ktoré rady sa ho týkajú.
    """
    if not _has_waste_import:
        return jsonify({"ok": False, "error": "unavailable"}), 503
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "no file"}), 400
    data = f.read(_waste_import.MAX_UPLOAD_BYTES + 1)
    if len(data) > _waste_import.MAX_UPLOAD_BYTES:
        return jsonify({"ok": False, "error": "too_large"}), 413
    if not data:
        return jsonify({"ok": False, "error": "empty"}), 400

    ext  = Path(_safe_filename(f.filename)).suffix.lower()
    lang = _waste_lang()
    is_pdf = ext == ".pdf" or data[:5] == b"%PDF-"

    result = _waste_import.parse_pdf(data, lang) if is_pdf else {"ok": False, "error": "not_pdf"}
    if not result.get("ok"):
        # Fotka, sken alebo neznáme rozloženie – skús vision model, ak je kľúč.
        media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".gif": "image/gif",
                 ".pdf": "application/pdf"}.get(ext, "application/pdf" if is_pdf else "")
        if not media:
            return jsonify({"ok": False, "error": "unsupported_format"}), 400
        if not ANTHROPIC_API_KEY:
            return jsonify({"ok": False, "error": result.get("error") or "no_api_key",
                            "vision_available": False}), 422
        log.info("Harmonogram: parser neuspel ({}), skúšam vision".format(result.get("error")))
        result = _waste_import.parse_with_vision(data, media, lang, ANTHROPIC_API_KEY)
        if not result.get("ok"):
            return jsonify(result), 422

    log.info("Harmonogram naimportovaný ({}): {} radov, rok {}".format(
        result.get("source"), len(result.get("series", [])), result.get("year")))
    result["types"] = _waste.type_catalog(lang) if _has_waste else []
    return jsonify(result)

# ── HTML ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Stránka rámu. HTML/CSS/JS sú súbory v /usr/share/snapframe – do stránky
    sa vkladá len konfigurácia, takže CSS a JS si prehliadač môže nakešovať
    natrvalo (menia sa len s ?v=<verzia assetov>)."""
    lang = LANGUAGE if LANGUAGE in TRANSLATIONS else "sk"
    cfg = {
        "tr":               TRANSLATIONS[lang],
        "slideshow_secs":   SLIDESHOW_SECS,
        "sleep_start":      SLEEP_START,
        "sleep_end":        SLEEP_END,
        "weather_interval": WEATHER_PHOTO_INTERVAL,
        "weekdays":         WEEKDAYS[lang],
        "weekdays_short":   WEEKDAYS_SHORT[lang],
        "months":           MONTHS[lang],
        "week_ordinals":    WEEK_ORDINALS[lang],
    }
    html = _read_index_html()
    html = html.replace("__SNAPFRAME_CFG__", json_module.dumps(cfg, ensure_ascii=False))
    html = html.replace("__ASSET_V__", ASSET_VERSION)
    resp = Response(html, mimetype="text/html; charset=utf-8")
    # Samotné HTML sa nekešuje – nástenný displej tak po update dostane nové
    # ?v= na CSS/JS bez ručného čistenia cache v Safari.
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"]        = "no-cache"
    resp.headers["Expires"]       = "0"
    return resp


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
