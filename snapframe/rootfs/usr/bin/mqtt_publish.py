#!/usr/bin/env python3
"""
SnapFrame – publikovanie stavu cez MQTT discovery.

Prečo:
    Bez tohto si každý musí v configuration.yaml ručne napísať REST senzor
    na /waste/next a reštartovať Home Assistanta. S MQTT discovery sa entity
    objavia samé a hneď sa dajú použiť v automatizáciách či na dashboarde.

Čo publikujeme:
    * najbližší vývoz odpadu (dátum + atribúty: o koľko dní, ktoré druhy),
    * počet fotiek v knižnici,
    * čas posledného skenu,
    * či je práve zapnutý weather mode.

Spojenie je nepovinné: keď broker nie je nakonfigurovaný alebo paho chýba,
modul sa ticho vypne a zvyšok add-onu beží ďalej.
"""

import json
import logging
import os
import threading
import time
from datetime import date, datetime

log = logging.getLogger("snapframe.mqtt")

HOST     = os.environ.get("MQTT_HOST", "")
PORT     = int(os.environ.get("MQTT_PORT", "1883") or "1883")
USERNAME = os.environ.get("MQTT_USER", "")
PASSWORD = os.environ.get("MQTT_PASSWORD", "")
VERSION  = os.environ.get("SNAPFRAME_VERSION", "")

DISCOVERY_PREFIX = os.environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant")
BASE_TOPIC       = "snapframe"
AVAILABILITY     = BASE_TOPIC + "/availability"
PUBLISH_INTERVAL = 300      # s

_DEVICE = {
    "identifiers":  ["snapframe"],
    "name":         "SnapFrame",
    "manufacturer": "SnapFrame",
    "model":        "Digital photo frame add-on",
}

# (kľúč, doména, meno, ikona, device_class)
_ENTITIES = [
    ("waste_next",   "sensor",        "SnapFrame next waste collection", "mdi:trash-can",      None),
    ("photo_count",  "sensor",        "SnapFrame photos",                "mdi:image-multiple", None),
    ("last_scan",    "sensor",        "SnapFrame last scan",             "mdi:folder-search",  "timestamp"),
    ("weather_mode", "binary_sensor", "SnapFrame weather mode",          "mdi:weather-partly-cloudy", None),
]

_client   = None
_wake     = threading.Event()
_stopping = False


def enabled() -> bool:
    return bool(HOST)


def _state_topic(key):
    return "{}/{}/state".format(BASE_TOPIC, key)


def _attr_topic(key):
    return "{}/{}/attributes".format(BASE_TOPIC, key)


def _publish_discovery(client):
    for key, domain, name, icon, device_class in _ENTITIES:
        config = {
            "name":                 name,
            "unique_id":            "snapframe_" + key,
            "state_topic":          _state_topic(key),
            "json_attributes_topic": _attr_topic(key),
            "availability_topic":   AVAILABILITY,
            "icon":                 icon,
            "device":               dict(_DEVICE, sw_version=VERSION) if VERSION else _DEVICE,
        }
        if device_class:
            config["device_class"] = device_class
        topic = "{}/{}/snapframe/{}/config".format(DISCOVERY_PREFIX, domain, key)
        client.publish(topic, json.dumps(config), qos=1, retain=True)
    log.info("MQTT discovery odoslané ({} entít)".format(len(_ENTITIES)))


def _collect():
    """Aktuálne hodnoty. Každá položka je (state, attributes)."""
    out = {}

    try:
        import webserver
        photos = webserver.list_photos("")
        out["photo_count"] = (len(photos), {})
    except Exception as e:
        log.debug("MQTT: počet fotiek sa nepodarilo zistiť: {}".format(e))

    try:
        import state as _state
        s = _state.get_status()
        if s.get("last_scan_time"):
            out["last_scan"] = (
                datetime.fromtimestamp(s["last_scan_time"]).astimezone().isoformat(),
                {"converted_total": s.get("converted_total", 0)})
        w = _state.get_weather_status()
        out["weather_mode"] = ("ON" if w.get("active") else "OFF", {})
    except Exception as e:
        log.debug("MQTT: stav add-onu sa nepodarilo zistiť: {}".format(e))

    try:
        import waste as _waste
        cfg = _waste.load_config()
        lang = os.environ.get("LANGUAGE", "sk")
        nxt = _waste.next_collection(cfg, date.today(), lang if lang in ("sk", "en", "de") else "sk")
        if nxt:
            out["waste_next"] = (nxt["date"], {
                "days_until": nxt["days_until"],
                "types":      [t["id"] for t in nxt["types"]],
                "text":       ", ".join(t["label"] for t in nxt["types"]),
            })
        else:
            out["waste_next"] = ("", {"days_until": None, "types": [], "text": ""})
    except Exception as e:
        log.debug("MQTT: kalendár odpadu sa nepodarilo zistiť: {}".format(e))

    return out


def _publish_states(client):
    for key, (value, attrs) in _collect().items():
        client.publish(_state_topic(key), str(value), qos=0, retain=True)
        client.publish(_attr_topic(key), json.dumps(attrs, ensure_ascii=False),
                       qos=0, retain=True)


def notify():
    """Vyžiada okamžité publikovanie (napr. po skončení skenu)."""
    _wake.set()


def _loop():
    global _client
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        log.warning("paho-mqtt nie je nainštalované – MQTT sa preskakuje")
        return

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="snapframe")
    except AttributeError:              # paho < 2.0
        client = mqtt.Client(client_id="snapframe")
    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD)
    client.will_set(AVAILABILITY, "offline", qos=1, retain=True)

    while not _stopping:
        try:
            client.connect(HOST, PORT, keepalive=60)
            client.loop_start()
            _client = client
            client.publish(AVAILABILITY, "online", qos=1, retain=True)
            _publish_discovery(client)
            log.info("MQTT pripojené: {}:{}".format(HOST, PORT))
            while not _stopping:
                _publish_states(client)
                _wake.wait(PUBLISH_INTERVAL)
                _wake.clear()
        except Exception as e:
            log.warning("MQTT spojenie zlyhalo ({}), skúsim o 60 s".format(e))
            try:
                client.loop_stop()
            except Exception:
                pass
            time.sleep(60)


def start():
    """Spustí publikovanie na pozadí. Vráti True, ak je MQTT nakonfigurované."""
    if not enabled():
        return False
    threading.Thread(target=_loop, daemon=True, name="mqtt").start()
    return True
