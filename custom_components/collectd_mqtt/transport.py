"""Thin wrappers around the MQTT integration's subscribe API.

Home Assistant owns the broker connection; this module is the single place
that imports it, which also gives the tests one seam to stub.
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.mqtt import (
    async_subscribe as _async_subscribe,
)
from homeassistant.components.mqtt import (
    async_subscribe_connection_status as _async_subscribe_connection_status,
)
from homeassistant.components.mqtt import (
    async_wait_for_mqtt_client as _async_wait_for_mqtt_client,
)
from homeassistant.core import HomeAssistant, callback

ConnectionCallback = Callable[[bool], None]


async def async_wait_for_mqtt_client(hass: HomeAssistant) -> bool:
    """Wait for the MQTT integration to become available."""
    return await _async_wait_for_mqtt_client(hass)


async def async_subscribe(
    hass: HomeAssistant,
    topic: str,
    msg_callback: Callable,
) -> Callable[[], None]:
    """Subscribe to a topic and return the unsubscribe callback."""
    return await _async_subscribe(hass, topic, msg_callback, encoding=None)


@callback
def async_subscribe_connection_status(
    hass: HomeAssistant, connection_callback: ConnectionCallback
) -> Callable[[], None]:
    """Subscribe to MQTT connection state changes."""
    return _async_subscribe_connection_status(hass, connection_callback)
