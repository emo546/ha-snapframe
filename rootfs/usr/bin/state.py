#!/usr/bin/env python3
"""
Zdieľaný stav medzi watcher.py a webserver.py.
Oba moduly bežia v rovnakom procese (webserver ako daemon vlákno).
"""

import threading
import time as _time

_lock = threading.Lock()

last_scan_time = None    # float – unix timestamp posledného skenu
next_scan_time = None    # float – unix timestamp nasledujúceho skenu
converted_total = 0      # int   – celkový počet skonvertovaných od štartu
_scan_requested = False  # bool  – flag pre manuálny trigger


def request_scan():
    """Vyžiada okamžitý scan (nastavený cez /scan endpoint)."""
    global _scan_requested
    with _lock:
        _scan_requested = True


def consume_scan_request():
    """Ak bol vyžiadaný scan, resetuj flag a vráť True."""
    global _scan_requested
    with _lock:
        if _scan_requested:
            _scan_requested = False
            return True
        return False


def update_after_scan(converted: int, next_scan: float):
    """Watcher zavolá po každom skene."""
    global last_scan_time, next_scan_time, converted_total
    with _lock:
        last_scan_time = _time.time()
        next_scan_time = next_scan
        converted_total += converted


def get_status() -> dict:
    with _lock:
        return {
            "last_scan_time": last_scan_time,
            "next_scan_time": next_scan_time,
            "converted_total": converted_total,
            "scan_pending": _scan_requested,
        }

# ── Progres pregenerácie thumbnailov ─────────────────────────────────────────
thumb_total   = 0    # celkový počet fotiek na spracovanie
thumb_done    = 0    # hotové thumbnaile
thumb_running = False  # práve beží pregenerácia


def thumb_start(total: int):
    global thumb_total, thumb_done, thumb_running
    with _lock:
        thumb_total   = total
        thumb_done    = 0
        thumb_running = True


def thumb_progress(done: int):
    global thumb_done
    with _lock:
        thumb_done = done


def thumb_finish():
    global thumb_running
    with _lock:
        thumb_running = False


def get_thumb_status() -> dict:
    with _lock:
        return {
            "running": thumb_running,
            "total":   thumb_total,
            "done":    thumb_done,
        }

# ── Weather mode (spúšťané pohybovým senzorom cez HA automatizáciu) ─────────
_weather_mode_until = None   # float unix timestamp, None = vypnuté
_weather_data        = None  # dict s poslednými dátami o počasí
_weather_updated_at   = None # float unix timestamp posledného /weather-update


def weather_mode_on(duration_seconds: float):
    """Zapne weather mode na daný počet sekúnd od teraz (opakované volanie predĺži trvanie)."""
    global _weather_mode_until
    with _lock:
        _weather_mode_until = _time.time() + duration_seconds


def weather_mode_off():
    global _weather_mode_until
    with _lock:
        _weather_mode_until = None


def set_weather_data(data: dict):
    global _weather_data, _weather_updated_at
    with _lock:
        _weather_data = data
        _weather_updated_at = _time.time()


def get_weather_status() -> dict:
    with _lock:
        active = _weather_mode_until is not None and _time.time() < _weather_mode_until
        return {
            "active":     active,
            "until":      _weather_mode_until,
            "data":       _weather_data,
            "updated_at": _weather_updated_at,
        }
