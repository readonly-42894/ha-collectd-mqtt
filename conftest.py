"""Shared pytest configuration for the collectd MQTT integration."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.collectd_mqtt import transport
from custom_components.collectd_mqtt.const import DOMAIN

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components in every test."""
    yield


def _topic_matches(topic: str, pattern: str) -> bool:
    """Match an MQTT topic against a filter with + and # wildcards."""
    topic_parts = topic.split("/")
    pattern_parts = pattern.split("/")
    for index, part in enumerate(pattern_parts):
        if part == "#":
            return True
        if index >= len(topic_parts):
            return False
        if part not in ("+", topic_parts[index]):
            return False
    return len(topic_parts) == len(pattern_parts)


class FakeMqtt:
    """Stand-in for the MQTT integration's subscribe API."""

    def __init__(self) -> None:
        self.subscriptions: dict[str, Any] = {}
        self.connection_callbacks: list[Any] = []
        self.available = True
        self.probe_message: tuple[str, str] | None = None

    async def async_wait_for_mqtt_client(self, _hass: Any) -> bool:
        return self.available

    async def async_subscribe(self, _hass: Any, topic: str, callback: Any):
        self.subscriptions[topic] = callback

        def unsubscribe() -> None:
            self.subscriptions.pop(topic, None)

        if self.probe_message is not None:
            probe_topic, probe_payload = self.probe_message
            callback(
                type("Message", (), {"topic": probe_topic, "payload": probe_payload})()
            )
        return unsubscribe

    def async_subscribe_connection_status(self, _hass: Any, callback: Any):
        self.connection_callbacks.append(callback)

        def unsubscribe() -> None:
            self.connection_callbacks.remove(callback)

        return unsubscribe

    def deliver(self, topic: str, payload: bytes | str) -> None:
        """Deliver a message to every matching subscription."""
        for pattern, callback in list(self.subscriptions.items()):
            if _topic_matches(topic, pattern):
                callback(type("Message", (), {"topic": topic, "payload": payload})())

    def set_connected(self, connected: bool) -> None:
        """Notify listeners about a broker connection change."""
        for callback in list(self.connection_callbacks):
            callback(connected)


@pytest.fixture
def mqtt(monkeypatch: pytest.MonkeyPatch) -> FakeMqtt:
    """Replace the MQTT transport with an in-memory fake."""
    fake = FakeMqtt()
    monkeypatch.setattr(
        transport, "async_wait_for_mqtt_client", fake.async_wait_for_mqtt_client
    )
    monkeypatch.setattr(transport, "async_subscribe", fake.async_subscribe)
    monkeypatch.setattr(
        transport,
        "async_subscribe_connection_status",
        fake.async_subscribe_connection_status,
    )
    return fake


@pytest.fixture
def make_entry():
    """Return a factory that adds a config entry to Home Assistant."""

    def factory(**options: Any) -> MockConfigEntry:
        return MockConfigEntry(domain=DOMAIN, options=options)

    return factory
