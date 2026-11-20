"""Sensor platform for collectd MQTT."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CollectdMqttConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CollectdMqttConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Hand the entity adder to the collector; entities appear as data arrives."""
    entry.runtime_data.async_set_entity_adder(async_add_entities)
