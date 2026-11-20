"""Tests for the entity naming rules."""

from __future__ import annotations

import pytest

from custom_components.collectd_mqtt.naming import entity_name, unique_id
from custom_components.collectd_mqtt.parser import MetricKey


@pytest.mark.parametrize(
    ("key", "dsname", "expected"),
    [
        (MetricKey("router", "cpu", "0", "cpu", "user"), "value", "CPU 0 User"),
        (MetricKey("router", "load", "", "load", ""), "shortterm", "Load Shortterm"),
        (MetricKey("router", "load", "", "load", ""), "midterm", "Load Midterm"),
        (MetricKey("router", "memory", "", "memory", "used"), "value", "Memory Used"),
        (
            MetricKey("router", "df", "root", "df_complex", "used"),
            "value",
            "DF root Used",
        ),
        (
            MetricKey("router", "interface", "eth0", "if_octets", ""),
            "rx",
            "Interface eth0 RX",
        ),
        (
            MetricKey("router", "interface", "eth0", "if_octets", ""),
            "tx",
            "Interface eth0 TX",
        ),
        (
            MetricKey("router", "disk", "sda", "disk_ops", ""),
            "read",
            "Disk sda Read",
        ),
        (
            MetricKey("router", "thermal", "0", "temperature", ""),
            "value",
            "Thermal 0 Temperature",
        ),
        (MetricKey("router", "uptime", "", "uptime", ""), "value", "Uptime"),
        (
            MetricKey("router", "ps", "", "ps_state", "running"),
            "value",
            "Processes State Running",
        ),
    ],
)
def test_entity_name(key: MetricKey, dsname: str, expected: str) -> None:
    """Instance and data source names compose readable entity names."""
    assert entity_name(key, dsname) == expected


def test_data_source_name_is_not_repeated() -> None:
    """A data source that equals the type instance is not appended twice."""
    key = MetricKey("router", "df", "root", "df_complex", "used")
    assert entity_name(key, "used") == "DF root Used"


def test_unique_id_is_stable_and_prefix_free() -> None:
    """Unique IDs contain the metric identity and the data source only."""
    key = MetricKey("router", "interface", "eth0", "if_octets", "")
    assert unique_id(key, "rx") == "router|interface|eth0|if_octets||rx"
    assert unique_id(key, "tx") == "router|interface|eth0|if_octets||tx"
    assert "collectd" not in unique_id(key, "rx")
