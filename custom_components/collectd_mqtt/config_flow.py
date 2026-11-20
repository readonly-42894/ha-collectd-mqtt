"""Config flow for the collectd MQTT integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from . import transport
from .const import (
    CONF_EXCLUDE,
    CONF_HOSTS,
    CONF_INCLUDE,
    CONF_STALE_AFTER,
    CONF_STORE_RATES,
    CONF_TOPIC_PREFIX,
    DEFAULT_STALE_AFTER,
    DEFAULT_STORE_RATES,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    NAME,
)
from .coordinator import as_pattern_list

_LOGGER = logging.getLogger(__name__)

PROBE_TIMEOUT = 5

CONF_PROBE = "confirm_without_data"


def _normalize_prefix(value: str) -> str:
    """Validate and normalize a topic prefix."""
    prefix = value.strip().strip("/")
    if not prefix or any(char in prefix for char in "+#") or " " in prefix:
        raise ValueError("invalid topic prefix")
    return prefix


async def _probe(hass: HomeAssistant, prefix: str) -> int:
    """Count the messages published below a prefix for a few seconds."""
    received = 0
    seen = asyncio.Event()

    @callback
    def _on_message(_message: Any) -> None:
        nonlocal received
        received += 1
        seen.set()

    unsubscribe = await transport.async_subscribe(hass, f"{prefix}/#", _on_message)
    try:
        async with asyncio.timeout(PROBE_TIMEOUT):
            await seen.wait()
    except TimeoutError:
        pass
    finally:
        unsubscribe()
    return received


class CollectdMqttConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the collectd topic prefix and verify that data is flowing."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> CollectdMqttOptionsFlow:
        """Return the options flow for this handler."""
        return CollectdMqttOptionsFlow()

    def __init__(self) -> None:
        """Initialize the flow."""
        self._prefix = DEFAULT_TOPIC_PREFIX

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                prefix = _normalize_prefix(user_input[CONF_TOPIC_PREFIX])
            except ValueError:
                errors["base"] = "invalid_prefix"
            else:
                if not await transport.async_wait_for_mqtt_client(self.hass):
                    errors["base"] = "mqtt_not_configured"
                else:
                    try:
                        received = await _probe(self.hass, prefix)
                    except HomeAssistantError:
                        errors["base"] = "cannot_connect"
                    else:
                        if received == 0:
                            self._prefix = prefix
                            return await self.async_step_no_data()
                        return self._create_entry(prefix)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOPIC_PREFIX, default=self._prefix): TextSelector(
                        TextSelectorConfig()
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_no_data(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether to continue when no message was seen during the probe."""
        if user_input is not None:
            if user_input.get(CONF_PROBE):
                return self._create_entry(self._prefix)
            return self.async_abort(reason="no_data")
        return self.async_show_form(
            step_id="no_data",
            data_schema=vol.Schema(
                {vol.Required(CONF_PROBE, default=False): BooleanSelector()}
            ),
            description_placeholders={"prefix": self._prefix},
        )

    def _create_entry(self, prefix: str) -> ConfigFlowResult:
        self._prefix = prefix
        return self.async_create_entry(
            title=f"{NAME} ({prefix})",
            data={},
            options={CONF_TOPIC_PREFIX: prefix},
        )


class CollectdMqttOptionsFlow(OptionsFlowWithReload):
    """Edit the metric filters and interpretation options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the options form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                prefix = _normalize_prefix(user_input[CONF_TOPIC_PREFIX])
            except ValueError:
                errors["base"] = "invalid_prefix"
            else:
                options = {
                    CONF_TOPIC_PREFIX: prefix,
                    CONF_HOSTS: as_pattern_list(user_input.get(CONF_HOSTS)),
                    CONF_INCLUDE: as_pattern_list(user_input.get(CONF_INCLUDE)),
                    CONF_EXCLUDE: as_pattern_list(user_input.get(CONF_EXCLUDE)),
                    CONF_STORE_RATES: bool(user_input[CONF_STORE_RATES]),
                    CONF_STALE_AFTER: int(user_input[CONF_STALE_AFTER]),
                }
                return self.async_create_entry(data=options)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TOPIC_PREFIX,
                        default=options.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                    ): TextSelector(TextSelectorConfig()),
                    vol.Optional(
                        CONF_HOSTS,
                        default="\n".join(as_pattern_list(options.get(CONF_HOSTS))),
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                    vol.Optional(
                        CONF_INCLUDE,
                        default="\n".join(as_pattern_list(options.get(CONF_INCLUDE))),
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                    vol.Optional(
                        CONF_EXCLUDE,
                        default="\n".join(as_pattern_list(options.get(CONF_EXCLUDE))),
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                    vol.Required(
                        CONF_STORE_RATES,
                        default=bool(
                            options.get(CONF_STORE_RATES, DEFAULT_STORE_RATES)
                        ),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_STALE_AFTER,
                        default=int(options.get(CONF_STALE_AFTER, DEFAULT_STALE_AFTER)),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10,
                            max=86400,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
            errors=errors,
        )
