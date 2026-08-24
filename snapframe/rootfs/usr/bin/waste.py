#!/usr/bin/env python3
"""
SnapFrame – kalendár vývozu odpadu (waste collection calendar).

Model:
  * Konfigurácia je jeden JSON súbor v /data (prežije reštart aj update add-onu),
    editovateľný priamo z webového rozhrania – žiadne prepisovanie YAML options
    kvôli desiatkam dátumov.
  * Kalendár nie je zoznam dátumov, ale zoznam PRAVIDIEL (rules). Reálne obecné
    harmonogramy sú takmer vždy "každý druhý štvrtok" alebo "prvý pondelok
    v mesiaci"; explicitné dátumy sú len tretia možnosť pre nepravidelné zvozy.
    Ku každému pravidlu sa dá pridať platnosť od/do, výnimky (skip) a
    mimoriadne termíny navyše (extra).
  * Modul počíta LEN výskyty (occurrences) pre dané okno dní. Rozhodnutie
    "čo sa vyváža zajtra" robí prehliadač na tablete – ten má na rozdiel od
    kontajnera vždy správnu lokálnu časovú zónu.
"""

import json
import logging
import os
import re
import threading
from collections import OrderedDict
from datetime import date, timedelta

log = logging.getLogger("snapframe.waste")

CONFIG_FILE = os.environ.get("WASTE_CONFIG_FILE", "/data/waste_schedule.json")

MAX_RULES     = 40      # ochrana proti nezmyselne veľkému configu z prehliadača
MAX_DATES     = 400     # max. dátumov v jednom zozname (dates / skip / extra)
UPCOMING_DAYS = 24      # koľko dní dopredu posielame do prehliadača

_lock = threading.Lock()

# ── Katalóg druhov odpadu ────────────────────────────────────────────────────
# icon = emoji (žiadne externé assety, funguje aj na starom iPad Safari)
# color = farba pruhu/akcentu v UI
WASTE_TYPES = OrderedDict([
    ("mixed",    {"icon": "\U0001F5D1️", "color": "#8b95a5",
                  "labels": {"sk": "Zmesový odpad", "en": "Mixed waste",     "de": "Restmüll"}}),
    ("bio",      {"icon": "\U0001F33F",       "color": "#7cb342",
                  "labels": {"sk": "Bioodpad",      "en": "Bio waste",       "de": "Biomüll"}}),
    ("plastic",  {"icon": "\U0001F964",       "color": "#f2c200",
                  "labels": {"sk": "Plasty",        "en": "Plastic",         "de": "Kunststoff"}}),
    ("paper",    {"icon": "\U0001F4C4",       "color": "#4a90e2",
                  "labels": {"sk": "Papier",        "en": "Paper",           "de": "Papier"}}),
    ("glass",    {"icon": "\U0001F37E",       "color": "#26a96c",
                  "labels": {"sk": "Sklo",          "en": "Glass",           "de": "Glas"}}),
    ("metal",    {"icon": "\U0001F96B",       "color": "#e0574f",
                  "labels": {"sk": "Kovy",          "en": "Metal",           "de": "Metall"}}),
    ("tetrapak", {"icon": "\U0001F9C3",       "color": "#ff8a3d",
                  "labels": {"sk": "Tetrapak (VKM)", "en": "Drink cartons",  "de": "Getränkekartons"}}),
    ("electro",  {"icon": "\U0001F50C",       "color": "#a855f7",
                  "labels": {"sk": "Elektroodpad",  "en": "E-waste",         "de": "Elektroschrott"}}),
    ("bulky",    {"icon": "\U0001F6CB️", "color": "#a9805e",
                  "labels": {"sk": "Objemný odpad", "en": "Bulky waste",     "de": "Sperrmüll"}}),
    ("other",    {"icon": "♻️",     "color": "#9aa5b1",
                  "labels": {"sk": "Iný odpad",     "en": "Other waste",     "de": "Sonstiger Abfall"}}),
])

DEFAULT_CONFIG = {
    "enabled":        False,
    "mode":           "overlay",   # overlay | slide | both
    "photo_interval": 10,          # po koľkých fotkách vložiť celoobrazovkový slide
    "days_before":    1,           # koľko dní vopred upozorniť
    "show_on_day":    True,        # upozorniť aj ráno v deň vývozu
    "start_hour":     0,           # deň-vopred upozornenie zobrazovať až od tejto hodiny
    "end_hour":       24,          # upozornenie v deň vývozu zobrazovať len do tejto hodiny (24 = celý deň)
    "rules":          [],
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Malé helpery ─────────────────────────────────────────────────────────────

def _clamp_int(value, lo, hi, default):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return lo if n < lo else (hi if n > hi else n)


def _parse_date(value):
    """'YYYY-MM-DD' -> date, inak None."""
    s = str(value or "").strip()
    if not _DATE_RE.match(s):
        return None
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _valid_date_str(value):
    d = _parse_date(value)
    return d.isoformat() if d else ""


def _clean_dates(value):
    """Zoznam dátumových reťazcov -> zoradený zoznam validných unikátnych ISO dátumov."""
    if not isinstance(value, (list, tuple)):
        return []
    seen = set()
    for item in value[:MAX_DATES * 2]:
        iso = _valid_date_str(item)
        if iso:
            seen.add(iso)
    return sorted(seen)[:MAX_DATES]


def _clean_months(value):
    """Zoznam čísel mesiacov 1–12; prázdny zoznam = bez obmedzenia."""
    if not isinstance(value, (list, tuple)):
        return []
    out = set()
    for item in value[:12]:
        try:
            n = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 12:
            out.add(n)
    return sorted(out)


def _rule_id(value):
    s = re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:24]
    return s or "r{}".format(os.urandom(4).hex())


def _nth_weekday(year, month, weekday, nth):
    """N-tý daný deň v týždni v mesiaci. nth: 1..5, alebo -1 = posledný."""
    if nth < 0:
        first_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        last = first_next - timedelta(days=1)
        return last - timedelta(days=(last.weekday() - weekday) % 7)
    first  = date(year, month, 1)
    day    = 1 + ((weekday - first.weekday()) % 7) + (nth - 1) * 7
    try:
        return date(year, month, day)
    except ValueError:
        return None   # napr. 5. pondelok v mesiaci, ktorý ho nemá


# ── Sanitizácia configu (dáta prichádzajú z prehliadača) ─────────────────────

def _sanitize_rule(raw):
    if not isinstance(raw, dict):
        return None
    rtype = str(raw.get("type") or "").strip()
    if rtype not in WASTE_TYPES:
        rtype = "other"

    raw_rec = raw.get("recurrence")
    if not isinstance(raw_rec, dict):
        raw_rec = {}
    kind = str(raw_rec.get("kind") or "dates")
    if kind not in ("dates", "weekly", "monthly"):
        kind = "dates"

    rec = {"kind": kind}
    extra = _clean_dates(raw.get("extra"))
    if kind == "dates":
        rec["dates"] = _clean_dates(raw_rec.get("dates"))
        if not rec["dates"] and not extra:
            return None                       # pravidlo bez jediného termínu
    elif kind == "weekly":
        rec["weekday"]        = _clamp_int(raw_rec.get("weekday"), 0, 6, 0)
        rec["interval_weeks"] = _clamp_int(raw_rec.get("interval_weeks"), 1, 12, 1)
        rec["anchor"]         = _valid_date_str(raw_rec.get("anchor"))
        rec["months"]         = _clean_months(raw_rec.get("months"))
        if rec["interval_weeks"] > 1 and not rec["anchor"]:
            # bez kotvy sa nedá určiť fáza „každý druhý týždeň“
            rec["interval_weeks"] = 1
    else:
        by = str(raw_rec.get("monthly_by") or "weekday")
        rec["monthly_by"]    = by if by in ("weekday", "day") else "weekday"
        rec["weekday"]       = _clamp_int(raw_rec.get("weekday"), 0, 6, 0)
        wom                  = _clamp_int(raw_rec.get("week_of_month"), -1, 5, 1)
        rec["week_of_month"] = 1 if wom == 0 else wom
        rec["day_of_month"]  = _clamp_int(raw_rec.get("day_of_month"), 1, 31, 1)
        rec["months"]        = _clean_months(raw_rec.get("months"))

    return {
        "id":         _rule_id(raw.get("id")),
        "type":       rtype,
        "label":      str(raw.get("label") or "").strip()[:40],
        "recurrence": rec,
        "from":       _valid_date_str(raw.get("from")),
        "to":         _valid_date_str(raw.get("to")),
        "skip":       _clean_dates(raw.get("skip")),
        "extra":      extra,
    }


def sanitize_config(raw):
    if not isinstance(raw, dict):
        raw = {}
    mode = str(raw.get("mode") or "overlay")
    cfg = {
        "enabled":        bool(raw.get("enabled", False)),
        "mode":           mode if mode in ("overlay", "slide", "both") else "overlay",
        "photo_interval": _clamp_int(raw.get("photo_interval"), 2, 100, 10),
        "days_before":    _clamp_int(raw.get("days_before"), 0, 7, 1),
        "show_on_day":    bool(raw.get("show_on_day", True)),
        "start_hour":     _clamp_int(raw.get("start_hour"), 0, 23, 0),
        "end_hour":       _clamp_int(raw.get("end_hour"), 1, 24, 24),
        "rules":          [],
    }
    if cfg["days_before"] == 0:
        cfg["show_on_day"] = True     # inak by sa neukázalo nikdy nič
    rules = raw.get("rules")
    if isinstance(rules, list):
        used_ids = set()
        for item in rules[:MAX_RULES]:
            rule = _sanitize_rule(item)
            if not rule:
                continue
            while rule["id"] in used_ids:
                rule["id"] = _rule_id(None)
            used_ids.add(rule["id"])
            cfg["rules"].append(rule)
    return cfg


# ── Načítanie / uloženie ─────────────────────────────────────────────────────

def load_config():
    with _lock:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            return sanitize_config(DEFAULT_CONFIG)
        except Exception as e:
            log.warning("Kalendár odpadu – načítanie zlyhalo: {}".format(e))
            return sanitize_config(DEFAULT_CONFIG)
    return sanitize_config(raw)


def save_config(raw):
    """Zvaliduje a atomicky uloží konfiguráciu. Vracia uloženú (očistenú) verziu."""
    cfg = sanitize_config(raw)
    with _lock:
        tmp = CONFIG_FILE + ".tmp"
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_FILE)
        except Exception as e:
            log.error("Kalendár odpadu – uloženie zlyhalo: {}".format(e))
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    return cfg


# ── Výpočet výskytov ─────────────────────────────────────────────────────────

def _compile_rule(rule):
    """Predparsuje dátumové reťazce, aby sa to nerobilo pre každý deň znova."""
    rec = rule.get("recurrence") or {}
    compiled = {
        "type":  rule.get("type", "other"),
        "label": rule.get("label", ""),
        "kind":  rec.get("kind", "dates"),
        "from":  _parse_date(rule.get("from")),
        "to":    _parse_date(rule.get("to")),
        "skip":  set(rule.get("skip") or []),
        "extra": set(rule.get("extra") or []),
        "rec":   rec,
        "dates": set(rec.get("dates") or []),
    }
    anchor = _parse_date(rec.get("anchor"))
    if anchor is not None and rec.get("kind") == "weekly":
        # kotvu zarovnaj na požadovaný deň v týždni, nech fáza sedí aj keď
        # používateľ zadá dátum, ktorý na daný deň nepadne
        weekday = _clamp_int(rec.get("weekday"), 0, 6, anchor.weekday())
        anchor -= timedelta(days=(anchor.weekday() - weekday) % 7)
    compiled["anchor"] = anchor
    return compiled


def _matches(c, day):
    iso = day.isoformat()
    if iso in c["skip"]:
        return False
    if iso in c["extra"]:
        return True
    if c["from"] and day < c["from"]:
        return False
    if c["to"] and day > c["to"]:
        return False

    rec  = c["rec"]
    kind = c["kind"]
    if kind == "dates":
        return iso in c["dates"]

    months = rec.get("months") or []
    if months and day.month not in months:
        return False

    if kind == "weekly":
        if day.weekday() != _clamp_int(rec.get("weekday"), 0, 6, 0):
            return False
        every = _clamp_int(rec.get("interval_weeks"), 1, 12, 1)
        if every <= 1:
            return True
        if c["anchor"] is None:
            return True
        return (((day - c["anchor"]).days // 7) % every) == 0

    if kind == "monthly":
        if rec.get("monthly_by") == "day":
            return day.day == _clamp_int(rec.get("day_of_month"), 1, 31, 1)
        target = _nth_weekday(day.year, day.month,
                              _clamp_int(rec.get("weekday"), 0, 6, 0),
                              _clamp_int(rec.get("week_of_month"), -1, 5, 1))
        return target is not None and target == day

    return False


def type_info(type_id, lang="sk", custom_label=""):
    meta = WASTE_TYPES.get(type_id) or WASTE_TYPES["other"]
    labels = meta["labels"]
    return {
        "id":    type_id if type_id in WASTE_TYPES else "other",
        "label": custom_label or labels.get(lang) or labels["en"],
        "icon":  meta["icon"],
        "color": meta["color"],
    }


def type_catalog(lang="sk"):
    return [type_info(tid, lang) for tid in WASTE_TYPES]


def occurrences(cfg, start, days=UPCOMING_DAYS, lang="sk"):
    """Zoznam dní (od `start`, `days` dopredu), v ktorých sa niečo vyváža."""
    compiled = [_compile_rule(r) for r in (cfg.get("rules") or [])]
    out = []
    for offset in range(max(0, days)):
        day   = start + timedelta(days=offset)
        types = []
        seen  = set()
        for c in compiled:
            if not _matches(c, day):
                continue
            info = type_info(c["type"], lang, c["label"])
            key  = (info["id"], info["label"])
            if key in seen:
                continue
            seen.add(key)
            types.append(info)
        if types:
            out.append({"date": day.isoformat(), "types": types})
    return out


def next_collection(cfg, today=None, lang="sk", horizon=400):
    """Najbližší vývoz od dneška (vrátane) – pre REST senzor v Home Assistante."""
    today = today or date.today()
    found = occurrences(cfg, today, horizon, lang)
    if not found:
        return None
    entry = found[0]
    day   = _parse_date(entry["date"]) or today
    entry = dict(entry)
    entry["days_until"] = (day - today).days
    return entry
