#!/usr/bin/env python3
"""
SnapFrame – import zvozového harmonogramu z PDF (prípadne z obrázka).

Prečo geometria a nie OCR:
    Obecné harmonogramy sú mriežkový kalendár, kde nesie význam FARBA bunky,
    nie text – v texte sú len čísla dní. OCR by vrátilo čísla bez informácie,
    ktoré z nich sú vývozy. Vektorové PDF má ale aj čísla, aj farebné
    obdĺžniky so súradnicami, takže sa dajú spárovať priamo a presne –
    bez OCR, bez siete, bez API kľúča.

Ako sa určuje dátum:
    Riadky sú očíslované číslom ISO týždňa a stĺpce sú dni v týždni, takže
    (ISO týždeň + deň v týždni) dá presný dátum. Vytlačené číslo dňa sa potom
    použije ako kontrola – ak nesedí, bunka sa zahodí. Nemusíme teda vôbec
    riešiť, ktorý blok na stránke je ktorý mesiac.

Čo sa vracia:
    Zoznam "radov" (series) = skupín dní s rovnakým farebným kódom, nie hotové
    druhy odpadu. Paleta sa zámerne nehardcoduje: jedna obec má plasty žlté,
    iná modré, a ten istý leták môže obsahovať dva rôzne harmonogramy naraz
    (napr. dvojtýždňový aj mesačný zvoz zmesového odpadu) – ktorý z nich sa
    týka konkrétnej domácnosti, vie iba používateľ. Priradenie radu k druhu
    odpadu preto robí človek v appke; my ponúkneme len návrh podľa farby.
"""

import base64
import io
import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import date

log = logging.getLogger("snapframe.waste_import")

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MIN_MAPPED_DAYS  = 40      # pod touto hranicou parser vyhlási neúspech
MAX_SERIES       = 24
MAX_DATES        = 400

# Skratky dní v týždni, ktoré vieme rozpoznať v hlavičke tabuľky.
WEEKDAY_HEADERS = {
    "po": 0, "mo": 0, "mon": 0, "pon": 0,
    "ut": 1, "tu": 1, "tue": 1, "di": 1, "út": 1,
    "st": 2, "we": 2, "wed": 2, "mi": 2,
    "št": 3, "st.": 3, "th": 3, "thu": 3, "do": 3, "čt": 3,
    "pi": 4, "fr": 4, "fri": 4, "pá": 4,
    "so": 5, "sa": 5, "sat": 5,
    "ne": 6, "su": 6, "sun": 6, "so.": 6,
}

# Návrh druhu odpadu podľa farby výplne. Len návrh – používateľ ho prepíše.
COLOUR_HINTS = [
    ((0.00, 0.00, 0.00), "mixed",    "čierna"),
    ((0.35, 0.35, 0.35), "mixed",    "sivá"),
    ((0.45, 0.75, 0.30), "mixed",    "zelená"),
    ((0.00, 0.55, 0.25), "glass",    "tmavozelená"),
    ((0.80, 0.40, 0.10), "bio",      "hnedá"),
    ((0.55, 0.27, 0.07), "bio",      "tmavohnedá"),
    ((1.00, 1.00, 0.00), "plastic",  "žltá"),
    ((1.00, 0.75, 0.00), "plastic",  "oranžovožltá"),
    ((0.00, 0.69, 0.94), "paper",    "modrá"),
    ((0.00, 0.44, 0.75), "paper",    "tmavomodrá"),
    ((1.00, 0.00, 0.00), "metal",    "červená"),
    ((0.60, 0.30, 0.70), "electro",  "fialová"),
]


# ── Farby ────────────────────────────────────────────────────────────────────

def _norm_colour(c):
    """PDF farbu (grayscale float / 1-, 3- alebo 4-zložkovú) sprav na RGB 0–1."""
    if c is None:
        return None
    if isinstance(c, (int, float)):
        v = float(c)
        return (v, v, v)
    if isinstance(c, (list, tuple)):
        try:
            vals = [float(x) for x in c]
        except (TypeError, ValueError):
            return None
        if len(vals) == 1:
            return (vals[0],) * 3
        if len(vals) == 3:
            return tuple(vals)
        if len(vals) == 4:                      # CMYK
            cy, m, y, k = vals
            return (max(0.0, 1 - min(1, cy + k)),
                    max(0.0, 1 - min(1, m + k)),
                    max(0.0, 1 - min(1, y + k)))
    return None


def _hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(
        *[max(0, min(255, int(round(v * 255)))) for v in rgb])


def _is_background(rgb):
    """Biela a svetlá sivá sú mriežka/pozadie, nie značka vývozu."""
    r, g, b = rgb
    return min(r, g, b) > 0.80 and (max(r, g, b) - min(r, g, b)) < 0.06


def _colour_hint(rgb):
    best, best_d = ("other", ""), 9.0
    for ref, type_id, name in COLOUR_HINTS:
        d = sum((a - b) ** 2 for a, b in zip(ref, rgb, strict=True))
        if d < best_d:
            best, best_d = (type_id, name), d
    return best if best_d < 0.25 else ("other", "")


# ── Popis pravidelnosti radu ─────────────────────────────────────────────────

WEEKDAY_NAMES = {
    "sk": ["pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota", "nedeľa"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
}

_FREQ = {
    "sk": {7: "každý týždeň", 14: "každé 2 týždne", 21: "každé 3 týždne",
           28: "každé 4 týždne", 0: "nepravidelne"},
    "en": {7: "weekly", 14: "every 2 weeks", 21: "every 3 weeks",
           28: "every 4 weeks", 0: "irregular"},
    "de": {7: "wöchentlich", 14: "alle 2 Wochen", 21: "alle 3 Wochen",
           28: "alle 4 Wochen", 0: "unregelmäßig"},
}


def _summarise(dates, lang="sk"):
    """Ľudský popis radu, napr. 'každé 2 týždne · štvrtok'."""
    if not dates:
        return ""
    names = WEEKDAY_NAMES.get(lang, WEEKDAY_NAMES["sk"])
    freq  = _FREQ.get(lang, _FREQ["sk"])
    parts = []
    if len(dates) > 1:
        gaps = Counter((dates[i + 1] - dates[i]).days for i in range(len(dates) - 1))
        gap, hits = gaps.most_common(1)[0]
        # za pravidelný rad považujeme ten, kde väčšina odstupov sedí
        parts.append(freq.get(gap if hits >= len(dates) * 0.6 else 0, freq[0]))
    wd = Counter(d.weekday() for d in dates)
    if wd and wd.most_common(1)[0][1] >= len(dates) * 0.8:
        parts.append(names[wd.most_common(1)[0][0]])
    return " · ".join(p for p in parts if p)


# ── Parsovanie PDF ───────────────────────────────────────────────────────────

def _guess_year(text, today=None):
    """Rok z hlavičky letáku; inak aktuálny (resp. nasledujúci od decembra)."""
    today = today or date.today()
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text or "")]
    plausible = [y for y in years if today.year - 1 <= y <= today.year + 2]
    if plausible:
        return Counter(plausible).most_common(1)[0][0]
    return today.year + 1 if today.month == 12 else today.year


def _cell_dates(page, year):
    """Spáruj čísla dní s dátumami cez (ISO týždeň, deň v týždni)."""
    words = page.extract_words()
    cx = lambda w: (w["x0"] + w["x1"]) / 2.0        # noqa: E731
    cy = lambda w: (w["top"] + w["bottom"]) / 2.0   # noqa: E731

    headers, weeks, days = [], [], []
    for w in words:
        t = w["text"].strip()
        key = t.lower().rstrip(".")
        if key in WEEKDAY_HEADERS and len(t) <= 4:
            headers.append((w, WEEKDAY_HEADERS[key]))
        elif re.fullmatch(r"\d{1,2}\.", t):
            weeks.append(w)
        elif re.fullmatch(r"\d{1,2}", t):
            days.append(w)
    if not headers or not weeks:
        return []

    out = []
    for n in days:
        hdr, wd = min(headers, key=lambda h: abs(cx(h[0]) - cx(n)))
        if abs(cx(hdr) - cx(n)) > 12:
            continue
        row = [w for w in weeks if abs(cy(w) - cy(n)) < 5 and w["x1"] < n["x0"]]
        if not row:
            continue
        week = int(min(row, key=lambda w: cx(n) - cx(w))["text"].rstrip("."))
        try:
            d = date.fromisocalendar(year, week, wd + 1)
        except ValueError:
            continue
        if d.day != int(n["text"]):     # kontrola proti vytlačenému číslu
            continue
        out.append((d, n))
    return out


def _grid_pitch(cells):
    """Rozostup buniek mriežky (šírka stĺpca, výška riadka) priamo zo stránky.

    Nedá sa použiť konštanta v bodoch: ten istý harmonogram vysádzaný na A4
    a na A5 má iné rozstupy a natvrdo zadaný polomer by pri jednom z nich
    priradil značku susednému dňu.
    """
    xs = sorted({round((w["x0"] + w["x1"]) / 2.0, 1) for _, w in cells})
    ys = sorted({round((w["top"] + w["bottom"]) / 2.0, 1) for _, w in cells})

    def pitch(vals, fallback):
        gaps = [b - a for a, b in zip(vals, vals[1:], strict=False) if 3.0 < b - a < 80.0]
        if not gaps:
            return fallback
        gaps.sort()
        return gaps[len(gaps) // 2]                 # medián odolá odskokom medzi blokmi

    return pitch(xs, 20.0), pitch(ys, 16.0)


def _marks_by_date(page, cells):
    """Ku každému dňu zisti farbu výplne bunky a farby prípadného rámika."""
    cx = lambda w: (w["x0"] + w["x1"]) / 2.0        # noqa: E731
    cy = lambda w: (w["top"] + w["bottom"]) / 2.0   # noqa: E731
    cw, ch = _grid_pitch(cells)
    fills   = {}
    borders = defaultdict(set)
    edges   = []

    def nearest(pool, rx, ry, reach=0.85):
        """Najbližší deň v mierke bunky; None, ak je značka mimo mriežky."""
        if not pool:
            return None
        best = min(pool, key=lambda c: ((cx(c[1]) - rx) / cw) ** 2
                                     + ((cy(c[1]) - ry) / ch) ** 2)
        if abs(cx(best[1]) - rx) > cw * reach or abs(cy(best[1]) - ry) > ch * reach:
            return None
        return best

    for r in page.rects:
        rgb = _norm_colour(r.get("non_stroking_color"))
        if rgb is None or _is_background(rgb):
            continue
        rx, ry = (r["x0"] + r["x1"]) / 2.0, (r["top"] + r["bottom"]) / 2.0
        # Výplň bunky vyplní väčšinu jej plochy; čokoľvek tenšie je kus rámika.
        if r["width"] > cw * 0.6 and r["height"] > ch * 0.6:
            best = nearest(cells, rx, ry)
            if best is not None:
                fills[best[0]] = rgb
        else:
            edges.append((rx, ry, tuple(round(v, 3) for v in rgb)))

    # Rámik sa kreslí PO obvode bunky, takže jeho segmenty ležia bližšie k
    # susednému dňu než k tomu, ktorý zvýrazňujú. Priraď ich preto prednostne
    # k vyfarbenej bunke – rámik zvýrazňuje označený deň, nie prázdny.
    filled = [c for c in cells if c[0] in fills]
    for rx, ry, rgb in edges:
        best = nearest(filled, rx, ry, reach=1.15) or nearest(cells, rx, ry)
        if best is None:
            continue                                # legenda, nie kalendár
        borders[best[0]].add(rgb)
    return fills, borders


def _build_series(fills, borders, lang):
    """Zoskup dni do radov – a to na dvoch úrovniach naraz.

    Rámik okolo bunky totiž neoznačuje iný odpad, ale podmnožinu alebo príplatok:
    na tomto letáku je čierna bunka zvoz zmesového odpadu, pričom čierne bunky
    so zeleným rámikom sú navyše termíny pre domácnosti s mesačnou frekvenciou,
    a hnedý rámik na žltej bunke znamená "BIO aj plast v ten istý deň".
    Preto ponúkame aj súhrn "všetky dni, kde sa daná farba vyskytuje" (fill aj
    rámik), aj jednotlivé presné kombinácie – ktorá z nich platí pre konkrétnu
    domácnosť, rozhodne používateľ v appke.
    """
    combos  = defaultdict(set)   # (výplň, rámik) -> dni
    anycol  = defaultdict(set)   # farba -> dni, kde sa vyskytuje akokoľvek

    for d, rgb in fills.items():
        fill_key = tuple(round(v, 3) for v in rgb)
        edge = sorted(c for c in borders.get(d, ()) if c != fill_key)
        combos[(fill_key, tuple(edge[:1]))].add(d)
        anycol[fill_key].add(d)
        for c in edge:
            anycol[c].add(d)
    for d, edges in borders.items():
        if d in fills:
            continue
        for e in edges:                 # deň označený iba rámikom
            combos[(e, ())].add(d)
            anycol[e].add(d)

    candidates = []
    for colour, dates in anycol.items():
        candidates.append((colour, (), dates, True))
    for (fill_key, edge), dates in combos.items():
        candidates.append((fill_key, edge, dates, False))

    series, seen = [], set()
    for colour, edge, dates, is_aggregate in candidates:
        dates = sorted(dates)[:MAX_DATES]
        if len(dates) < 2:              # jediný výskyt = takmer isto legenda
            continue
        key = (colour, tuple(dates))
        if key in seen:                 # súhrn je zhodný s kombináciou
            continue
        seen.add(key)
        type_id, colour_name = _colour_hint(colour)
        series.append({
            "id":             "s{}".format(len(series) + 1),
            "fill":           _hex(colour),
            "outline":        _hex(edge[0]) if edge else "",
            "colour_name":    colour_name,
            "aggregate":      is_aggregate,
            "suggested_type": type_id,
            "dates":          [d.isoformat() for d in dates],
            "count":          len(dates),
            "summary":        _summarise(dates, lang),
        })
    # najprv súhrny (tie sedia väčšine domácností), v rámci nich najpočetnejšie
    series.sort(key=lambda s: (not s["aggregate"], -s["count"]))
    return series[:MAX_SERIES]


def parse_pdf(data, lang="sk", today=None):
    """Vytiahni rady vývozov z vektorového PDF. Vracia dict, nikdy nevyhadzuje."""
    try:
        import pdfplumber
    except ImportError:
        return {"ok": False, "error": "pdf_unavailable"}

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = pdf.pages[:4]
            text  = " ".join((p.extract_text() or "") for p in pages)
            year  = _guess_year(text, today)
            fills, borders, mapped = {}, defaultdict(set), 0
            for page in pages:
                cells = _cell_dates(page, year)
                mapped += len(cells)
                if not cells:
                    continue
                f, b = _marks_by_date(page, cells)
                fills.update(f)
                for d, e in b.items():
                    borders[d] |= e
    except Exception as e:                       # poškodené PDF, heslo, …
        log.warning("Parsovanie PDF zlyhalo: {}".format(e))
        return {"ok": False, "error": "pdf_parse_failed"}

    if mapped < MIN_MAPPED_DAYS:
        return {"ok": False, "error": "no_calendar_found", "year": year}
    series = _build_series(fills, borders, lang)
    if not series:
        return {"ok": False, "error": "no_marks_found", "year": year}
    return {"ok": True, "source": "pdf", "year": year, "series": series}


# ── Záložná cesta cez vision model ───────────────────────────────────────────

_VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "year": {"type": "integer"},
        "series": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "colour_name": {"type": "string"},
                    "fill": {"type": "string"},
                    "suggested_type": {
                        "type": "string",
                        "enum": ["mixed", "bio", "plastic", "paper", "glass",
                                 "metal", "tetrapak", "electro", "bulky", "other"],
                    },
                    "dates": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["colour_name", "fill", "suggested_type", "dates"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["year", "series"],
    "additionalProperties": False,
}

_VISION_PROMPT = """Toto je obecný harmonogram vývozu odpadu.

Vytiahni z neho VŠETKY termíny vývozu. Jeden "rad" (series) = jedna kombinácia
farby/značky, ktorá v kalendári označuje jeden druh vývozu.

Pravidlá:
- dátumy vracaj ako YYYY-MM-DD
- rok urči z dokumentu; ak tam nie je, použi {year}
- ak dokument obsahuje viac variantov toho istého odpadu (napr. dvojtýždňový
  a mesačný zvoz zmesového odpadu), vráť ich ako SAMOSTATNÉ rady – nezlučuj ich
- `fill` je farba značky ako #rrggbb, `colour_name` jej názov tak, ako je
  pomenovaná v legende (napr. "čierna nádoba")
- nič nedomýšľaj: vráť len dni, ktoré sú v dokumente naozaj označené
"""


def parse_with_vision(data, media_type, lang="sk", api_key=None, model="claude-opus-5",
                      today=None):
    """Záloha pre skeny, fotky a PDF, ktorých rozloženie parser nepozná."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "no_api_key"}
    try:
        import anthropic
    except ImportError:
        return {"ok": False, "error": "vision_unavailable"}

    year  = (today or date.today()).year
    block = ({"type": "document",
              "source": {"type": "base64", "media_type": "application/pdf",
                         "data": base64.b64encode(data).decode("ascii")}}
             if media_type == "application/pdf" else
             {"type": "image",
              "source": {"type": "base64", "media_type": media_type,
                         "data": base64.b64encode(data).decode("ascii")}})
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": _VISION_SCHEMA}},
            messages=[{"role": "user", "content": [
                block, {"type": "text", "text": _VISION_PROMPT.format(year=year)}]}],
        )
        if getattr(resp, "stop_reason", "") == "refusal":
            return {"ok": False, "error": "vision_refused"}
        raw = json.loads(next(b.text for b in resp.content if b.type == "text"))
    except Exception as e:
        log.warning("Vision extrakcia zlyhala: {}".format(e))
        return {"ok": False, "error": "vision_failed"}

    series = []
    for item in (raw.get("series") or [])[:MAX_SERIES]:
        dates = sorted({d for d in (item.get("dates") or [])
                        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d))})[:MAX_DATES]
        if not dates:
            continue
        parsed = [date(*map(int, d.split("-"))) for d in dates]
        fill = str(item.get("fill") or "")
        series.append({
            "id":             "v{}".format(len(series) + 1),
            "fill":           fill if re.fullmatch(r"#[0-9a-fA-F]{6}", fill) else "#9aa5b1",
            "outline":        "",
            "colour_name":    str(item.get("colour_name") or "")[:40],
            "suggested_type": str(item.get("suggested_type") or "other"),
            "dates":          dates,
            "count":          len(dates),
            "summary":        _summarise(parsed, lang),
        })
    if not series:
        return {"ok": False, "error": "no_marks_found"}
    return {"ok": True, "source": "vision",
            "year": int(raw.get("year") or year), "series": series}
