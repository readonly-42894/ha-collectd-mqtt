"""Tests for unit and device class resolution."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor.const import DEVICE_CLASS_UNITS

from custom_components.collectd_mqtt.profiles import (
    PROFILES,
    STATE_MEASUREMENT,
    STATE_TOTAL_INCREASING,
    resolve_profile,
)
from custom_components.collectd_mqtt.types_db import (
    DSTYPE_COUNTER,
    DSTYPE_DERIVE,
    DSTYPE_GAUGE,
)


def test_gauge_bytes() -> None:
    """Gauges keep their unit and are sampled measurements."""
    resolved = resolve_profile("memory", DSTYPE_GAUGE, store_rates=True)
    assert resolved.unit == "B"
    assert resolved.device_class == "data_size"
    assert resolved.state_class == STATE_MEASUREMENT
    assert resolved.precision == 0


def test_rates_use_the_rate_unit() -> None:
    """Derive and counter values arrive as rates by default."""
    resolved = resolve_profile("if_octets", DSTYPE_DERIVE, store_rates=True)
    assert resolved.unit == "B/s"
    assert resolved.device_class == "data_rate"
    assert resolved.state_class == STATE_MEASUREMENT


def test_raw_counters_are_total_increasing() -> None:
    """With StoreRates disabled the value is a cumulative counter."""
    resolved = resolve_profile("if_octets", DSTYPE_COUNTER, store_rates=False)
    assert resolved.unit == "B"
    assert resolved.device_class == "data_size"
    assert resolved.state_class == STATE_TOTAL_INCREASING


def test_percent_and_temperature() -> None:
    """Common sensor families get their expected classifications."""
    assert resolve_profile("percent", DSTYPE_GAUGE, store_rates=True).unit == "%"
    temperature = resolve_profile("temperature", DSTYPE_GAUGE, store_rates=True)
    assert temperature.unit == "°C"
    assert temperature.device_class == "temperature"


def test_unknown_type_has_no_unit() -> None:
    """Unlisted types still report a number without a guessed unit."""
    resolved = resolve_profile("does_not_exist", None, store_rates=True)
    assert resolved.unit is None
    assert resolved.device_class is None
    assert resolved.state_class == STATE_MEASUREMENT
    assert resolved.precision is None


def test_profiles_use_units_home_assistant_accepts() -> None:
    """Every device class is paired with a unit Home Assistant validates."""
    for type_name, profile in PROFILES.items():
        for device_class, unit in (
            (profile.device_class, profile.unit),
            (profile.rate_device_class, profile.rate_unit),
        ):
            if device_class is None:
                continue
            allowed = {
                str(item)
                for item in DEVICE_CLASS_UNITS[SensorDeviceClass(device_class)]
            }
            assert unit in allowed, (
                f"{type_name}: {unit!r} not valid for {device_class}"
            )
