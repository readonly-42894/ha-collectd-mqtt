"""Tests for topic and payload parsing."""

from __future__ import annotations

import math

import pytest

from custom_components.collectd_mqtt.parser import (
    MetricKey,
    parse_payload,
    parse_topic,
)


@pytest.mark.parametrize(
    ("prefix", "topic", "expected"),
    [
        (
            "collectd",
            "collectd/router/cpu-0/cpu-user",
            MetricKey("router", "cpu", "0", "cpu", "user"),
        ),
        (
            "collectd",
            "collectd/router/load/load",
            MetricKey("router", "load", "", "load", ""),
        ),
        (
            "collectd",
            "collectd/router/interface-eth0/if_octets",
            MetricKey("router", "interface", "eth0", "if_octets", ""),
        ),
        (
            "collectd",
            "collectd/router/df-root/df_complex-used",
            MetricKey("router", "df", "root", "df_complex", "used"),
        ),
        (
            "collectd",
            "collectd/router/cpu-cpu-total/cpu-idle",
            MetricKey("router", "cpu", "cpu-total", "cpu", "idle"),
        ),
        (
            "site/router",
            "site/router/router/memory/memory-used",
            MetricKey("router", "memory", "", "memory", "used"),
        ),
    ],
)
def test_parse_topic(prefix: str, topic: str, expected: MetricKey) -> None:
    """Topics map onto host, plugin and type components."""
    assert parse_topic(topic, prefix) == expected


@pytest.mark.parametrize(
    "topic",
    [
        "collectd/event/router/cpu-0/cpu-user",
        "collectd/router/cpu-0",
        "collectd//cpu-0/cpu-user",
        "other/router/cpu-0/cpu-user",
        "collectd",
        "",
    ],
)
def test_parse_topic_rejects_non_metrics(topic: str) -> None:
    """Notification topics and malformed topics are ignored."""
    assert parse_topic(topic, "collectd") is None


@pytest.mark.parametrize(
    ("payload", "timestamp", "values"),
    [
        ("1763600000.123:0.45", 1763600000.123, (0.45,)),
        ("1763600000.123:1.2:3.4:5.6", 1763600000.123, (1.2, 3.4, 5.6)),
        (" 1763600000.123:-1e-3\n", 1763600000.123, (-0.001,)),
        ("1763600000.123:nan", 1763600000.123, (math.nan,)),
    ],
)
def test_parse_payload(
    payload: str, timestamp: float, values: tuple[float, ...]
) -> None:
    """PLAIN payloads carry a timestamp followed by one or more values."""
    parsed = parse_payload(payload)
    assert parsed is not None
    assert parsed.timestamp == pytest.approx(timestamp)
    assert len(parsed.values) == len(values)
    for actual, expected in zip(parsed.values, values, strict=True):
        if math.isnan(expected):
            assert math.isnan(actual)
        else:
            assert actual == pytest.approx(expected)


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "   ",
        "1763600000.123",
        "1763600000.123:",
        "1763600000.123:1.0:oops",
        "Time: 1763600000.123\r\nSeverity: FAILURE\r\nMessage: disk full",
        '[{"values":[1.0],"time":1763600000.123}]',
        '{"values":[1.0]}',
    ],
)
def test_parse_payload_rejects_other_messages(payload: str) -> None:
    """Notifications, JSON and truncated payloads are not values."""
    assert parse_payload(payload) is None


def test_parse_payload_accepts_bytes() -> None:
    """The MQTT client hands us bytes when no encoding is configured."""
    parsed = parse_payload(b"1763600000.123:42.0")
    assert parsed is not None
    assert parsed.values == (42.0,)


def test_metric_key_canonical_and_unique_id() -> None:
    """Filters use the instance-aware form, entities use a stable identity."""
    key = MetricKey("router", "interface", "eth0", "if_octets", "")
    assert key.canonical == "interface-eth0/if_octets"
    assert key.unique_id == "router|interface|eth0|if_octets|"

    key = MetricKey("router", "load", "", "load", "")
    assert key.canonical == "load/load"
    assert key.unique_id == "router|load||load|"
