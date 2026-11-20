"""Tests for the config and options flows."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.collectd_mqtt import config_flow
from custom_components.collectd_mqtt.const import (
    CONF_EXCLUDE,
    CONF_HOSTS,
    CONF_INCLUDE,
    CONF_STALE_AFTER,
    CONF_STORE_RATES,
    CONF_TOPIC_PREFIX,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def fast_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not wait five seconds when the probe sees no data."""
    monkeypatch.setattr(config_flow, "PROBE_TIMEOUT", 0.05)


async def _start_flow(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})


async def test_user_flow_creates_entry(hass: HomeAssistant, mqtt) -> None:
    """A flowing topic tree is accepted without further questions."""
    mqtt.probe_message = ("collectd/router/load/load", "1763600000.123:1.0:2.0:3.0")

    result = await _start_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOPIC_PREFIX: "collectd"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "collectd MQTT (collectd)"
    assert result["result"].options == {CONF_TOPIC_PREFIX: "collectd"}


async def test_user_flow_normalizes_prefix(hass: HomeAssistant, mqtt) -> None:
    """Surrounding slashes are not part of the prefix."""
    mqtt.probe_message = ("site/metrics/router/load/load", "1763600000.123:1.0")

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOPIC_PREFIX: "/site/metrics/"}
    )
    assert "site/metrics/#" in mqtt.subscriptions
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].options == {CONF_TOPIC_PREFIX: "site/metrics"}


async def test_user_flow_without_data_can_continue(hass: HomeAssistant, mqtt) -> None:
    """An empty broker is not a hard failure; the user decides."""
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOPIC_PREFIX: "collectd"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "no_data"
    assert result["description_placeholders"] == {"prefix": "collectd"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"confirm_without_data": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_without_data_aborts(hass: HomeAssistant, mqtt) -> None:
    """Declining the confirmation adds nothing."""
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOPIC_PREFIX: "collectd"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"confirm_without_data": False}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_data"


@pytest.mark.parametrize("prefix", ["", "/", "collectd/#", "+", "has space"])
async def test_invalid_prefix(hass: HomeAssistant, mqtt, prefix: str) -> None:
    """Wildcards and blanks are rejected before subscribing."""
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOPIC_PREFIX: prefix}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_prefix"}
    assert mqtt.subscriptions == {}


async def test_mqtt_unavailable(hass: HomeAssistant, mqtt) -> None:
    """The flow explains when MQTT is missing."""
    mqtt.available = False
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOPIC_PREFIX: "collectd"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "mqtt_not_configured"}


async def test_single_instance(hass: HomeAssistant, mqtt) -> None:
    """Only one collectd MQTT entry is allowed."""
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_TOPIC_PREFIX: "collectd"})
    entry.add_to_hass(hass)

    result = await _start_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_updates_and_reloads(hass: HomeAssistant, mqtt) -> None:
    """Options are normalized to lists and the entry reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={CONF_TOPIC_PREFIX: "collectd", CONF_INCLUDE: ["*"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_TOPIC_PREFIX: "collectd",
            CONF_HOSTS: "router-1\nrouter-2",
            CONF_INCLUDE: "cpu-0/*, load/*",
            CONF_EXCLUDE: "*/cpu-idle",
            CONF_STORE_RATES: False,
            CONF_STALE_AFTER: 60,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_TOPIC_PREFIX: "collectd",
        CONF_HOSTS: ["router-1", "router-2"],
        CONF_INCLUDE: ["cpu-0/*", "load/*"],
        CONF_EXCLUDE: ["*/cpu-idle"],
        CONF_STORE_RATES: False,
        CONF_STALE_AFTER: 60,
    }
    assert "collectd/#" in mqtt.subscriptions


async def test_options_flow_rejects_bad_prefix(hass: HomeAssistant, mqtt) -> None:
    """The options form re-renders with an error instead of saving."""
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_TOPIC_PREFIX: "collectd"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_TOPIC_PREFIX: "collectd/#",
            CONF_HOSTS: "",
            CONF_INCLUDE: "",
            CONF_EXCLUDE: "",
            CONF_STORE_RATES: True,
            CONF_STALE_AFTER: 180,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_prefix"}
    assert entry.options == {CONF_TOPIC_PREFIX: "collectd"}
