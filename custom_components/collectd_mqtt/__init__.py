"""The collectd MQTT integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError

from . import transport
from .const import DOMAIN, PLATFORMS
from .coordinator import CollectdCollector

_LOGGER = logging.getLogger(__name__)

type CollectdMqttConfigEntry = ConfigEntry[CollectdCollector]


async def async_setup_entry(
    hass: HomeAssistant, entry: CollectdMqttConfigEntry
) -> bool:
    """Set up collectd MQTT from a config entry."""
    if not await transport.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("The MQTT integration is not available")

    collector = CollectdCollector(hass, entry)
    entry.runtime_data = collector

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    try:
        await collector.async_start()
    except HomeAssistantError as err:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        raise ConfigEntryNotReady(str(err)) from err

    _LOGGER.debug("Subscribed to %s/# for collectd metrics", collector.prefix)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CollectdMqttConfigEntry
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


__all__ = ["DOMAIN", "CollectdMqttConfigEntry"]
