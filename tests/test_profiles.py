"""Tests for unit and device class resolution."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor.const import (
    DEVICE_CLASS_UNITS,
    NON_NUMERIC_DEVICE_CLASSES,
)

from custom_components.collectd_mqtt.profiles import (
    PROFILES,
    STATE_MEASUREMENT,
    STATE_TOTAL_INCREASING,
    VALUE_UPTIME,
    render_value,
    resolve_profile,
)
from custom_components.collectd_mqtt.types_db import (
    DSTYPE_COUNTER,
    DSTYPE_DERIVE,
    DSTYPE_GAUGE,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
COLLECTD_TIMESTAMP = 1763600000.123


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


def test_uptime_is_a_startup_timestamp() -> None:
    """collectd uptime becomes the point in time the host last started."""
    resolved = resolve_profile("uptime", DSTYPE_GAUGE, store_rates=True)
    assert resolved.unit is None
    assert resolved.device_class == "uptime"
    assert resolved.state_class is None
    assert resolved.precision is None
    assert resolved.value_kind == VALUE_UPTIME


def test_render_value_leaves_numbers_untouched() -> None:
    """Identical profiles keep the raw collectd value."""
    resolved = resolve_profile("memory", DSTYPE_GAUGE, store_rates=True)
    assert render_value(resolved, 12.5, COLLECTD_TIMESTAMP, now=NOW) == 12.5


def test_render_value_uses_the_sample_timestamp() -> None:
    """Uptime is subtracted from the collectd timestamp, not the receive time."""
    resolved = resolve_profile("uptime", DSTYPE_GAUGE, store_rates=True)
    rendered = render_value(resolved, 123456, COLLECTD_TIMESTAMP, now=NOW)
    assert rendered == datetime.fromtimestamp(COLLECTD_TIMESTAMP - 123456, tz=UTC)


def test_render_value_falls_back_to_now() -> None:
    """A missing sample timestamp uses the current time as reference."""
    resolved = resolve_profile("uptime", DSTYPE_GAUGE, store_rates=True)
    rendered = render_value(resolved, 3600, 0, now=NOW)
    assert rendered == datetime(2026, 11, 20, 11, 0, tzinfo=UTC)


def test_render_value_rejects_unrepresentable_timestamps() -> None:
    """Values outside the datetime range do not raise."""
    resolved = resolve_profile("uptime", DSTYPE_GAUGE, store_rates=True)
    assert render_value(resolved, 0, 1e308, now=NOW) is None


def test_profiles_use_units_home_assistant_accepts() -> None:
    """Every device class is paired with a unit Home Assistant validates."""
    for type_name, profile in PROFILES.items():
        for device_class, unit in (
            (profile.device_class, profile.unit),
            (profile.rate_device_class, profile.rate_unit),
        ):
            if device_class is None:
                continue
            sensor_device_class = SensorDeviceClass(device_class)
            if sensor_device_class in NON_NUMERIC_DEVICE_CLASSES:
                assert unit is None, (
                    f"{type_name}: {device_class} must not carry a unit"
                )
                continue
            allowed = {str(item) for item in DEVICE_CLASS_UNITS[sensor_device_class]}
            assert unit in allowed, (
                f"{type_name}: {unit!r} not valid for {device_class}"
            )
