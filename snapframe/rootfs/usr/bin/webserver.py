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

app = Flask(__name__)

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
/* Fluidná typografia (clamp + vw): škáluje sa s veľkosťou obrazovky,
   aby bola obrazovka čitateľná aj z druhého konca miestnosti. */
#weather-slide {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0; z-index: 80;
  background:
    radial-gradient(ellipse at 50% 26%, #1c2c4a 0%, #0a1120 55%, #05070e 100%);
  display: none; -webkit-flex-direction: column; flex-direction: column;
  align-items: center; justify-content: center; text-align: center;
  padding: 4vh 4vw; -webkit-box-sizing: border-box; box-sizing: border-box;
  opacity: 0; -webkit-transition: opacity 1s ease-in-out; transition: opacity 1s ease-in-out;
}
#weather-slide.visible { display: -webkit-flex; display: flex; opacity: 1; }
/* — Hero: veľká ikona + obrovská teplota vedľa seba —
   Pozn.: pred každým clamp()/min() je px fallback pre staré Safari
   (napr. iPad Safari 9–12), ktoré clamp()/min() nepodporujú a inak by
   celý riadok zahodili → text spadne na default a rozbije sa layout. */
.weather-hero {
  display: -webkit-flex; display: flex; -webkit-align-items: center; align-items: center;
  -webkit-justify-content: center; justify-content: center;
  gap: 28px;
  gap: clamp(12px, 2.5vw, 40px);
}
.weather-icon {
  font-size: 130px;
  font-size: clamp(78px, 12vw, 168px); line-height: 1;
  filter: drop-shadow(0 8px 26px rgba(0,0,0,0.6));
  -webkit-filter: drop-shadow(0 8px 26px rgba(0,0,0,0.6));
}
.weather-main { text-align: left; }
.weather-temp {
  font-size: 160px;
  font-size: clamp(92px, 16vw, 220px); font-weight: 200; letter-spacing: -0.03em;
  color: #fff; line-height: 0.9;
  text-shadow: 0 3px 30px rgba(0,0,0,0.5);
}
.weather-cond {
  font-size: 30px;
  font-size: clamp(20px, 3vw, 44px); font-weight: 300; letter-spacing: 0.01em;
  color: rgba(255,255,255,0.82);
  margin-top: 10px; margin-top: clamp(4px, 0.8vw, 14px);
}
/* — Max/Min dnešného dňa — */
.weather-range {
  margin-top: 30px; margin-top: clamp(18px, 3.2vh, 44px);
  font-size: 18px; font-size: clamp(15px, 1.7vw, 24px);
  letter-spacing: 0.12em; text-transform: uppercase;
  color: rgba(255,255,255,0.5);
}
.weather-range .val {
  color: #fff;
  font-size: 24px; font-size: clamp(19px, 2.2vw, 32px);
  text-transform: none; letter-spacing: 0;
  margin-left: 8px; margin-left: clamp(6px, 0.7vw, 12px);
  margin-right: 22px;  /* medzera pred ďalším popiskom aj bez flex `gap` (staré Safari) */
}
/* — Hodinová predpoveď: menej, ale veľkých kariet, čitateľných zďaleka — */
.weather-hourly {
  margin-top: 44px; margin-top: clamp(26px, 4.5vh, 70px);
  display: -webkit-flex; display: flex; -webkit-flex-wrap: nowrap; flex-wrap: nowrap;
  gap: 14px; gap: clamp(8px, 1.2vw, 20px);
  width: 100%; max-width: 1500px; -webkit-justify-content: center; justify-content: center;
}
.weather-hour {
  display: -webkit-flex; display: flex; -webkit-flex-direction: column; flex-direction: column;
  -webkit-align-items: center; align-items: center; -webkit-flex: 1 1 0%; flex: 1 1 0%;
  min-width: 0; max-width: 220px;
  -webkit-box-sizing: border-box; box-sizing: border-box;
  padding: 20px 10px 18px;
  padding: clamp(14px, 1.8vh, 26px) clamp(4px, 1vw, 16px) clamp(13px, 1.7vh, 24px);
  border-radius: 18px; border-radius: clamp(16px, 1.8vw, 26px);
  background: rgba(255,255,255,0.055); border: 1px solid rgba(255,255,255,0.07);
}
.weather-hour.now {
  background: rgba(120,170,255,0.16); border-color: rgba(140,185,255,0.4);
}
.weather-hour .wh-time {
  font-size: 19px; font-size: clamp(15px, 1.9vw, 27px);
  letter-spacing: 0.03em; font-weight: 300;
  color: rgba(255,255,255,0.72);
}
.weather-hour.now .wh-time { color: #cfe0ff; }
.weather-hour .wh-ico  {
  font-size: 44px; font-size: clamp(34px, 4.6vw, 68px); line-height: 1;
  margin: 12px 0 10px; margin: clamp(9px, 1.3vh, 18px) 0 clamp(8px, 1.1vh, 16px);
}
.weather-hour .wh-temp {
  font-size: 26px; font-size: clamp(23px, 3.2vw, 46px);
  font-weight: 400; color: #fff; line-height: 1;
}
.weather-date {
  position: absolute; bottom: 28px; bottom: clamp(20px, 3.5vh, 44px);
  left: 0; right: 0; text-align: center;
  font-size: 15px; font-size: clamp(13px, 1.4vw, 20px);
  letter-spacing: 0.22em; text-transform: uppercase;
  color: rgba(255,255,255,0.32);
}
/* — Portrét (tablet/telefón na výšku): hero na stred, hodiny ako riadky zhora dole — */
@media (orientation: portrait) {
  #weather-slide {
    -webkit-justify-content: center; justify-content: center;
    padding: 3vh 5vw;
  }
  .weather-hero {
    -webkit-flex-direction: column; flex-direction: column;
    gap: 6px; gap: clamp(2px, 0.6vh, 8px);
  }
  .weather-main { text-align: center; }
  .weather-temp { font-size: 150px; font-size: clamp(80px, 21vw, 190px); }
  .weather-icon { font-size: 120px; font-size: clamp(74px, 17vw, 150px); }
  .weather-cond {
    font-size: 30px; font-size: clamp(21px, 4.6vw, 36px);
    margin-top: 6px; margin-top: clamp(2px, 0.5vh, 8px);
  }
  .weather-range {
    margin-top: 20px; margin-top: clamp(10px, 1.8vh, 26px);
    font-size: 20px; font-size: clamp(15px, 3.3vw, 24px);
  }
  .weather-range .val { font-size: 24px; font-size: clamp(19px, 4.2vw, 28px); }
  /* Hodiny ako riadky zhora dole. Zámerne NIE flexbox ani gap/clamp/min pre
     štruktúru – starý iPad Safari (9–13) má buggy flexbox a nepozná gap/clamp/min.
     display:table + table-cell funguje spoľahlivo aj na prastarom Safari. */
  .weather-hourly {
    display: block;
    width: 360px; width: min(92%, 360px);
    max-width: 92%;
    margin-left: auto; margin-right: auto;
    margin-top: 28px; margin-top: clamp(14px, 2.6vh, 36px);
  }
  .weather-hour {
    display: table; table-layout: fixed; width: 100%;
    -webkit-flex: 0 1 auto; flex: 0 1 auto; max-width: none;
    margin: 0 auto 10px; margin-bottom: clamp(7px, 1vh, 13px);
    padding: 14px 22px;
    padding: clamp(8px, 1.3vh, 18px) clamp(16px, 5vw, 24px);
  }
  .weather-hour .wh-time {
    display: table-cell; vertical-align: middle; text-align: left; width: 32%;
    font-size: 28px; font-size: clamp(21px, 5.4vw, 34px);
  }
  .weather-hour .wh-ico {
    display: table-cell; vertical-align: middle; text-align: center; margin: 0;
    font-size: 44px; font-size: clamp(32px, 7.6vw, 52px);
  }
  .weather-hour .wh-temp {
    display: table-cell; vertical-align: middle; text-align: right; width: 32%;
    font-size: 36px; font-size: clamp(26px, 6.6vw, 44px);
  }
  /* dátum do toku, nech neprekrýva riadky na vysokom obsahu */
  .weather-date {
    position: static;
    margin-top: 24px; margin-top: clamp(16px, 3vh, 34px); bottom: auto;
  }
}
/* ===== ODPAD: štítok v rohu fotky ===== */
/* Rovnaký princíp ako weather slide: vždy px fallback pred clamp(),
   žiadny flex `gap` – starý iPad Safari (9–13) ich nepozná. */
#waste-badge {
  position: absolute; top: 16px; left: 18px; z-index: 95;
  display: none; max-width: 62%;
  background: rgba(8,10,14,0.62);
  border-radius: 14px; border-radius: clamp(12px, 1.2vw, 18px);
  border-left: 6px solid #9aa5b1;
  padding: 12px 18px 12px 14px;
  padding: clamp(9px, 1.4vh, 18px) clamp(13px, 1.5vw, 24px) clamp(9px, 1.4vh, 18px) clamp(10px, 1.1vw, 18px);
  -webkit-box-sizing: border-box; box-sizing: border-box;
  text-shadow: 0 2px 8px rgba(0,0,0,0.9);
  pointer-events: none;
}
#waste-badge.visible { display: block; }
.wb-row { display: table; width: 100%; }
.wb-ico {
  display: table-cell; vertical-align: middle; padding-right: 12px;
  font-size: 38px; font-size: clamp(30px, 3.4vw, 54px); line-height: 1;
}
.wb-text { display: table-cell; vertical-align: middle; text-align: left; }
.wb-when {
  font-size: 13px; font-size: clamp(11px, 1.1vw, 17px);
  letter-spacing: 0.18em; text-transform: uppercase;
  color: rgba(255,255,255,0.55); margin-bottom: 3px;
}
.wb-what {
  font-size: 26px; font-size: clamp(20px, 2.2vw, 36px);
  font-weight: 300; color: #fff; line-height: 1.15;
}
/* ===== ODPAD: celoobrazovkový slide ===== */
#waste-slide {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0; z-index: 82;
  background:
    radial-gradient(ellipse at 50% 28%, #1d3324 0%, #0c1712 55%, #05080b 100%);
  display: none; -webkit-flex-direction: column; flex-direction: column;
  align-items: center; justify-content: center; text-align: center;
  padding: 4vh 5vw; -webkit-box-sizing: border-box; box-sizing: border-box;
  opacity: 0; -webkit-transition: opacity 1s ease-in-out; transition: opacity 1s ease-in-out;
}
#waste-slide.visible { display: block; display: -webkit-flex; display: flex; opacity: 1; }
.waste-when {
  font-size: 24px; font-size: clamp(18px, 2.4vw, 38px);
  letter-spacing: 0.26em; text-transform: uppercase;
  color: rgba(255,255,255,0.55);
  margin-bottom: 18px; margin-bottom: clamp(10px, 2vh, 30px);
}
.waste-icons {
  font-size: 110px; font-size: clamp(70px, 13vw, 168px); line-height: 1.05;
  filter: drop-shadow(0 8px 26px rgba(0,0,0,0.6));
  -webkit-filter: drop-shadow(0 8px 26px rgba(0,0,0,0.6));
}
.waste-names {
  font-size: 58px; font-size: clamp(34px, 6.4vw, 96px);
  font-weight: 200; letter-spacing: -0.01em; color: #fff; line-height: 1.1;
  margin-top: 16px; margin-top: clamp(8px, 1.8vh, 26px);
  text-shadow: 0 3px 30px rgba(0,0,0,0.5);
}
.waste-names .wn-sep { color: rgba(255,255,255,0.32); }
.waste-accent {
  width: 120px; width: clamp(80px, 11vw, 190px);
  height: 6px; height: clamp(4px, 0.6vh, 9px);
  border-radius: 4px; background: #7cb342;
  margin: 26px auto 0; margin-top: clamp(16px, 2.6vh, 36px);
}
.waste-hint {
  font-size: 22px; font-size: clamp(16px, 2vw, 32px); font-weight: 300;
  color: rgba(255,255,255,0.7);
  margin-top: 26px; margin-top: clamp(15px, 2.6vh, 38px);
  max-width: 900px;
}
.waste-date {
  position: absolute; bottom: 28px; bottom: clamp(20px, 3.5vh, 44px);
  left: 0; right: 0; text-align: center;
  font-size: 15px; font-size: clamp(13px, 1.4vw, 20px);
  letter-spacing: 0.22em; text-transform: uppercase;
  color: rgba(255,255,255,0.32);
}
@media (orientation: portrait) {
  .waste-names { font-size: 46px; font-size: clamp(30px, 9vw, 62px); }
  .waste-icons { font-size: 96px; font-size: clamp(64px, 20vw, 130px); }
  .waste-when  { font-size: 20px; font-size: clamp(15px, 4vw, 26px); }
  .waste-hint  { font-size: 20px; font-size: clamp(15px, 4vw, 26px); }
  .waste-date  { position: static; margin-top: 26px; }
}
/* ===== ODPAD: import harmonogramu ===== */
.wimp-intro { font-size: 12px; line-height: 1.55; color: #6a6a6a; margin-bottom: 12px; }
.wimp-hint  { font-size: 11px; line-height: 1.55; color: #4a4a4a; margin: 8px 0 12px; }
#waste-import-file { display: none; }
.wimp-serie {
  display: table; width: 100%; background: #151515; border: 1px solid #232323;
  border-radius: 11px; padding: 12px 13px; margin-bottom: 8px;
  -webkit-box-sizing: border-box; box-sizing: border-box;
  cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.wimp-serie.on { border-color: #4a7fd6; background: #171e2b; }
.wimp-serie .ws-sw {
  display: table-cell; vertical-align: middle; width: 34px;
}
.wimp-serie .ws-chip {
  width: 22px; height: 22px; border-radius: 6px;
  border: 3px solid transparent; -webkit-box-sizing: border-box; box-sizing: border-box;
}
.wimp-serie .ws-txt { display: table-cell; vertical-align: middle; padding-right: 8px; }
.wimp-serie .ws-name { color: #e8e8e8; font-size: 14px; margin-bottom: 2px; }
.wimp-serie .ws-sub  { color: #6b6b6b; font-size: 11.5px; line-height: 1.45; }
.wimp-serie .ws-box  {
  display: table-cell; vertical-align: middle; width: 24px;
  text-align: right; color: #3a3a3a; font-size: 17px;
}
.wimp-serie.on .ws-box { color: #5b9bf8; }
.wimp-type {
  /* prisadnutý k svojmu radu, aby bolo jasné, ku ktorému riadku patrí */
  width: 92%; margin: -4px 0 10px auto; display: block;
  -webkit-box-sizing: border-box; box-sizing: border-box;
  background: #1b1b1b; border: 1px solid #2a2a2a; border-radius: 8px;
  color: #ddd; font-size: 13px; padding: 8px 10px; outline: none;
}
/* ===== ODPAD: editor kalendára ===== */
#waste-dialog {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  z-index: 400; background: #0c0c0c; display: none;
  overflow-y: auto; -webkit-overflow-scrolling: touch;
  padding: 26px 18px 40px; -webkit-box-sizing: border-box; box-sizing: border-box;
}
.wd-inner { max-width: 560px; margin: 0 auto; text-align: left; }
.wd-title {
  font-size: 13px; letter-spacing: 2.5px; text-transform: uppercase;
  color: #777; margin-bottom: 22px; text-align: center;
}
.wd-group { margin-bottom: 22px; }
.wd-label {
  font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #555; margin-bottom: 9px;
}
.wd-hint { font-size: 11px; line-height: 1.5; color: #4a4a4a; margin-top: 6px; }
.wd-seg { display: block; width: 100%; font-size: 0; }
.wd-seg .wd-opt {
  display: inline-block; -webkit-box-sizing: border-box; box-sizing: border-box;
  background: #171717; border: 1.5px solid #272727; border-radius: 10px;
  padding: 11px 6px; text-align: center; color: #8b8b8b; font-size: 14px;
  cursor: pointer; outline: none; -webkit-tap-highlight-color: transparent;
  margin: 0 2% 8px 0; vertical-align: top;
  -webkit-transition: border-color .15s, background .15s, color .15s;
  transition: border-color .15s, background .15s, color .15s;
}
/* Šírky sú zámerne pod matematickým maximom: každá dlaždica má margin-right,
   takže riadok musí vyjsť aj bez spoliehania sa na :last-child – inak by pri
   10 druhoch odpadu vyšli riadky raz po 3 a raz po 4 kusoch. */
.wd-seg.cols2 .wd-opt { width: 47.8%; }
.wd-seg.cols3 .wd-opt { width: 31%; }
.wd-seg.cols4 .wd-opt { width: 22.7%; }
.wd-seg.cols7 .wd-opt { width: 12.1%; padding: 11px 2px; font-size: 13px; }
.wd-seg .wd-opt.active { border-color: #4a7fd6; background: #1a2333; color: #dce6fb; }
.wd-input, .wd-select {
  width: 100%; -webkit-box-sizing: border-box; box-sizing: border-box;
  background: #171717; border: 1px solid #272727; border-radius: 9px;
  color: #ddd; font-size: 15px; padding: 11px 12px; outline: none;
  -webkit-appearance: none; appearance: none;
  font-family: -apple-system, Helvetica, Arial, sans-serif;
}
.wd-select { -webkit-appearance: menulist; appearance: menulist; }
.wd-stepper { display: table; width: 100%; }
.wd-stepper .wd-step-btn {
  display: table-cell; width: 54px; text-align: center; vertical-align: middle;
  background: #1c1c1c; border: 1px solid #2a2a2a; border-radius: 9px;
  color: #bbb; font-size: 22px; line-height: 1; padding: 10px 0;
  cursor: pointer; outline: none; -webkit-tap-highlight-color: transparent;
  -webkit-user-select: none; user-select: none;
}
.wd-stepper .wd-step-val {
  display: table-cell; text-align: center; vertical-align: middle;
  color: #fff; font-size: 19px; font-weight: 300;
}
.wd-check {
  display: table; width: 100%; background: #171717; border: 1px solid #262626;
  border-radius: 10px; padding: 12px 14px; -webkit-box-sizing: border-box;
  box-sizing: border-box; cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.wd-check .wc-txt { display: table-cell; vertical-align: middle; color: #bbb; font-size: 14px; }
.wd-check .wc-box {
  display: table-cell; vertical-align: middle; width: 26px; text-align: right;
  color: #3a3a3a; font-size: 18px;
}
.wd-check.on .wc-box { color: #5b9bf8; }
.wd-check.on .wc-txt { color: #e6e6e6; }
.wd-rule {
  display: table; width: 100%; background: #151515; border: 1px solid #232323;
  border-left-width: 5px; border-radius: 11px; padding: 13px 14px; margin-bottom: 9px;
  -webkit-box-sizing: border-box; box-sizing: border-box;
  cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.wd-rule .wr-ico { display: table-cell; vertical-align: middle; width: 40px; font-size: 25px; }
.wd-rule .wr-txt { display: table-cell; vertical-align: middle; }
.wd-rule .wr-name { color: #eee; font-size: 15px; margin-bottom: 2px; }
.wd-rule .wr-sub  { color: #6b6b6b; font-size: 12px; line-height: 1.4; }
.wd-rule .wr-go   { display: table-cell; vertical-align: middle; width: 22px;
                    text-align: right; color: #444; font-size: 17px; }
.wd-empty { color: #4a4a4a; font-size: 13px; padding: 14px 2px; }
.wd-btn {
  display: block; width: 100%; -webkit-box-sizing: border-box; box-sizing: border-box;
  padding: 13px; border-radius: 10px; font-size: 15px; text-align: center;
  cursor: pointer; outline: none; -webkit-tap-highlight-color: transparent;
  border: 1px solid #2c2c2c; background: #202020; color: #ccc; margin-bottom: 9px;
}
.wd-btn.primary { background: #24457c; border-color: #2f5da8; color: #eaf1ff; }
.wd-btn.danger  { background: #2a1616; border-color: #4a2020; color: #d98a8a; }
.wd-btn.ghost   { background: transparent; border-color: #262626; color: #777; }
.wd-status { font-size: 13px; text-align: center; min-height: 18px; margin-bottom: 8px; color: #888; }
.wd-status.ok  { color: #4caf50; }
.wd-status.err { color: #d9534f; }
.wd-chips { font-size: 0; }
.wd-chip {
  display: inline-block; background: #1b1b1b; border: 1px solid #2a2a2a;
  border-radius: 20px; padding: 7px 12px; margin: 0 6px 6px 0;
  color: #bbb; font-size: 13px; cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.wd-chip .wc-x { color: #666; margin-left: 7px; }
.wd-chip.month.on { background: #1a2333; border-color: #4a7fd6; color: #dce6fb; }
.wd-daterow { display: table; width: 100%; }
.wd-daterow .wd-dcell { display: table-cell; vertical-align: middle; }
.wd-daterow .wd-dbtn  {
  display: table-cell; vertical-align: middle; width: 90px; padding-left: 8px;
}
.wd-preview-day {
  display: table; width: 100%; padding: 9px 0; border-bottom: 1px solid #1c1c1c;
}
.wd-preview-day .wp-date { display: table-cell; vertical-align: middle; width: 45%;
                           color: #9a9a9a; font-size: 13px; }
.wd-preview-day .wp-types { display: table-cell; vertical-align: middle;
                            color: #ddd; font-size: 13px; text-align: right; }
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
    <div class="settings-group">
      <button class="wd-btn" id="t-waste-open-btn" onclick="openWasteDialog()"></button>
    </div>
    <button class="settings-close" id="t-settings-close" onclick="closeSettings()"></button>
  </div>
</div>

<!-- EDITOR KALENDÁRA VÝVOZU ODPADU -->
<div id="waste-dialog">
  <div class="wd-inner">
    <div class="wd-title" id="t-waste-title"></div>

    <!-- prehľad + globálne nastavenia -->
    <div id="waste-main">
      <div class="wd-group">
        <div class="wd-label" id="t-waste-enabled-label"></div>
        <div class="wd-seg cols2" id="waste-enabled-seg">
          <div class="wd-opt" id="waste-en-off" onclick="wdSetEnabled(0)"></div>
          <div class="wd-opt" id="waste-en-on"  onclick="wdSetEnabled(1)"></div>
        </div>
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-display-label"></div>
        <div class="wd-seg cols3" id="waste-mode-seg">
          <div class="wd-opt" id="waste-mode-overlay" onclick="wdSetMode('overlay')"></div>
          <div class="wd-opt" id="waste-mode-slide"   onclick="wdSetMode('slide')"></div>
          <div class="wd-opt" id="waste-mode-both"    onclick="wdSetMode('both')"></div>
        </div>
      </div>

      <div class="wd-group" id="waste-interval-group">
        <div class="wd-label" id="t-waste-interval-label"></div>
        <div class="wd-stepper">
          <div class="wd-step-btn" onclick="wdStep('photo_interval',-1,2,100)">&minus;</div>
          <div class="wd-step-val" id="waste-interval-val"></div>
          <div class="wd-step-btn" onclick="wdStep('photo_interval',1,2,100)">+</div>
        </div>
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-days-label"></div>
        <div class="wd-stepper">
          <div class="wd-step-btn" onclick="wdStep('days_before',-1,0,7)">&minus;</div>
          <div class="wd-step-val" id="waste-days-val"></div>
          <div class="wd-step-btn" onclick="wdStep('days_before',1,0,7)">+</div>
        </div>
      </div>

      <div class="wd-group">
        <div class="wd-check" id="waste-showday-check" onclick="wdToggleShowOnDay()">
          <div class="wc-txt" id="t-waste-show-on-day"></div>
          <div class="wc-box">&#10003;</div>
        </div>
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-start-hour"></div>
        <div class="wd-stepper">
          <div class="wd-step-btn" onclick="wdStep('start_hour',-1,0,23)">&minus;</div>
          <div class="wd-step-val" id="waste-hour-val"></div>
          <div class="wd-step-btn" onclick="wdStep('start_hour',1,0,23)">+</div>
        </div>
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-rules-label"></div>
        <div id="waste-rule-list"></div>
        <button class="wd-btn ghost" id="t-waste-add-rule" onclick="wdNewRule()"></button>
        <button class="wd-btn ghost" id="t-wimp-open" onclick="wimpOpen()"></button>
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-preview"></div>
        <div id="waste-preview-list"></div>
      </div>

      <div class="wd-status" id="waste-status"></div>
      <button class="wd-btn primary" id="t-waste-save" onclick="wdSaveConfig()"></button>
      <button class="wd-btn" id="t-waste-close" onclick="closeWasteDialog()"></button>
    </div>

    <!-- import harmonogramu -->
    <div id="waste-import" style="display:none">
      <div class="wimp-intro" id="t-wimp-intro"></div>
      <input type="file" id="waste-import-file" accept=".pdf,.png,.jpg,.jpeg,image/*,application/pdf"
             onchange="wimpUpload(this)">
      <button class="wd-btn" id="t-wimp-pick"
              onclick="document.getElementById('waste-import-file').click()"></button>
      <div class="wd-status" id="wimp-status"></div>
      <div id="wimp-result"></div>
      <button class="wd-btn primary" id="t-wimp-add" style="display:none" onclick="wimpAdd()"></button>
      <button class="wd-btn" id="t-wimp-cancel" onclick="wimpClose()"></button>
    </div>

    <!-- editor jedného zvozu -->
    <div id="waste-editor" style="display:none">
      <div class="wd-group">
        <div class="wd-label" id="t-waste-type-label"></div>
        <div class="wd-seg cols4" id="waste-type-seg"></div>
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-name-label"></div>
        <input type="text" class="wd-input" id="waste-name-input" maxlength="40">
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-recurrence"></div>
        <div class="wd-seg cols3" id="waste-kind-seg">
          <div class="wd-opt" id="waste-kind-weekly"  onclick="wdSetKind('weekly')"></div>
          <div class="wd-opt" id="waste-kind-monthly" onclick="wdSetKind('monthly')"></div>
          <div class="wd-opt" id="waste-kind-dates"   onclick="wdSetKind('dates')"></div>
        </div>
      </div>

      <!-- týždenné -->
      <div id="waste-weekly-box">
        <div class="wd-group">
          <div class="wd-label" id="t-waste-weekday"></div>
          <div class="wd-seg cols7" id="waste-weekday-seg"></div>
        </div>
        <div class="wd-group">
          <div class="wd-label" id="t-waste-every-weeks"></div>
          <div class="wd-stepper">
            <div class="wd-step-btn" onclick="wdStepRule('interval_weeks',-1,1,12)">&minus;</div>
            <div class="wd-step-val" id="waste-weeks-val"></div>
            <div class="wd-step-btn" onclick="wdStepRule('interval_weeks',1,1,12)">+</div>
          </div>
        </div>
        <div class="wd-group" id="waste-anchor-group">
          <div class="wd-label" id="t-waste-anchor"></div>
          <input type="date" class="wd-input" id="waste-anchor-input"
                 placeholder="YYYY-MM-DD" onchange="wdReadAnchor()">
          <div class="wd-hint" id="t-waste-anchor-hint"></div>
        </div>
      </div>

      <!-- mesačné -->
      <div id="waste-monthly-box" style="display:none">
        <div class="wd-group">
          <div class="wd-label" id="t-waste-monthly-by"></div>
          <div class="wd-seg cols2" id="waste-by-seg">
            <div class="wd-opt" id="waste-by-weekday" onclick="wdSetMonthlyBy('weekday')"></div>
            <div class="wd-opt" id="waste-by-day"     onclick="wdSetMonthlyBy('day')"></div>
          </div>
        </div>
        <div id="waste-by-weekday-box">
          <div class="wd-group">
            <div class="wd-label" id="t-waste-week-of-month"></div>
            <select class="wd-select" id="waste-wom-select" onchange="wdReadWom()"></select>
          </div>
          <div class="wd-group">
            <div class="wd-label" id="t-waste-weekday-2"></div>
            <div class="wd-seg cols7" id="waste-weekday-seg2"></div>
          </div>
        </div>
        <div class="wd-group" id="waste-by-day-box" style="display:none">
          <div class="wd-label" id="t-waste-day-of-month"></div>
          <div class="wd-stepper">
            <div class="wd-step-btn" onclick="wdStepRule('day_of_month',-1,1,31)">&minus;</div>
            <div class="wd-step-val" id="waste-dom-val"></div>
            <div class="wd-step-btn" onclick="wdStepRule('day_of_month',1,1,31)">+</div>
          </div>
        </div>
        <div class="wd-group">
          <div class="wd-label" id="t-waste-months"></div>
          <div class="wd-chips" id="waste-months-chips"></div>
        </div>
      </div>

      <!-- konkrétne dátumy -->
      <div id="waste-dates-box" style="display:none">
        <div class="wd-group">
          <div class="wd-label" id="t-waste-dates-label"></div>
          <div class="wd-daterow">
            <div class="wd-dcell"><input type="date" class="wd-input" id="waste-date-input" placeholder="YYYY-MM-DD"></div>
            <div class="wd-dbtn"><button class="wd-btn" style="margin:0" id="t-waste-add-date"
                 onclick="wdAddDate('dates')"></button></div>
          </div>
          <div class="wd-chips" id="waste-dates-chips" style="margin-top:10px"></div>
        </div>
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-valid-from"></div>
        <input type="date" class="wd-input" id="waste-from-input" placeholder="YYYY-MM-DD" onchange="wdReadRange()">
      </div>
      <div class="wd-group">
        <div class="wd-label" id="t-waste-valid-to"></div>
        <input type="date" class="wd-input" id="waste-to-input" placeholder="YYYY-MM-DD" onchange="wdReadRange()">
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-skip-label"></div>
        <div class="wd-daterow">
          <div class="wd-dcell"><input type="date" class="wd-input" id="waste-skip-input" placeholder="YYYY-MM-DD"></div>
          <div class="wd-dbtn"><button class="wd-btn" style="margin:0" id="t-waste-add-skip"
               onclick="wdAddDate('skip')"></button></div>
        </div>
        <div class="wd-chips" id="waste-skip-chips" style="margin-top:10px"></div>
      </div>

      <div class="wd-group">
        <div class="wd-label" id="t-waste-extra-label"></div>
        <div class="wd-daterow">
          <div class="wd-dcell"><input type="date" class="wd-input" id="waste-extra-input" placeholder="YYYY-MM-DD"></div>
          <div class="wd-dbtn"><button class="wd-btn" style="margin:0" id="t-waste-add-extra"
               onclick="wdAddDate('extra')"></button></div>
        </div>
        <div class="wd-chips" id="waste-extra-chips" style="margin-top:10px"></div>
      </div>

      <button class="wd-btn primary" id="t-waste-rule-ok"     onclick="wdCommitRule()"></button>
      <button class="wd-btn"         id="t-waste-rule-cancel" onclick="wdCancelRule()"></button>
      <button class="wd-btn danger"  id="t-waste-rule-delete" onclick="wdDeleteRule()"></button>
    </div>
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
  <div id="waste-badge">
    <div class="wb-row">
      <div class="wb-ico" id="waste-badge-ico"></div>
      <div class="wb-text">
        <div class="wb-when" id="waste-badge-when"></div>
        <div class="wb-what" id="waste-badge-what"></div>
      </div>
    </div>
  </div>
  <div id="waste-slide">
    <div class="waste-when"  id="waste-slide-when"></div>
    <div class="waste-icons" id="waste-slide-icons"></div>
    <div class="waste-names" id="waste-slide-names"></div>
    <div class="waste-accent" id="waste-slide-accent"></div>
    <div class="waste-hint"  id="waste-slide-hint"></div>
    <div class="waste-date"  id="waste-slide-date"></div>
  </div>
  <div id="weather-slide">
    <div class="weather-hero">
      <div class="weather-icon" id="weather-icon"></div>
      <div class="weather-main">
        <div class="weather-temp" id="weather-temp"></div>
        <div class="weather-cond" id="weather-cond"></div>
      </div>
    </div>
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
var WEEKDAYS         = __WEEKDAYS__;
var WEEKDAYS_SHORT   = __WEEKDAYS_SHORT__;
var MONTHS_LIST      = __MONTHS_LIST__;
var WEEK_ORDINALS    = __WEEK_ORDINALS__;

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
  // — kalendár vývozu odpadu —
  document.getElementById("t-waste-open-btn").textContent       = tr("waste_open_btn");
  document.getElementById("t-waste-title").textContent          = tr("waste_title");
  document.getElementById("t-waste-enabled-label").textContent  = tr("waste_enabled_label");
  document.getElementById("waste-en-on").textContent            = tr("waste_on");
  document.getElementById("waste-en-off").textContent           = tr("waste_off");
  document.getElementById("t-waste-display-label").textContent  = tr("waste_display_label");
  document.getElementById("waste-mode-overlay").textContent     = tr("waste_mode_overlay");
  document.getElementById("waste-mode-slide").textContent       = tr("waste_mode_slide");
  document.getElementById("waste-mode-both").textContent        = tr("waste_mode_both");
  document.getElementById("t-waste-interval-label").textContent = tr("waste_interval_label");
  document.getElementById("t-waste-days-label").textContent     = tr("waste_days_label");
  document.getElementById("t-waste-show-on-day").textContent    = tr("waste_show_on_day");
  document.getElementById("t-waste-start-hour").textContent     = tr("waste_start_hour");
  document.getElementById("t-waste-rules-label").textContent    = tr("waste_rules_label");
  document.getElementById("t-waste-add-rule").textContent       = tr("waste_add_rule");
  document.getElementById("t-waste-preview").textContent        = tr("waste_preview");
  document.getElementById("t-waste-save").textContent           = tr("waste_save");
  document.getElementById("t-waste-close").textContent          = tr("settings_close");
  document.getElementById("t-waste-type-label").textContent     = tr("waste_type_label");
  document.getElementById("t-waste-name-label").textContent     = tr("waste_name_label");
  document.getElementById("t-waste-recurrence").textContent     = tr("waste_recurrence");
  document.getElementById("waste-kind-weekly").textContent      = tr("waste_kind_weekly");
  document.getElementById("waste-kind-monthly").textContent     = tr("waste_kind_monthly");
  document.getElementById("waste-kind-dates").textContent       = tr("waste_kind_dates");
  document.getElementById("t-waste-weekday").textContent        = tr("waste_weekday");
  document.getElementById("t-waste-weekday-2").textContent      = tr("waste_weekday");
  document.getElementById("t-waste-every-weeks").textContent    = tr("waste_every_weeks");
  document.getElementById("t-waste-anchor").textContent         = tr("waste_anchor");
  document.getElementById("t-waste-anchor-hint").textContent    = tr("waste_anchor_hint");
  document.getElementById("t-waste-monthly-by").textContent     = tr("waste_monthly_by");
  document.getElementById("waste-by-weekday").textContent       = tr("waste_by_weekday");
  document.getElementById("waste-by-day").textContent           = tr("waste_by_day");
  document.getElementById("t-waste-week-of-month").textContent  = tr("waste_week_of_month");
  document.getElementById("t-waste-day-of-month").textContent   = tr("waste_day_of_month");
  document.getElementById("t-waste-months").textContent         = tr("waste_months");
  document.getElementById("t-waste-dates-label").textContent    = tr("waste_dates_label");
  document.getElementById("t-waste-add-date").textContent       = tr("waste_add_date");
  document.getElementById("t-waste-add-skip").textContent       = tr("waste_add_date");
  document.getElementById("t-waste-add-extra").textContent      = tr("waste_add_date");
  document.getElementById("t-waste-valid-from").textContent     = tr("waste_valid_from");
  document.getElementById("t-waste-valid-to").textContent       = tr("waste_valid_to");
  document.getElementById("t-waste-skip-label").textContent     = tr("waste_skip_label");
  document.getElementById("t-waste-extra-label").textContent    = tr("waste_extra_label");
  document.getElementById("t-waste-rule-ok").textContent        = tr("waste_save");
  document.getElementById("t-waste-rule-cancel").textContent    = tr("waste_cancel");
  document.getElementById("t-waste-rule-delete").textContent    = tr("waste_delete");
  // — import harmonogramu —
  document.getElementById("t-wimp-open").textContent   = tr("wimp_open");
  document.getElementById("t-wimp-intro").textContent  = tr("wimp_intro");
  document.getElementById("t-wimp-pick").textContent   = tr("wimp_pick");
  document.getElementById("t-wimp-add").textContent    = tr("wimp_add");
  document.getElementById("t-wimp-cancel").textContent = tr("waste_cancel");
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
    updateWasteBadge();
  } else {
    el.style.display = "none";
    _stopMeteorShowerLoop();
    if (slideshowActive && photos.length > 0) {
      startAdvanceTimer();
      _startRefreshTimer();
    }
    // po prebudení je už možno „zajtra“ – prepočítaj pripomienku
    fetchWasteStatus();
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
  hideWasteSlide();
  document.getElementById("waste-badge").className = "";
  photosSinceWeather = 0;
  photosSinceWaste   = 0;
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
  hideWasteSlide();
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
  updateWasteBadge();
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
    photosSinceWaste++;
    showWeatherSlide();
    return;
  }
  if (wasteModeHas("slide") && currentWasteAlert() &&
      photosSinceWaste >= (wasteCfg.photo_interval || 10)) {
    photosSinceWaste = 0;
    photosSinceWeather++;
    showWasteSlide();
    return;
  }
  photosSinceWeather++;
  photosSinceWaste++;
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

// Po otočení obrazovky (portrét <-> landscape) prekresli weather slide,
// aby sa počet a rozloženie hodinových kariet prispôsobili orientácii.
function _weatherIsVisible() {
  return document.getElementById("weather-slide").className.indexOf("visible") !== -1;
}
window.addEventListener("resize", function() {
  if (_weatherIsVisible() && weatherData) { showWeatherSlide(); }
});

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
  document.getElementById("waste-badge").className      = "";
  document.getElementById("weather-slide").className = "visible";
}

function renderHourly(hourly) {
  var host = document.getElementById("weather-hourly");
  if (!hourly || !hourly.length) { host.innerHTML = ""; host.style.display = "none"; return; }
  host.style.display = "";
  // Portrét (na výšku): hodiny sú riadky zhora dole. Landscape (na stene):
  // 6 veľkých kariet vedľa seba. 6 položiek sa zmestí aj na telefón na výšku
  // a ostáva všade veľké a čitateľné zďaleka. Rozloženie rieši CSS podľa orientácie.
  var maxItems = 6;
  var list = hourly;
  if (list.length > maxItems) {
    // Rovnomerne navzorkuj naprieč celým rozsahom vrátane prvej a poslednej hodiny.
    var sampled = [];
    for (var k = 0; k < maxItems; k++) {
      sampled.push(list[Math.round(k * (list.length - 1) / (maxItems - 1))]);
    }
    list = sampled;
  }
  var html = "";
  for (var j = 0; j < list.length; j++) {
    var h = list[j];
    var ico  = WEATHER_EMOJI[h.condition] || "🌡️";
    var temp = (h.temperature != null) ? Math.round(h.temperature) + "°" : "--";
    html += "<div class=\"weather-hour" + (j === 0 ? " now" : "") + "\">"
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

// ── Kalendár vývozu odpadu: beh na fotorámiku ─────────────────────────────────
var wasteCfg          = null;   // nastavenia zo /waste/status
var wasteByDate       = {};     // "YYYY-MM-DD" -> [{id,label,icon,color}, ...]
var wasteUpcoming     = [];     // surový zoznam pre náhľad v editore
var photosSinceWaste  = 0;
var wasteSlideVisible = false;

function _pad2(n) { return (n < 10 ? "0" : "") + n; }

// Lokálny ISO dátum (NIE toISOString – ten prepočíta na UTC a v CEST posunie deň).
function _isoLocal(d) {
  return d.getFullYear() + "-" + _pad2(d.getMonth() + 1) + "-" + _pad2(d.getDate());
}

function fetchWasteStatus() {
  xhrGet("/waste/status", function(err, text) {
    if (err) { return; }
    try {
      var data = JSON.parse(text);
      wasteCfg      = data;
      wasteUpcoming = data.upcoming || [];
      wasteByDate   = {};
      for (var i = 0; i < wasteUpcoming.length; i++) {
        wasteByDate[wasteUpcoming[i].date] = wasteUpcoming[i].types || [];
      }
    } catch (e) { return; }
    updateWasteBadge();
  });
}
setInterval(fetchWasteStatus, 15 * 60 * 1000);

// Ktorý najbližší termín (v rámci nastaveného predstihu) máme práve pripomínať.
// „Dnešok“ určuje prehliadač na tablete – ten má správnu lokálnu časovú zónu.
function currentWasteAlert() {
  if (!wasteCfg || !wasteCfg.enabled) { return null; }
  var now   = new Date();
  var start = wasteCfg.show_on_day ? 0 : 1;
  for (var off = start; off <= wasteCfg.days_before; off++) {
    var d     = new Date(now.getFullYear(), now.getMonth(), now.getDate() + off);
    var types = wasteByDate[_isoLocal(d)];
    if (!types || !types.length) { continue; }
    // deň-vopred pripomienku netlačiť skôr, než si používateľ praje
    if (off >= 1 && now.getHours() < (wasteCfg.start_hour || 0)) { continue; }
    return { days: off, date: _isoLocal(d), types: types };
  }
  return null;
}

function wasteModeHas(what) {
  if (!wasteCfg) { return false; }
  return wasteCfg.mode === what || wasteCfg.mode === "both";
}

function wasteWhenLabel(days) {
  if (days === 0) { return tr("waste_today"); }
  if (days === 1) { return tr("waste_tomorrow"); }
  if (days <= 4)  { return trf("waste_in_days_few",  [days]); }
  return trf("waste_in_days_many", [days]);
}

function wasteIcons(types) {
  var out = "";
  for (var i = 0; i < types.length; i++) { out += types[i].icon; }
  return out;
}

function wasteNames(types) {
  var out = [];
  for (var i = 0; i < types.length; i++) { out.push(types[i].label); }
  return out;
}

function _wasteFormatDate(iso) {
  var p = iso.split("-");
  var d = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
  return WEEKDAYS[(d.getDay() + 6) % 7] + " · " + d.toLocaleDateString();
}

function updateWasteBadge() {
  var el = document.getElementById("waste-badge");
  if (!el) { return; }
  var a = currentWasteAlert();
  if (!a || !wasteModeHas("overlay") || !slideshowActive ||
      wasteSlideVisible || _weatherIsVisible() || _sleeping) {
    el.className = ""; return;
  }
  document.getElementById("waste-badge-ico").innerHTML  = escHtml(wasteIcons(a.types));
  document.getElementById("waste-badge-when").innerHTML = escHtml(wasteWhenLabel(a.days));
  document.getElementById("waste-badge-what").innerHTML = escHtml(wasteNames(a.types).join(" · "));
  el.style.borderLeftColor = a.types[0].color || "#9aa5b1";
  el.className = "visible";
}

function showWasteSlide() {
  var a = currentWasteAlert();
  if (!a) { return; }
  var names = wasteNames(a.types), html = "";
  for (var i = 0; i < names.length; i++) {
    if (i) { html += "<span class=\"wn-sep\"> · </span>"; }
    html += escHtml(names[i]);
  }
  document.getElementById("waste-slide-icons").innerHTML = escHtml(wasteIcons(a.types));
  document.getElementById("waste-slide-when").innerHTML  =
      escHtml(wasteWhenLabel(a.days) + " · " + tr("waste_headline"));
  document.getElementById("waste-slide-names").innerHTML = html;
  document.getElementById("waste-slide-accent").style.background = a.types[0].color || "#7cb342";
  document.getElementById("waste-slide-hint").innerHTML  =
      escHtml(a.days === 0 ? tr("waste_hint_today") : tr("waste_hint"));
  document.getElementById("waste-slide-date").innerHTML  = escHtml(_wasteFormatDate(a.date));
  document.getElementById("overlay-date").innerHTML     = "";
  document.getElementById("overlay-location").innerHTML = "";
  document.getElementById("photo-counter").innerHTML    = "";
  document.getElementById("waste-badge").className      = "";
  document.getElementById("waste-slide").className      = "visible";
  wasteSlideVisible = true;
}

function hideWasteSlide() {
  document.getElementById("waste-slide").className = "";
  wasteSlideVisible = false;
}

// ── Kalendár vývozu odpadu: editor ───────────────────────────────────────────
var wdCfg      = null;   // pracovná kópia celého configu
var wdTypes    = [];     // katalóg druhov odpadu zo servera
var wdMaxRules = 40;
var wdRule     = null;   // pracovná kópia práve editovaného pravidla
var wdRuleIdx  = -1;     // index v wdCfg.rules, -1 = nové pravidlo

function openWasteDialog() {
  closeSettings();
  document.getElementById("waste-dialog").style.display = "block";
  document.getElementById("waste-main").style.display   = "block";
  document.getElementById("waste-editor").style.display = "none";
  document.getElementById("waste-import").style.display = "none";
  document.getElementById("waste-dialog").scrollTop     = 0;
  wdStatus("", "");
  xhrGet("/waste/config", function(err, text) {
    if (err) { wdStatus(tr("waste_save_err"), "err"); return; }
    try {
      var data   = JSON.parse(text);
      wdCfg      = data.config || {};
      wdTypes    = data.types  || [];
      wdMaxRules = data.max_rules || 40;
    } catch (e) { wdStatus(tr("waste_save_err"), "err"); return; }
    if (!wdCfg.rules) { wdCfg.rules = []; }
    wdRenderMain();
  });
}

function closeWasteDialog() {
  document.getElementById("waste-dialog").style.display = "none";
  fetchWasteStatus();
}

function wdStatus(msg, cls) {
  var el = document.getElementById("waste-status");
  el.innerHTML = escHtml(msg || "");
  el.className = "wd-status" + (cls ? " " + cls : "");
}

function _seg(id, active) {
  var el = document.getElementById(id);
  if (el) { el.className = "wd-opt" + (active ? " active" : ""); }
}

function wdSetEnabled(on) { wdCfg.enabled = !!on; wdRenderMain(); }
function wdSetMode(m)     { wdCfg.mode = m;      wdRenderMain(); }

function wdStep(key, delta, lo, hi) {
  var v = (parseInt(wdCfg[key], 10) || 0) + delta;
  if (v < lo) { v = lo; }
  if (v > hi) { v = hi; }
  wdCfg[key] = v;
  if (key === "days_before" && v === 0) { wdCfg.show_on_day = true; }
  wdRenderMain();
}

function wdToggleShowOnDay() {
  if (wdCfg.days_before === 0) { return; }   // inak by sa nezobrazilo nikdy nič
  wdCfg.show_on_day = !wdCfg.show_on_day;
  wdRenderMain();
}

function wdRenderMain() {
  _seg("waste-en-on",  wdCfg.enabled);
  _seg("waste-en-off", !wdCfg.enabled);
  _seg("waste-mode-overlay", wdCfg.mode === "overlay");
  _seg("waste-mode-slide",   wdCfg.mode === "slide");
  _seg("waste-mode-both",    wdCfg.mode === "both");
  document.getElementById("waste-interval-group").style.display =
      (wdCfg.mode === "overlay") ? "none" : "";
  document.getElementById("waste-interval-val").innerHTML = wdCfg.photo_interval;
  document.getElementById("waste-days-val").innerHTML     = wdCfg.days_before;
  document.getElementById("waste-hour-val").innerHTML     = _pad2(wdCfg.start_hour) + ":00";
  document.getElementById("waste-showday-check").className =
      "wd-check" + (wdCfg.show_on_day ? " on" : "");
  wdRenderRules();
  wdRenderPreview();
}

function wdTypeInfo(id) {
  for (var i = 0; i < wdTypes.length; i++) {
    if (wdTypes[i].id === id) { return wdTypes[i]; }
  }
  return { id: id, label: id, icon: "♻️", color: "#9aa5b1" };
}

// Slovenčina skloňuje 1 / 2–4 / 5+ inak; ostatné jazyky použijú rovnaký tvar.
function wdCountLabel(n) {
  if (n === 1)              { return trf("waste_dates_one",  [n]); }
  if (n >= 2 && n <= 4)     { return trf("waste_dates_few",  [n]); }
  return trf("waste_dates_many", [n]);
}

function wdRuleSummary(rule) {
  var rec = rule.recurrence || {}, out = "";
  if (rec.kind === "weekly") {
    var n = rec.interval_weeks || 1;
    out = WEEKDAYS[rec.weekday || 0] + " · " +
          (n === 1 ? tr("waste_every_week") : trf("waste_every_n_weeks", [n]));
  } else if (rec.kind === "monthly") {
    if (rec.monthly_by === "day") {
      out = tr("waste_day_of_month") + ": " + (rec.day_of_month || 1) + ".";
    } else {
      out = WEEK_ORDINALS["" + (rec.week_of_month || 1)] + " " +
            WEEKDAYS[rec.weekday || 0].toLowerCase();
    }
    if (rec.months && rec.months.length) {
      var mm = [];
      for (var i = 0; i < rec.months.length; i++) { mm.push(MONTHS_LIST[rec.months[i] - 1].substr(0, 3)); }
      out += " (" + mm.join(", ") + ")";
    }
  } else {
    out = wdCountLabel((rec.dates || []).length);
  }
  if ((rule.extra || []).length) { out += " +" + rule.extra.length; }
  if ((rule.skip  || []).length) { out += " −" + rule.skip.length; }
  return out;
}

function wdRenderRules() {
  var host = document.getElementById("waste-rule-list");
  var rules = wdCfg.rules || [];
  if (!rules.length) {
    host.innerHTML = "<div class=\"wd-empty\">" + escHtml(tr("waste_no_rules")) + "</div>";
  } else {
    var html = "";
    for (var i = 0; i < rules.length; i++) {
      var info = wdTypeInfo(rules[i].type);
      var name = rules[i].label || info.label;
      html += "<div class=\"wd-rule\" style=\"border-left-color:" + escHtml(info.color) + "\""
            + " onclick=\"wdEditRule(" + i + ")\">"
            + "<div class=\"wr-ico\">" + escHtml(info.icon) + "</div>"
            + "<div class=\"wr-txt\"><div class=\"wr-name\">" + escHtml(name) + "</div>"
            + "<div class=\"wr-sub\">" + escHtml(wdRuleSummary(rules[i])) + "</div></div>"
            + "<div class=\"wr-go\">&#8250;</div></div>";
    }
    host.innerHTML = html;
  }
  var addBtn = document.getElementById("t-waste-add-rule");
  addBtn.style.display = (rules.length >= wdMaxRules) ? "none" : "";
}

// Náhľad ukazuje ULOŽENÝ harmonogram (rozvinutý serverom), nie rozpracované zmeny.
function wdRenderPreview() {
  var host = document.getElementById("waste-preview-list");
  if (!wasteUpcoming.length) {
    host.innerHTML = "<div class=\"wd-empty\">" + escHtml(tr("waste_preview_none")) + "</div>";
    return;
  }
  var todayIso = _isoLocal(new Date()), html = "", shown = 0;
  for (var i = 0; i < wasteUpcoming.length && shown < 6; i++) {
    if (wasteUpcoming[i].date < todayIso) { continue; }
    shown++;
    html += "<div class=\"wd-preview-day\"><div class=\"wp-date\">"
          + escHtml(_wasteFormatDate(wasteUpcoming[i].date)) + "</div>"
          + "<div class=\"wp-types\">"
          + escHtml(wasteIcons(wasteUpcoming[i].types) + " " +
                    wasteNames(wasteUpcoming[i].types).join(", "))
          + "</div></div>";
  }
  host.innerHTML = shown ? html
      : "<div class=\"wd-empty\">" + escHtml(tr("waste_preview_none")) + "</div>";
}

function wdSaveConfig() {
  wdStatus("…", "");
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "/waste/config", true);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    if (xhr.status !== 200) { wdStatus(tr("waste_save_err"), "err"); return; }
    try {
      var data = JSON.parse(xhr.responseText);
      if (data.config) { wdCfg = data.config; if (!wdCfg.rules) { wdCfg.rules = []; } }
    } catch (e) {}
    wdStatus(tr("waste_saved"), "ok");
    // po uložení si vypýtaj rozvinutý harmonogram, nech sedí náhľad aj rámik
    xhrGet("/waste/status", function(err2, text2) {
      if (!err2) {
        try {
          var st = JSON.parse(text2);
          wasteCfg      = st;
          wasteUpcoming = st.upcoming || [];
          wasteByDate   = {};
          for (var i = 0; i < wasteUpcoming.length; i++) {
            wasteByDate[wasteUpcoming[i].date] = wasteUpcoming[i].types || [];
          }
        } catch (e2) {}
      }
      updateWasteBadge();
      wdRenderMain();
    });
  };
  xhr.send(JSON.stringify(wdCfg));
}

// ── Import harmonogramu ──────────────────────────────────────────────────────
var wimpSeries = [];   // rady rozpoznané zo súboru
var wimpYear   = 0;

function wimpOpen() {
  document.getElementById("waste-main").style.display   = "none";
  document.getElementById("waste-import").style.display = "block";
  document.getElementById("waste-dialog").scrollTop     = 0;
  wimpReset();
}

function wimpClose() {
  document.getElementById("waste-import").style.display = "none";
  document.getElementById("waste-main").style.display   = "block";
  document.getElementById("waste-dialog").scrollTop     = 0;
  wimpReset();
  wdRenderMain();
}

function wimpReset() {
  wimpSeries = []; wimpYear = 0;
  document.getElementById("wimp-result").innerHTML = "";
  document.getElementById("waste-import-file").value = "";
  document.getElementById("t-wimp-add").style.display = "none";
  wimpStatus("", "");
}

function wimpStatus(msg, cls) {
  var el = document.getElementById("wimp-status");
  el.innerHTML = escHtml(msg || "");
  el.className = "wd-status" + (cls ? " " + cls : "");
}

function wimpErrKey(code) {
  if (code === "too_large")           { return "wimp_err_large"; }
  if (code === "unsupported_format")  { return "wimp_err_format"; }
  if (code === "no_api_key")          { return "wimp_err_novision"; }
  if (code === "no_calendar_found" || code === "no_marks_found" ||
      code === "pdf_parse_failed"     || code === "not_pdf") { return "wimp_err_parse"; }
  return "wimp_err_generic";
}

function wimpUpload(input) {
  if (!input.files || !input.files.length) { return; }
  wimpStatus(tr("wimp_working"), "");
  document.getElementById("wimp-result").innerHTML = "";
  document.getElementById("t-wimp-add").style.display = "none";
  var fd = new FormData();
  fd.append("file", input.files[0]);
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "/waste/import", true);
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) { return; }
    var data = null;
    try { data = JSON.parse(xhr.responseText); } catch (e) {}
    if (!data || !data.ok) {
      var code = data ? data.error : "";
      // Ak parser neuspel a vision nie je k dispozícii, povedz to konkrétne.
      if (data && data.vision_available === false && code !== "too_large") {
        code = "no_api_key";
      }
      wimpStatus(tr(wimpErrKey(code)), "err");
      return;
    }
    wimpSeries = data.series || [];
    wimpYear   = data.year || 0;
    for (var i = 0; i < wimpSeries.length; i++) {
      wimpSeries[i].selected = false;
      wimpSeries[i].type = wimpSeries[i].suggested_type || "other";
    }
    wimpStatus(tr(data.source === "vision" ? "wimp_via_vision" : "wimp_via_pdf"), "ok");
    wimpRender();
  };
  xhr.send(fd);
}

function wimpRender() {
  var host = document.getElementById("wimp-result");
  if (!wimpSeries.length) { host.innerHTML = ""; return; }
  var html = "<div class=\"wd-label\">"
           + escHtml(trf("wimp_found", [wimpSeries.length, wimpYear])) + "</div>"
           + "<div class=\"wimp-hint\">" + escHtml(tr("wimp_hint")) + "</div>";
  for (var i = 0; i < wimpSeries.length; i++) {
    var s = wimpSeries[i];
    var sw = "background:" + escHtml(s.fill)
           + (s.outline ? ";border-color:" + escHtml(s.outline) : "");
    var sub = [];
    if (s.summary) { sub.push(s.summary); }
    sub.push(s.count + "\u00d7");
    if (s.dates && s.dates.length) { sub.push(s.dates[0] + " \u2026 " + s.dates[s.dates.length - 1]); }
    html += "<div class=\"wimp-serie" + (s.selected ? " on" : "") + "\" onclick=\"wimpToggle(" + i + ")\">"
          + "<div class=\"ws-sw\"><div class=\"ws-chip\" style=\"" + sw + "\"></div></div>"
          + "<div class=\"ws-txt\"><div class=\"ws-name\">"
          + escHtml(s.colour_name || s.fill) + "</div>"
          + "<div class=\"ws-sub\">" + escHtml(sub.join(" \u00b7 ")) + "</div></div>"
          + "<div class=\"ws-box\">" + (s.selected ? "\u2713" : "\u25cb") + "</div></div>";
    if (s.selected) {
      html += "<select class=\"wimp-type\" onchange=\"wimpSetType(" + i + ",this.value)\">";
      for (var j = 0; j < wdTypes.length; j++) {
        html += "<option value=\"" + escHtml(wdTypes[j].id) + "\""
              + (wdTypes[j].id === s.type ? " selected" : "") + ">"
              + escHtml(wdTypes[j].icon + " " + wdTypes[j].label) + "</option>";
      }
      html += "</select>";
    }
  }
  host.innerHTML = html;
  var any = false;
  for (var k = 0; k < wimpSeries.length; k++) { if (wimpSeries[k].selected) { any = true; } }
  document.getElementById("t-wimp-add").style.display = any ? "" : "none";
}

function wimpToggle(i)      { wimpSeries[i].selected = !wimpSeries[i].selected; wimpRender(); }
function wimpSetType(i, v)  { wimpSeries[i].type = v; }

function wimpAdd() {
  var added = 0;
  for (var i = 0; i < wimpSeries.length; i++) {
    var s = wimpSeries[i];
    if (!s.selected || !s.dates || !s.dates.length) { continue; }
    wdCfg.rules.push({
      id: _newRuleId(), type: s.type, label: "",
      recurrence: { kind: "dates", dates: s.dates.slice(0) },
      from: "", to: "", skip: [], extra: []
    });
    added++;
  }
  if (!added) { wimpStatus(tr("wimp_none_selected"), "err"); return; }
  // Import sám osebe nemá zmysel, kým je pripomienka vypnutá.
  wdCfg.enabled = true;
  wimpClose();
  wdStatus(trf("wimp_added", [added]), "ok");
}

// ── Editor jedného zvozu ─────────────────────────────────────────────────────
function _newRuleId() {
  return "r" + Date.now().toString(36) + Math.floor(Math.random() * 1000).toString(36);
}

function wdNewRule() {
  wdRuleIdx = -1;
  wdRule = {
    id: _newRuleId(), type: (wdTypes[0] ? wdTypes[0].id : "mixed"), label: "",
    recurrence: { kind: "weekly", weekday: 0, interval_weeks: 1, anchor: "", months: [] },
    from: "", to: "", skip: [], extra: []
  };
  wdOpenEditor();
}

function wdEditRule(idx) {
  wdRuleIdx = idx;
  var src = wdCfg.rules[idx];
  var rec = src.recurrence || {};
  wdRule = {
    id: src.id || _newRuleId(), type: src.type, label: src.label || "",
    recurrence: {
      kind:           rec.kind || "weekly",
      weekday:        rec.weekday || 0,
      interval_weeks: rec.interval_weeks || 1,
      anchor:         rec.anchor || "",
      week_of_month:  rec.week_of_month || 1,
      day_of_month:   rec.day_of_month || 1,
      monthly_by:     rec.monthly_by || "weekday",
      months:         (rec.months || []).slice(0),
      dates:          (rec.dates  || []).slice(0)
    },
    from: src.from || "", to: src.to || "",
    skip: (src.skip || []).slice(0), extra: (src.extra || []).slice(0)
  };
  wdOpenEditor();
}

function wdOpenEditor() {
  document.getElementById("waste-main").style.display   = "none";
  document.getElementById("waste-editor").style.display = "block";
  document.getElementById("waste-dialog").scrollTop     = 0;
  document.getElementById("t-waste-rule-delete").style.display = (wdRuleIdx < 0) ? "none" : "";
  document.getElementById("waste-name-input").value  = wdRule.label || "";
  document.getElementById("waste-from-input").value  = wdRule.from  || "";
  document.getElementById("waste-to-input").value    = wdRule.to    || "";
  document.getElementById("waste-anchor-input").value = wdRule.recurrence.anchor || "";
  wdBuildTypeSeg();
  wdBuildWeekdaySegs();
  wdBuildWomSelect();
  wdBuildMonthChips();
  wdRenderEditor();
}

function wdBuildTypeSeg() {
  var host = document.getElementById("waste-type-seg"), html = "";
  for (var i = 0; i < wdTypes.length; i++) {
    var t = wdTypes[i];
    html += "<div class=\"wd-opt\" id=\"wd-type-" + escHtml(t.id) + "\""
          + " onclick=\"wdSetType('" + escHtml(t.id) + "')\">"
          + "<div style=\"font-size:24px;line-height:1.2\">" + escHtml(t.icon) + "</div>"
          + "<div style=\"font-size:11px;margin-top:3px\">" + escHtml(t.label) + "</div></div>";
  }
  host.innerHTML = html;
}

function wdBuildWeekdaySegs() {
  var html = "";
  for (var i = 0; i < 7; i++) {
    html += "<div class=\"wd-opt\" id=\"__PFX__" + i + "\" onclick=\"wdSetWeekday(" + i + ")\">"
          + escHtml(WEEKDAYS_SHORT[i]) + "</div>";
  }
  document.getElementById("waste-weekday-seg").innerHTML  = html.replace(/__PFX__/g, "wd-wd-");
  document.getElementById("waste-weekday-seg2").innerHTML = html.replace(/__PFX__/g, "wd-wd2-");
}

function wdBuildWomSelect() {
  var sel = document.getElementById("waste-wom-select"), html = "";
  var order = ["1", "2", "3", "4", "5", "-1"];
  for (var i = 0; i < order.length; i++) {
    html += "<option value=\"" + order[i] + "\">" + escHtml(WEEK_ORDINALS[order[i]]) + "</option>";
  }
  sel.innerHTML = html;
}

function wdBuildMonthChips() {
  var host = document.getElementById("waste-months-chips"), html = "";
  for (var m = 1; m <= 12; m++) {
    html += "<div class=\"wd-chip month\" id=\"wd-month-" + m + "\" onclick=\"wdToggleMonth(" + m + ")\">"
          + escHtml(MONTHS_LIST[m - 1].substr(0, 3)) + "</div>";
  }
  host.innerHTML = html;
}

function wdSetType(id)  { wdRule.type = id; wdRenderEditor(); }
function wdSetKind(k)   { wdRule.recurrence.kind = k; wdRenderEditor(); }
function wdSetWeekday(i){ wdRule.recurrence.weekday = i; wdRenderEditor(); }
function wdSetMonthlyBy(v) { wdRule.recurrence.monthly_by = v; wdRenderEditor(); }
function wdReadWom()    { wdRule.recurrence.week_of_month = parseInt(document.getElementById("waste-wom-select").value, 10); }
function wdReadAnchor() { wdRule.recurrence.anchor = _wdCleanDate(document.getElementById("waste-anchor-input").value); }
function wdReadRange()  {
  wdRule.from = _wdCleanDate(document.getElementById("waste-from-input").value);
  wdRule.to   = _wdCleanDate(document.getElementById("waste-to-input").value);
}

function wdStepRule(key, delta, lo, hi) {
  var v = (parseInt(wdRule.recurrence[key], 10) || 0) + delta;
  if (v < lo) { v = lo; }
  if (v > hi) { v = hi; }
  wdRule.recurrence[key] = v;
  wdRenderEditor();
}

function wdToggleMonth(m) {
  var arr = wdRule.recurrence.months || [], idx = -1;
  for (var i = 0; i < arr.length; i++) { if (arr[i] === m) { idx = i; break; } }
  if (idx >= 0) { arr.splice(idx, 1); } else { arr.push(m); arr.sort(function(a, b) { return a - b; }); }
  wdRule.recurrence.months = arr;
  wdRenderEditor();
}

function _wdCleanDate(v) {
  v = (v || "").replace(/^\s+|\s+$/g, "");
  return /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : "";
}

function _wdListFor(which) {
  return (which === "dates") ? (wdRule.recurrence.dates = wdRule.recurrence.dates || [])
       : (which === "skip")  ? (wdRule.skip  = wdRule.skip  || [])
                             : (wdRule.extra = wdRule.extra || []);
}

function wdAddDate(which) {
  var input = document.getElementById("waste-" + (which === "dates" ? "date" : which) + "-input");
  var v = _wdCleanDate(input.value);
  if (!v) { return; }
  var list = _wdListFor(which);
  for (var i = 0; i < list.length; i++) { if (list[i] === v) { input.value = ""; return; } }
  list.push(v);
  list.sort();
  input.value = "";
  wdRenderEditor();
}

function wdRemoveDate(which, iso) {
  var list = _wdListFor(which);
  for (var i = 0; i < list.length; i++) {
    if (list[i] === iso) { list.splice(i, 1); break; }
  }
  wdRenderEditor();
}

function _wdRenderChips(hostId, which, list) {
  var host = document.getElementById(hostId), html = "";
  for (var i = 0; i < list.length; i++) {
    html += "<div class=\"wd-chip\" onclick=\"wdRemoveDate('" + which + "','" + escHtml(list[i]) + "')\">"
          + escHtml(list[i]) + "<span class=\"wc-x\">&times;</span></div>";
  }
  host.innerHTML = html;
}

function wdRenderEditor() {
  var rec = wdRule.recurrence;
  for (var i = 0; i < wdTypes.length; i++) {
    _seg("wd-type-" + wdTypes[i].id, wdTypes[i].id === wdRule.type);
  }
  _seg("waste-kind-weekly",  rec.kind === "weekly");
  _seg("waste-kind-monthly", rec.kind === "monthly");
  _seg("waste-kind-dates",   rec.kind === "dates");
  document.getElementById("waste-weekly-box").style.display  = (rec.kind === "weekly")  ? "" : "none";
  document.getElementById("waste-monthly-box").style.display = (rec.kind === "monthly") ? "" : "none";
  document.getElementById("waste-dates-box").style.display   = (rec.kind === "dates")   ? "" : "none";

  for (var w = 0; w < 7; w++) {
    _seg("wd-wd-"  + w, w === rec.weekday);
    _seg("wd-wd2-" + w, w === rec.weekday);
  }
  document.getElementById("waste-weeks-val").innerHTML = rec.interval_weeks || 1;
  document.getElementById("waste-anchor-group").style.display = ((rec.interval_weeks || 1) > 1) ? "" : "none";

  _seg("waste-by-weekday", rec.monthly_by !== "day");
  _seg("waste-by-day",     rec.monthly_by === "day");
  document.getElementById("waste-by-weekday-box").style.display = (rec.monthly_by === "day") ? "none" : "";
  document.getElementById("waste-by-day-box").style.display     = (rec.monthly_by === "day") ? "" : "none";
  document.getElementById("waste-wom-select").value = "" + (rec.week_of_month || 1);
  document.getElementById("waste-dom-val").innerHTML = rec.day_of_month || 1;

  var months = rec.months || [];
  for (var m = 1; m <= 12; m++) {
    var on = false;
    for (var k = 0; k < months.length; k++) { if (months[k] === m) { on = true; break; } }
    var chip = document.getElementById("wd-month-" + m);
    if (chip) { chip.className = "wd-chip month" + (on ? " on" : ""); }
  }

  _wdRenderChips("waste-dates-chips", "dates", rec.dates || []);
  _wdRenderChips("waste-skip-chips",  "skip",  wdRule.skip  || []);
  _wdRenderChips("waste-extra-chips", "extra", wdRule.extra || []);
}

function wdCommitRule() {
  var rec = wdRule.recurrence;
  wdRule.label = document.getElementById("waste-name-input").value.replace(/^\s+|\s+$/g, "");
  wdReadRange();
  if (rec.kind === "weekly") {
    wdReadAnchor();
    // bez referenčného dátumu sa fáza „každý N-tý týždeň“ nedá určiť
    if ((rec.interval_weeks || 1) > 1 && !rec.anchor) {
      document.getElementById("waste-anchor-input").focus();
      return;
    }
  } else if (rec.kind === "dates") {
    if (!(rec.dates || []).length && !(wdRule.extra || []).length) {
      document.getElementById("waste-date-input").focus();
      return;
    }
  }
  if (wdRuleIdx < 0) { wdCfg.rules.push(wdRule); }
  else               { wdCfg.rules[wdRuleIdx] = wdRule; }
  wdCloseEditor();
}

function wdCancelRule() { wdCloseEditor(); }

function wdDeleteRule() {
  if (wdRuleIdx >= 0) { wdCfg.rules.splice(wdRuleIdx, 1); }
  wdCloseEditor();
}

function wdCloseEditor() {
  wdRule = null; wdRuleIdx = -1;
  document.getElementById("waste-editor").style.display = "none";
  document.getElementById("waste-main").style.display   = "block";
  document.getElementById("waste-dialog").scrollTop     = 0;
  wdStatus("", "");
  wdRenderMain();
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
fetchWasteStatus();
</script>
</body>
</html>"""
    lang = LANGUAGE if LANGUAGE in TRANSLATIONS else "sk"
    html = html.replace("__SNAPFRAME_TR__",  json_module.dumps(TRANSLATIONS[lang], ensure_ascii=False))
    html = html.replace("__SLIDESHOW_SECS__", str(SLIDESHOW_SECS))
    html = html.replace("__SLEEP_START__",    SLEEP_START)
    html = html.replace("__SLEEP_END__",      SLEEP_END)
    html = html.replace("__WEATHER_INTERVAL__", str(WEATHER_PHOTO_INTERVAL))
    html = html.replace("__WEEKDAYS__",       json_module.dumps(WEEKDAYS[lang], ensure_ascii=False))
    html = html.replace("__WEEKDAYS_SHORT__", json_module.dumps(WEEKDAYS_SHORT[lang], ensure_ascii=False))
    html = html.replace("__MONTHS_LIST__",    json_module.dumps(MONTHS[lang], ensure_ascii=False))
    html = html.replace("__WEEK_ORDINALS__",  json_module.dumps(WEEK_ORDINALS[lang], ensure_ascii=False))
    resp = Response(html, mimetype="text/html; charset=utf-8")
    # Nekešuj HTML (obsahuje všetok CSS/JS) – nástenný displej tak vždy dostane
    # aktuálnu verziu po update/rebuild bez ručného čistenia cache v Safari.
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
