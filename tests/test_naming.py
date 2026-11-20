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
            MetricKey("router", "interface", "eth0", "if_packets", ""),
            "rx",
            "Interface eth0 Packets RX",
        ),
        (
            MetricKey("router", "interface", "eth0", "if_errors", ""),
            "tx",
            "Interface eth0 Errors TX",
        ),
        (
            MetricKey("router", "interface", "eth0", "if_dropped", ""),
            "rx",
            "Interface eth0 Dropped RX",
        ),
        (
            MetricKey("router", "disk", "sda", "disk_octets", ""),
            "read",
            "Disk sda Read",
        ),
        (
            MetricKey("router", "disk", "sda", "disk_ops", ""),
            "read",
            "Disk sda Ops Read",
        ),
        (
            MetricKey("router", "disk", "sda", "disk_time", ""),
            "write",
            "Disk sda Time Write",
        ),
        (
            MetricKey("router", "df", "root", "df_inodes", "used"),
            "value",
            "DF root Inodes Used",
        ),
        (
            MetricKey("router", "df", "root", "df_inodes", ""),
            "inodes",
            "DF root Inodes",
        ),
        (
            MetricKey("router", "df", "root", "percent_bytes", "used"),
            "value",
            "DF root Percent Used",
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


def test_family_types_keep_distinct_names() -> None:
    """Types of one family that share data source names stay distinguishable."""
    keys = [
        MetricKey("router", "interface", "eth0", type_name, "")
        for type_name in ("if_octets", "if_packets", "if_errors", "if_dropped")
    ]
    assert len({entity_name(key, "rx") for key in keys}) == len(keys)


def test_unique_id_is_stable_and_prefix_free() -> None:
    """Unique IDs contain the metric identity and the data source only."""
    key = MetricKey("router", "interface", "eth0", "if_octets", "")
    assert unique_id(key, "rx") == "router|interface|eth0|if_octets||rx"
    assert unique_id(key, "tx") == "router|interface|eth0|if_octets||tx"
    assert "collectd" not in unique_id(key, "rx")
