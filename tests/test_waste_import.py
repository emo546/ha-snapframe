#!/usr/bin/env python3
"""Testy pre import zvozového harmonogramu (waste_import.py).

Geometrické parsovanie sa dá ticho pokaziť zmenou jednej konštanty, preto sú
testy postavené na PDF, ktoré si sami vygenerujeme – vieme teda presne, ktoré
dni sú označené, a môžeme overiť, že parser vráti presne tie.
"""

import io
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "snapframe", "rootfs", "usr", "bin"))

import waste_import as wi  # noqa: E402

try:
    import reportlab  # noqa: F401
    HAVE_REPORTLAB = True
except ImportError:
    HAVE_REPORTLAB = False

try:
    import pdfplumber  # noqa: F401
    HAVE_PDFPLUMBER = True
except ImportError:
    HAVE_PDFPLUMBER = False


def build_pdf(marks, year=2026, weeks=tuple(range(1, 13))):
    """Malý kalendár: riadok = ISO týždeň, stĺpec = deň. `marks` = {date: (rgb, edge)}."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 8)
    c.drawString(40, 800, "Zvozovy harmonogram {}".format(year))
    x0, y0, cw, ch = 60, 760, 22.0, 16.0
    for i, _name in enumerate(["Po", "Ut", "St", "St", "Pi"]):
        c.drawString(x0 + 30 + i * cw + 6, y0 + 6, ["Po", "Ut", "St", "Št", "Pi"][i])
    for row, wk in enumerate(weeks):
        y = y0 - (row + 1) * ch
        c.drawString(x0, y + 4, "{}.".format(wk))
        for col in range(5):
            try:
                d = date.fromisocalendar(year, wk, col + 1)
            except ValueError:
                continue
            cx = x0 + 30 + col * cw
            if d in marks:
                rgb, edge = marks[d]
                if edge:
                    c.setFillColorRGB(*edge)
                    for ex, ey, ew, eh in ((cx, y - 3, cw, 3), (cx, y + ch, cw, 3),
                                           (cx - 3, y, 3, ch), (cx + cw, y, 3, ch)):
                        c.rect(ex, ey, ew, eh, stroke=0, fill=1)
                c.setFillColorRGB(*rgb)
                c.rect(cx, y, cw, ch, stroke=0, fill=1)
            c.setFillColorRGB(0, 0, 0) if d not in marks else c.setFillColorRGB(1, 1, 1)
            c.drawString(cx + 7, y + 4, str(d.day))
            c.setFillColorRGB(0, 0, 0)
    c.showPage()
    c.save()
    return buf.getvalue()


class TestHelpers(unittest.TestCase):
    def test_colour_normalisation(self):
        self.assertEqual(wi._norm_colour(0.0), (0.0, 0.0, 0.0))       # grayscale
        self.assertEqual(wi._norm_colour([0.5]), (0.5, 0.5, 0.5))     # 1-zložkové
        self.assertEqual(wi._norm_colour((1, 0, 0)), (1, 0, 0))       # RGB
        self.assertEqual(wi._norm_colour((0, 0, 0, 0)), (1, 1, 1))    # CMYK biela
        self.assertIsNone(wi._norm_colour(None))
        self.assertIsNone(wi._norm_colour("modra"))

    def test_background_detection(self):
        self.assertTrue(wi._is_background((1.0, 1.0, 1.0)))
        self.assertTrue(wi._is_background((0.851, 0.851, 0.851)))     # mriežka
        self.assertFalse(wi._is_background((0.0, 0.0, 0.0)))
        self.assertFalse(wi._is_background((1.0, 1.0, 0.0)))          # žltá je značka

    def test_hex_output(self):
        self.assertEqual(wi._hex((0, 0, 0)), "#000000")
        self.assertEqual(wi._hex((1, 1, 0)), "#ffff00")

    def test_colour_hints(self):
        self.assertEqual(wi._colour_hint((1.0, 1.0, 0.0))[0], "plastic")
        self.assertEqual(wi._colour_hint((0.0, 0.69, 0.94))[0], "paper")
        self.assertEqual(wi._colour_hint((0.80, 0.40, 0.10))[0], "bio")
        self.assertEqual(wi._colour_hint((0.0, 0.0, 0.0))[0], "mixed")
        self.assertEqual(wi._colour_hint((0.5, 1.0, 1.0))[0], "other")     # bledá tyrkysová – ďaleko od všetkých

    def test_year_guess(self):
        today = date(2026, 5, 1)
        self.assertEqual(wi._guess_year("Harmonogram 2026", today), 2026)
        self.assertEqual(wi._guess_year("nic tu nie je", today), 2026)
        self.assertEqual(wi._guess_year("rok 1998", today), 2026)           # nepravdepodobný
        self.assertEqual(wi._guess_year("", date(2026, 12, 3)), 2027)       # v decembri už ďalší

    def test_summary(self):
        every2 = [date.fromordinal(date(2026, 1, 1).toordinal() + 14 * i) for i in range(6)]
        self.assertIn("každé 2 týždne", wi._summarise(every2, "sk"))
        self.assertIn("štvrtok", wi._summarise(every2, "sk"))
        self.assertIn("every 2 weeks", wi._summarise(every2, "en"))
        self.assertEqual(wi._summarise([], "sk"), "")

    def test_missing_dependency_is_reported_not_raised(self):
        self.assertFalse(wi.parse_pdf(b"nie je to pdf")["ok"])

    def test_vision_without_key_is_reported(self):
        r = wi.parse_with_vision(b"x", "image/png", api_key="")
        self.assertEqual(r["error"], "no_api_key")


@unittest.skipUnless(HAVE_REPORTLAB and HAVE_PDFPLUMBER,
                     "vyžaduje reportlab + pdfplumber")
class TestParsePdf(unittest.TestCase):
    BLACK, YELLOW, GREEN = (0, 0, 0), (1, 1, 0), (0.57, 0.82, 0.31)

    def test_extracts_exactly_the_marked_days(self):
        marks = {date(2026, 1, 1): (self.BLACK, None),
                 date(2026, 1, 15): (self.BLACK, None),
                 date(2026, 1, 29): (self.BLACK, None)}
        r = wi.parse_pdf(build_pdf(marks))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["year"], 2026)
        black = [s for s in r["series"] if s["fill"] == "#000000"]
        self.assertTrue(black)
        self.assertEqual(black[0]["dates"],
                         ["2026-01-01", "2026-01-15", "2026-01-29"])

    def test_two_colours_become_two_series(self):
        marks = {date(2026, 1, 1): (self.BLACK, None),
                 date(2026, 1, 15): (self.BLACK, None),
                 date(2026, 1, 5): (self.YELLOW, None),
                 date(2026, 1, 19): (self.YELLOW, None)}
        r = wi.parse_pdf(build_pdf(marks))
        fills = {s["fill"] for s in r["series"]}
        self.assertIn("#000000", fills)
        self.assertIn("#ffff00", fills)

    def test_outline_yields_both_a_subset_and_an_aggregate(self):
        """Rámik označuje podmnožinu – používateľ musí vidieť aj celok, aj časť."""
        marks = {date(2026, 1, 1): (self.BLACK, self.GREEN),
                 date(2026, 1, 15): (self.BLACK, None),
                 date(2026, 1, 29): (self.BLACK, self.GREEN)}
        r = wi.parse_pdf(build_pdf(marks))
        black_all = [s for s in r["series"]
                     if s["fill"] == "#000000" and s["aggregate"]]
        self.assertEqual(len(black_all), 1)
        self.assertEqual(len(black_all[0]["dates"]), 3)          # celý rad
        green = [s for s in r["series"] if s["fill"].lower() in ("#92d14f", "#92d14e", "#92d150")
                 or s["colour_name"] == "zelená"]
        self.assertTrue(green, [s["fill"] for s in r["series"]])
        self.assertEqual(len(green[0]["dates"]), 2)              # iba orámované dni

    def test_suggested_type_follows_the_colour(self):
        marks = {date(2026, 1, 5): (self.YELLOW, None),
                 date(2026, 1, 19): (self.YELLOW, None)}
        r = wi.parse_pdf(build_pdf(marks))
        yellow = [s for s in r["series"] if s["fill"] == "#ffff00"][0]
        self.assertEqual(yellow["suggested_type"], "plastic")

    def test_single_occurrence_is_ignored_as_legend(self):
        marks = {date(2026, 1, 5): (self.YELLOW, None)}
        r = wi.parse_pdf(build_pdf(marks))
        self.assertFalse([s for s in r.get("series", []) if s["fill"] == "#ffff00"])

    def test_calendar_without_marks_is_reported(self):
        r = wi.parse_pdf(build_pdf({}))
        self.assertFalse(r["ok"])
        self.assertIn(r["error"], ("no_marks_found", "no_calendar_found"))

    def test_garbage_input_never_raises(self):
        for junk in (b"", b"not a pdf", b"%PDF-1.4 broken", os.urandom(400)):
            self.assertFalse(wi.parse_pdf(junk)["ok"])


if __name__ == "__main__":
    unittest.main()
