#!/usr/bin/env python3
"""Testy pre kalendár vývozu odpadu (snapframe/rootfs/usr/bin/waste.py).

Dátumová matematika opakovaní je presne ten druh kódu, ktorý sa pokazí ticho,
preto ju držíme pokrytú. Spustenie: `python3 -m unittest discover -s tests`
"""

import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "snapframe", "rootfs", "usr", "bin"))

os.environ.setdefault("WASTE_CONFIG_FILE",
                      os.path.join(tempfile.mkdtemp(), "waste_schedule.json"))

import waste  # noqa: E402


def cfg_with(*rules):
    return waste.sanitize_config({"enabled": True, "rules": list(rules)})


def dates_of(cfg, start, days=60):
    return [o["date"] for o in waste.occurrences(cfg, start, days)]


class TestWeekly(unittest.TestCase):
    def test_every_week(self):
        cfg = cfg_with({"type": "mixed", "recurrence": {
            "kind": "weekly", "weekday": 3, "interval_weeks": 1}})
        got = dates_of(cfg, date(2026, 8, 23), 22)
        self.assertEqual(got, ["2026-08-27", "2026-09-03", "2026-09-10"])

    def test_every_other_week_uses_anchor_phase(self):
        cfg = cfg_with({"type": "mixed", "recurrence": {
            "kind": "weekly", "weekday": 3, "interval_weeks": 2,
            "anchor": "2026-08-27"}})
        got = dates_of(cfg, date(2026, 8, 23), 36)
        self.assertEqual(got, ["2026-08-27", "2026-09-10", "2026-09-24"])

    def test_phase_holds_before_the_anchor(self):
        """Kotva môže byť aj v budúcnosti – fáza musí platiť oboma smermi."""
        cfg = cfg_with({"type": "mixed", "recurrence": {
            "kind": "weekly", "weekday": 3, "interval_weeks": 2,
            "anchor": "2026-08-27"}})
        got = dates_of(cfg, date(2026, 8, 1), 27)
        self.assertEqual(got, ["2026-08-13", "2026-08-27"])

    def test_misaligned_anchor_is_snapped_to_the_weekday(self):
        """Používateľ zadá dátum, ktorý nepadne na zvolený deň v týždni."""
        cfg = cfg_with({"type": "mixed", "recurrence": {
            "kind": "weekly", "weekday": 3, "interval_weeks": 2,
            "anchor": "2026-08-29"}})          # sobota, nie štvrtok
        self.assertEqual(dates_of(cfg, date(2026, 8, 23), 22),
                         ["2026-08-27", "2026-09-10"])

    def test_interval_without_anchor_falls_back_to_every_week(self):
        cfg = cfg_with({"type": "mixed", "recurrence": {
            "kind": "weekly", "weekday": 0, "interval_weeks": 3}})
        self.assertEqual(cfg["rules"][0]["recurrence"]["interval_weeks"], 1)


class TestMonthly(unittest.TestCase):
    def test_first_monday(self):
        cfg = cfg_with({"type": "paper", "recurrence": {
            "kind": "monthly", "monthly_by": "weekday",
            "weekday": 0, "week_of_month": 1}})
        self.assertEqual(dates_of(cfg, date(2026, 8, 1), 130),
                         ["2026-08-03", "2026-09-07", "2026-10-05",
                          "2026-11-02", "2026-12-07"])

    def test_last_friday(self):
        cfg = cfg_with({"type": "paper", "recurrence": {
            "kind": "monthly", "monthly_by": "weekday",
            "weekday": 4, "week_of_month": -1}})
        self.assertEqual(dates_of(cfg, date(2026, 8, 1), 100),
                         ["2026-08-28", "2026-09-25", "2026-10-30"])

    def test_fifth_weekday_is_skipped_in_months_without_one(self):
        cfg = cfg_with({"type": "paper", "recurrence": {
            "kind": "monthly", "monthly_by": "weekday",
            "weekday": 0, "week_of_month": 5}})
        got = dates_of(cfg, date(2026, 1, 1), 365)
        for iso in got:
            y, m, d = [int(x) for x in iso.split("-")]
            self.assertEqual(date(y, m, d).weekday(), 0)
            self.assertGreaterEqual(d, 29)
        self.assertLess(len(got), 12)   # nie každý mesiac má 5. pondelok

    def test_by_day_of_month_with_month_filter(self):
        cfg = cfg_with({"type": "glass", "recurrence": {
            "kind": "monthly", "monthly_by": "day",
            "day_of_month": 15, "months": [8, 10]}})
        self.assertEqual(dates_of(cfg, date(2026, 8, 1), 120),
                         ["2026-08-15", "2026-10-15"])

    def test_day_31_only_lands_in_long_months(self):
        cfg = cfg_with({"type": "glass", "recurrence": {
            "kind": "monthly", "monthly_by": "day", "day_of_month": 31}})
        # apríl má 30 dní – vypadne, marec a máj ostanú
        self.assertEqual(dates_of(cfg, date(2026, 2, 1), 120),
                         ["2026-03-31", "2026-05-31"])


class TestOverrides(unittest.TestCase):
    def test_skip_and_extra(self):
        cfg = cfg_with({"type": "bio", "recurrence": {
            "kind": "weekly", "weekday": 0, "interval_weeks": 1},
            "skip": ["2026-08-31"], "extra": ["2026-09-02"]})
        got = dates_of(cfg, date(2026, 8, 24), 21)
        self.assertIn("2026-08-24", got)
        self.assertNotIn("2026-08-31", got)     # výnimka
        self.assertIn("2026-09-02", got)        # mimoriadny termín (streda)

    def test_skip_wins_over_extra(self):
        cfg = cfg_with({"type": "bio", "recurrence": {"kind": "dates", "dates": []},
                        "skip": ["2026-09-02"], "extra": ["2026-09-02"]})
        self.assertEqual(dates_of(cfg, date(2026, 9, 1), 10), [])

    def test_extra_ignores_validity_range(self):
        cfg = cfg_with({"type": "bulky", "recurrence": {
            "kind": "weekly", "weekday": 0, "interval_weeks": 1},
            "from": "2026-09-01", "to": "2026-09-30",
            "extra": ["2026-10-20"]})
        got = dates_of(cfg, date(2026, 8, 1), 120)
        self.assertNotIn("2026-08-31", got)     # pred „platí od“
        self.assertIn("2026-09-07", got)
        self.assertNotIn("2026-10-05", got)     # po „platí do“
        self.assertIn("2026-10-20", got)        # mimoriadny termín platí vždy

    def test_two_rules_same_day_are_merged(self):
        cfg = cfg_with(
            {"type": "plastic", "recurrence": {"kind": "dates", "dates": ["2026-09-03"]}},
            {"type": "paper",   "recurrence": {"kind": "dates", "dates": ["2026-09-03"]}})
        occ = waste.occurrences(cfg, date(2026, 9, 1), 10)
        self.assertEqual(len(occ), 1)
        self.assertEqual([t["id"] for t in occ[0]["types"]], ["plastic", "paper"])

    def test_duplicate_type_on_same_day_is_deduplicated(self):
        cfg = cfg_with(
            {"type": "bio", "recurrence": {"kind": "dates", "dates": ["2026-09-03"]}},
            {"type": "bio", "recurrence": {"kind": "dates", "dates": ["2026-09-03"]}})
        occ = waste.occurrences(cfg, date(2026, 9, 1), 10)
        self.assertEqual(len(occ[0]["types"]), 1)

    def test_custom_label_keeps_types_distinct(self):
        cfg = cfg_with(
            {"type": "plastic", "label": "Žlté vrecia",
             "recurrence": {"kind": "dates", "dates": ["2026-09-03"]}},
            {"type": "plastic", "label": "Kovy do vriec",
             "recurrence": {"kind": "dates", "dates": ["2026-09-03"]}})
        occ = waste.occurrences(cfg, date(2026, 9, 1), 10)
        self.assertEqual([t["label"] for t in occ[0]["types"]],
                         ["Žlté vrecia", "Kovy do vriec"])


class TestSanitize(unittest.TestCase):
    def test_junk_input_never_raises(self):
        for junk in (None, [], "text", 42, {"rules": "nope"}, {"rules": [None, 1, {}]}):
            self.assertIsInstance(waste.sanitize_config(junk), dict)

    def test_values_are_clamped_and_whitelisted(self):
        cfg = waste.sanitize_config({
            "mode": "../../etc/passwd", "photo_interval": 10 ** 9,
            "days_before": -5, "start_hour": 99})
        self.assertEqual(cfg["mode"], "overlay")
        self.assertEqual(cfg["photo_interval"], 100)
        self.assertEqual(cfg["days_before"], 0)
        self.assertEqual(cfg["start_hour"], 23)

    def test_days_before_zero_forces_show_on_day(self):
        cfg = waste.sanitize_config({"days_before": 0, "show_on_day": False})
        self.assertTrue(cfg["show_on_day"])

    def test_unknown_waste_type_falls_back_to_other(self):
        cfg = cfg_with({"type": "<script>", "recurrence": {
            "kind": "dates", "dates": ["2026-09-03"]}})
        self.assertEqual(cfg["rules"][0]["type"], "other")

    def test_rule_without_any_date_is_dropped(self):
        self.assertEqual(cfg_with({"type": "bio",
                                   "recurrence": {"kind": "dates", "dates": []}})["rules"], [])

    def test_invalid_dates_are_discarded_and_list_is_sorted(self):
        cfg = cfg_with({"type": "bio", "recurrence": {
            "kind": "dates",
            "dates": ["2026-09-03", "nope", "2026-13-45", "2026-08-01", "2026-09-03"]}})
        self.assertEqual(cfg["rules"][0]["recurrence"]["dates"],
                         ["2026-08-01", "2026-09-03"])

    def test_rule_ids_are_made_unique(self):
        cfg = cfg_with(
            {"id": "x", "type": "bio", "recurrence": {"kind": "dates", "dates": ["2026-09-03"]}},
            {"id": "x", "type": "paper", "recurrence": {"kind": "dates", "dates": ["2026-09-04"]}})
        self.assertNotEqual(cfg["rules"][0]["id"], cfg["rules"][1]["id"])

    def test_rule_count_is_capped(self):
        many = [{"type": "bio", "recurrence": {"kind": "dates", "dates": ["2026-09-03"]}}
                for _ in range(waste.MAX_RULES + 25)]
        self.assertEqual(len(cfg_with(*many)["rules"]), waste.MAX_RULES)


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.old = waste.CONFIG_FILE
        waste.CONFIG_FILE = os.path.join(self.dir, "sub", "waste_schedule.json")

    def tearDown(self):
        waste.CONFIG_FILE = self.old

    def test_missing_file_yields_defaults(self):
        cfg = waste.load_config()
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["rules"], [])

    def test_save_then_load_roundtrip(self):
        cfg = cfg_with({"type": "bio", "recurrence": {
            "kind": "weekly", "weekday": 2, "interval_weeks": 1}})
        waste.save_config(cfg)
        self.assertEqual(waste.load_config(), cfg)

    def test_corrupted_file_falls_back_to_defaults(self):
        os.makedirs(os.path.dirname(waste.CONFIG_FILE), exist_ok=True)
        with open(waste.CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        self.assertEqual(waste.load_config()["rules"], [])


class TestNextCollection(unittest.TestCase):
    def test_today_counts_as_next(self):
        cfg = cfg_with({"type": "bio", "recurrence": {
            "kind": "dates", "dates": ["2026-09-03", "2026-09-10"]}})
        nxt = waste.next_collection(cfg, date(2026, 9, 3))
        self.assertEqual((nxt["date"], nxt["days_until"]), ("2026-09-03", 0))

    def test_days_until_is_relative_to_the_given_day(self):
        cfg = cfg_with({"type": "bio", "recurrence": {
            "kind": "dates", "dates": ["2026-09-10"]}})
        self.assertEqual(waste.next_collection(cfg, date(2026, 9, 3))["days_until"], 7)

    def test_no_upcoming_collection_returns_none(self):
        cfg = cfg_with({"type": "bio", "recurrence": {
            "kind": "dates", "dates": ["2020-01-01"]}})
        self.assertIsNone(waste.next_collection(cfg, date(2026, 9, 3)))


if __name__ == "__main__":
    unittest.main()
