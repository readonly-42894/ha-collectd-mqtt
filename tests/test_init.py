"""Runtime tests for collectd MQTT setup, entities and availability."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.collectd_mqtt.const import (
    CONF_EXCLUDE,
    CONF_INCLUDE,
    CONF_STALE_AFTER,
    CONF_STORE_RATES,
    CONF_TOPIC_PREFIX,
    DOMAIN,
)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _flush(hass: HomeAssistant) -> None:
    """Run the deferred entity creation."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entity_id: str):
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} was not created"
    return state


async def test_creates_sensor_from_plain_payload(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """One value list becomes one sensor on the host device."""
    entry = await _setup(hass, make_entry())
    assert mqtt.subscriptions == {"collectd/#": mqtt.subscriptions["collectd/#"]}

    mqtt.deliver("collectd/router/cpu-0/cpu-user", "1763600000.123:0.45")
    await _flush(hass)

    state = _state(hass, "sensor.router_cpu_0_user")
    assert state.state == "0.45"
    assert "unit_of_measurement" not in state.attributes
    assert state.attributes["state_class"] == "measurement"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [device.name for device in devices] == ["router"]
    assert devices[0].manufacturer == "collectd"
    assert devices[0].model == "collectd metrics"
    assert entry.state is ConfigEntryState.LOADED


async def test_multi_value_metrics_become_multiple_sensors(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """Data source names from types.db separate rx from tx."""
    await _setup(hass, make_entry())
    mqtt.deliver("collectd/router/interface-eth0/if_octets", "1763600000.123:12.5:34.5")
    await _flush(hass)

    rx = _state(hass, "sensor.router_interface_eth0_rx")
    tx = _state(hass, "sensor.router_interface_eth0_tx")
    assert rx.state == "12.5"
    assert tx.state == "34.5"
    assert rx.attributes["unit_of_measurement"] == "B/s"
    assert rx.attributes["device_class"] == "data_rate"


async def test_updates_existing_sensor(hass: HomeAssistant, mqtt, make_entry) -> None:
    """Later messages keep the same entity and replace its value."""
    await _setup(hass, make_entry())
    mqtt.deliver("collectd/router/memory/memory-used", "1763600000.123:1048576")
    await _flush(hass)
    mqtt.deliver("collectd/router/memory/memory-used", "1763600010.123:2097152")
    await hass.async_block_till_done()

    state = _state(hass, "sensor.router_memory_used")
    assert state.state == "2097152.0"
    assert state.attributes["unit_of_measurement"] == "B"
    assert state.attributes["device_class"] == "data_size"


async def test_unknown_type_keeps_numbers(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """Types missing from types.db still produce named data sources."""
    await _setup(hass, make_entry())
    mqtt.deliver("collectd/router/mystery/mystery-widget", "1763600000.123:1.0:2.0")
    await _flush(hass)

    assert _state(hass, "sensor.router_mystery_widget").state == "1.0"
    assert _state(hass, "sensor.router_mystery_widget_value_1").state == "2.0"


async def test_include_and_exclude_filters(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """Only matching metrics create entities."""
    entry = await _setup(
        hass,
        make_entry(
            **{
                CONF_INCLUDE: ["interface-*/if_octets"],
                CONF_EXCLUDE: ["interface-eth1/*"],
            }
        ),
    )
    mqtt.deliver("collectd/router/cpu-0/cpu-user", "1763600000.123:0.5")
    mqtt.deliver("collectd/router/interface-eth0/if_octets", "1763600000.123:1.0:2.0")
    mqtt.deliver("collectd/router/interface-eth1/if_octets", "1763600000.123:1.0:2.0")
    await _flush(hass)

    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert {item.entity_id for item in entries} == {
        "sensor.router_interface_eth0_rx",
        "sensor.router_interface_eth0_tx",
    }


async def test_host_filter(hass: HomeAssistant, mqtt, make_entry) -> None:
    """A host allow-list keeps other collectd hosts silent."""
    await _setup(hass, make_entry(hosts=["edge-*"]))
    mqtt.deliver("collectd/core-1/load/load", "1763600000.123:1.0:2.0:3.0")
    mqtt.deliver("collectd/edge-1/load/load", "1763600000.123:1.0:2.0:3.0")
    await _flush(hass)

    assert _state(hass, "sensor.edge_1_load_shortterm").state == "1.0"
    assert hass.states.get("sensor.core_1_load_shortterm") is None


async def test_custom_topic_prefix(hass: HomeAssistant, mqtt, make_entry) -> None:
    """The topic prefix is transport configuration only."""
    await _setup(hass, make_entry(**{CONF_TOPIC_PREFIX: "site/metrics"}))
    assert "site/metrics/#" in mqtt.subscriptions

    mqtt.deliver("site/metrics/router/uptime/uptime", "1763600000.123:123456")
    await _flush(hass)
    assert _state(hass, "sensor.router_uptime").state == "123456.0"


async def test_store_rates_disabled_marks_counters_as_totals(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """Raw counters use the total_increasing state class."""
    await _setup(hass, make_entry(**{CONF_STORE_RATES: False}))
    mqtt.deliver("collectd/router/interface-eth0/if_octets", "1763600000.123:1024:2048")
    await _flush(hass)

    state = _state(hass, "sensor.router_interface_eth0_rx")
    assert state.state == "1024.0"
    assert state.attributes["unit_of_measurement"] == "B"
    assert state.attributes["state_class"] == "total_increasing"


async def test_non_metric_messages_are_ignored(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """Notifications, JSON and malformed payloads never become entities."""
    await _setup(hass, make_entry())
    mqtt.deliver(
        "collectd/event/router/cpu-0/cpu-user",
        "Time: 1763600000.123\r\nSeverity: FAILURE\r\nMessage: disk full",
    )
    mqtt.deliver("collectd/router/cpu-0/cpu-user", '[{"values":[0.5]}]')
    mqtt.deliver("collectd/router/cpu-0/cpu-user", "1763600000.123:oops")
    mqtt.deliver("collectd/router/memory/memory-used", "1763600000.123:nan")
    await _flush(hass)

    assert hass.states.async_entity_ids("sensor") == []


async def test_stale_values_become_unavailable(
    hass: HomeAssistant, mqtt, make_entry, freezer
) -> None:
    """A metric that stops publishing is marked unavailable."""
    freezer.move_to("2026-01-01 00:00:00+00:00")
    await _setup(hass, make_entry(**{CONF_STALE_AFTER: 5}))
    mqtt.deliver("collectd/router/cpu-0/cpu-user", "1763600000.123:0.5")
    await _flush(hass)

    freezer.tick(timedelta(seconds=40))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _state(hass, "sensor.router_cpu_0_user").state == STATE_UNAVAILABLE

    mqtt.deliver("collectd/router/cpu-0/cpu-user", "1763600040.123:0.7")
    await hass.async_block_till_done()
    assert _state(hass, "sensor.router_cpu_0_user").state == "0.7"


async def test_broker_disconnect_marks_entities_unavailable(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """The MQTT connection state drives entity availability."""
    await _setup(hass, make_entry())
    mqtt.deliver("collectd/router/load/load", "1763600000.123:1.0:2.0:3.0")
    await _flush(hass)

    mqtt.set_connected(False)
    await hass.async_block_till_done()
    assert _state(hass, "sensor.router_load_shortterm").state == STATE_UNAVAILABLE

    mqtt.set_connected(True)
    mqtt.deliver("collectd/router/load/load", "1763600010.123:4.0:5.0:6.0")
    await hass.async_block_till_done()
    assert _state(hass, "sensor.router_load_shortterm").state == "4.0"


async def test_filtered_metric_removes_existing_entities(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """Entities excluded by new options are removed from the registry."""
    entry = await _setup(hass, make_entry())
    mqtt.deliver("collectd/router/cpu-0/cpu-user", "1763600000.123:0.5")
    await _flush(hass)
    assert _state(hass, "sensor.router_cpu_0_user").state == "0.5"

    hass.config_entries.async_update_entry(entry, options={CONF_INCLUDE: ["load/load"]})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    mqtt.deliver("collectd/router/cpu-0/cpu-user", "1763600010.123:0.5")
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "router|cpu|0|cpu|user|value")
        is None
    )
    assert hass.states.get("sensor.router_cpu_0_user") is None


async def test_setup_retries_without_mqtt(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """A missing MQTT integration is retried instead of failing the entry."""
    mqtt.available = False
    entry = make_entry()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_removes_subscription(
    hass: HomeAssistant, mqtt, make_entry
) -> None:
    """Unloading releases the wildcard subscription."""
    entry = await _setup(hass, make_entry())
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert mqtt.subscriptions == {}


async def test_float_formatting(hass: HomeAssistant, mqtt, make_entry) -> None:
    """Values keep enough precision for rate sensors."""
    await _setup(hass, make_entry())
    mqtt.deliver(
        "collectd/router/disk-sda/disk_octets", "1763600000.123:1024.5:2048.25"
    )
    await _flush(hass)

    assert _state(hass, "sensor.router_disk_sda_read").state == "1024.5"
    assert _state(hass, "sensor.router_disk_sda_write").state == "2048.25"


@pytest.mark.parametrize(
    ("options", "topic", "payload", "expected"),
    [
        (
            {CONF_INCLUDE: ["*/percent-*"]},
            "collectd/router/cpu-0/percent-user",
            "1763600000.123:12.5",
            "sensor.router_cpu_0_percent_user",
        ),
        (
            {CONF_INCLUDE: ["*/ps_state-*"]},
            "collectd/router/ps/ps_state-running",
            "1763600000.123:3",
            "sensor.router_processes_state_running",
        ),
        (
            {CONF_INCLUDE: ["df-*/df_complex-*"]},
            "collectd/router/df-root/df_complex-used",
            "1763600000.123:734003200",
            "sensor.router_df_root_used",
        ),
        (
            {CONF_INCLUDE: ["thermal-*/temperature"]},
            "collectd/router/thermal-0/temperature",
            "1763600000.123:42.5",
            "sensor.router_thermal_0_temperature",
        ),
    ],
    ids=["percent", "process-state", "df", "thermal"],
)
async def test_representative_metrics(
    hass: HomeAssistant,
    mqtt,
    make_entry,
    options: dict[str, Any],
    topic: str,
    payload: str,
    expected: str,
) -> None:
    """Common plugin families resolve to readable entity IDs."""
    await _setup(hass, make_entry(**options))
    mqtt.deliver(topic, payload)
    await _flush(hass)
    assert _state(hass, expected) is not None
