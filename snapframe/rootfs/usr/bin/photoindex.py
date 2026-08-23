#!/usr/bin/env python3
"""
SnapFrame – index fotiek (SQLite v /data).

Prečo:
    Zoznam fotiek je zoradený podľa dátumu z EXIF, takže bez indexu treba pri
    každom /photos otvoriť každú fotku – a tie sú na SMB share. Pri knižnici
    s tisíckami fotiek to znamená tisícky sieťových čítaní každých pár minút,
    pre každý tablet zvlášť. LRU cache v pamäti to nerieši: je menšia než
    knižnica a po reštarte add-onu je prázdna.

Model:
    Kľúč je relatívna cesta, platnosť sa overuje cez mtime súboru – keď sa
    fotka zmení alebo nahradí, riadok sa prepíše. Zemepisná poloha (reverse
    geocoding) sa dopĺňa až keď ju appka naozaj potrebuje, preto môže byť
    NULL aj pri fotke, ktorá GPS súradnice má.
"""

import logging
import os
import sqlite3
import threading

log = logging.getLogger("snapframe.index")

DB_FILE = os.environ.get("PHOTO_INDEX_FILE", "/data/photo_index.db")

_lock = threading.Lock()
_conn = None


def _connect():
    global _conn
    if _conn is not None:
        return _conn
    os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            rel       TEXT PRIMARY KEY,
            mtime     REAL NOT NULL,
            date_ts   REAL,
            lat       REAL,
            lon       REAL,
            location  TEXT
        )
    """)
    conn.commit()
    _conn = conn
    return _conn


def init():
    """Otvorí databázu. Zlyhanie nie je fatálne – beží sa bez indexu."""
    try:
        with _lock:
            _connect()
        return True
    except Exception as e:
        log.warning("Index fotiek sa nepodarilo otvoriť ({}): {}".format(DB_FILE, e))
        return False


def available() -> bool:
    return _conn is not None


def get(rel: str, mtime: float):
    """Riadok pre danú fotku, ak je index platný pre jej aktuálny mtime."""
    try:
        with _lock:
            cur = _connect().execute(
                "SELECT mtime, date_ts, lat, lon, location FROM photos WHERE rel = ?", (rel,))
            row = cur.fetchone()
    except Exception:
        return None
    if row is None or abs(row[0] - mtime) > 0.001:
        return None
    return {"date_ts": row[1], "lat": row[2], "lon": row[3], "location": row[4]}


def all_dates() -> dict:
    """{rel: (mtime, date_ts)} pre celý index – jeden dotaz namiesto N."""
    try:
        with _lock:
            cur = _connect().execute("SELECT rel, mtime, date_ts FROM photos")
            return {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    except Exception:
        return {}


def put(rel: str, mtime: float, date_ts=None, lat=None, lon=None, location=None):
    try:
        with _lock:
            conn = _connect()
            conn.execute(
                "INSERT INTO photos (rel, mtime, date_ts, lat, lon, location) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(rel) DO UPDATE SET mtime=excluded.mtime, "
                "date_ts=excluded.date_ts, lat=excluded.lat, lon=excluded.lon, "
                "location=COALESCE(excluded.location, photos.location)",
                (rel, mtime, date_ts, lat, lon, location))
            conn.commit()
    except Exception as e:
        log.debug("Zápis do indexu zlyhal ({}): {}".format(rel, e))


def set_location(rel: str, location: str):
    try:
        with _lock:
            conn = _connect()
            conn.execute("UPDATE photos SET location = ? WHERE rel = ?", (location, rel))
            conn.commit()
    except Exception as e:
        log.debug("Zápis lokality zlyhal ({}): {}".format(rel, e))


def forget(rel: str):
    try:
        with _lock:
            conn = _connect()
            conn.execute("DELETE FROM photos WHERE rel = ?", (rel,))
            conn.commit()
    except Exception:
        pass


def prune(known_rels) -> int:
    """Zahodí riadky pre fotky, ktoré už v knižnici nie sú."""
    try:
        with _lock:
            conn = _connect()
            cur  = conn.execute("SELECT rel FROM photos")
            gone = [r[0] for r in cur.fetchall() if r[0] not in known_rels]
            if gone:
                conn.executemany("DELETE FROM photos WHERE rel = ?", [(g,) for g in gone])
                conn.commit()
            return len(gone)
    except Exception:
        return 0
