#!/usr/bin/env python3
"""Testy MQTT discovery – bez brokera, na falošnom klientovi."""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapframe" / "rootfs" / "usr" / "bin"))

import mqtt_publish   # noqa: E402


class FakeClient:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.messages.append((topic, payload, retain))


class TestDiscovery(unittest.TestCase):
    def test_discovery_payloads_are_valid_and_retained(self):
        client = FakeClient()
        mqtt_publish._publish_discovery(client)
        self.assertEqual(len(client.messages), len(mqtt_publish._ENTITIES))
        for topic, payload, retain in client.messages:
            with self.subTest(topic=topic):
                self.assertTrue(retain, "discovery musí byť retained, inak entity po reštarte zmiznú")
                self.assertTrue(topic.startswith("homeassistant/"))
                cfg = json.loads(payload)
                self.assertIn("unique_id", cfg)
                self.assertIn("state_topic", cfg)
                self.assertIn("availability_topic", cfg)
                self.assertEqual(cfg["device"]["identifiers"], ["snapframe"])

    def test_unique_ids_do_not_collide(self):
        client = FakeClient()
        mqtt_publish._publish_discovery(client)
        ids = [json.loads(p)["unique_id"] for _, p, _ in client.messages]
        self.assertEqual(len(ids), len(set(ids)))

    def test_disabled_without_a_broker(self):
        original = mqtt_publish.HOST
        try:
            mqtt_publish.HOST = ""
            self.assertFalse(mqtt_publish.enabled())
            self.assertFalse(mqtt_publish.start())
        finally:
            mqtt_publish.HOST = original


class TestCollect(unittest.TestCase):
    def test_collect_survives_missing_modules(self):
        """Zber hodnôt nesmie spadnúť, aj keď niektorý modul nie je dostupný."""
        os.environ.setdefault("WASTE_CONFIG_FILE", "/nonexistent/waste.json")
        values = mqtt_publish._collect()
        self.assertIsInstance(values, dict)
        for key, (_state, attrs) in values.items():
            with self.subTest(key=key):
                self.assertIsInstance(attrs, dict)
                json.dumps(attrs)      # atribúty musia byť serializovateľné


if __name__ == "__main__":
    unittest.main()
