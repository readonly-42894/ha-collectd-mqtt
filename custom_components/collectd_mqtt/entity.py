"""Sensor entity representing one collectd data source."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .model import MetricSample
from .profiles import render_value


class CollectdSensor(SensorEntity):
    """A single numeric value published by collectd."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, host: str, sample: MetricSample) -> None:
        """Create a sensor from its first observed sample."""
        self._key = sample.key
        self._dsname = sample.dsname
        self._attr_unique_id = sample.unique_id
        self._attr_name = sample.name
        self._attr_native_value = self._render(sample)
        self._attr_native_unit_of_measurement = sample.profile.unit
        self._attr_device_class = (
            SensorDeviceClass(sample.profile.device_class)
            if sample.profile.device_class
            else None
        )
        self._attr_state_class = (
            SensorStateClass(sample.profile.state_class)
            if sample.profile.state_class
            else None
        )
        self._attr_suggested_display_precision = sample.profile.precision
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=host,
            manufacturer="collectd",
            model="collectd metrics",
            entry_type=DeviceEntryType.SERVICE,
        )

    @staticmethod
    def _render(sample: MetricSample) -> float | datetime | None:
        """Return the value a sensor reports, converting uptime to a timestamp."""
        return render_value(
            sample.profile, sample.value, sample.timestamp, now=dt_util.utcnow()
        )

    @property
    def collectd_key(self) -> str:
        """Return the metric identity, used for diagnostics."""
        return self._key.unique_id

    @property
    def dsname(self) -> str:
        """Return the collectd data source name."""
        return self._dsname

    def update_sample(self, sample: MetricSample) -> None:
        """Apply a newer value and write it to the state machine."""
        self._attr_native_value = self._render(sample)
        self._attr_available = True
        self._write_state()

    def mark_unavailable(self) -> None:
        """Mark the sensor unavailable without discarding its value."""
        if not self._attr_available:
            return
        self._attr_available = False
        self._write_state()

    def _write_state(self) -> None:
        """Write state once Home Assistant has registered the entity."""
        if self.entity_id is None:
            return
        self.async_write_ha_state()
