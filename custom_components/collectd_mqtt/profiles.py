"""Map collectd types to Home Assistant sensor metadata.

collectd's types.db does not carry units, so this module holds a curated table
for the metric families that have an unambiguous Home Assistant counterpart.
Anything not listed keeps its numeric value without a unit, which is the safest
default: Home Assistant validates device classes against their unit sets.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types_db import CUMULATIVE_DSTYPES

STATE_MEASUREMENT = "measurement"
STATE_TOTAL_INCREASING = "total_increasing"


@dataclass(frozen=True, slots=True)
class MetricProfile:
    """Unit and classification hints for one collectd type."""

    unit: str | None = None
    device_class: str | None = None
    rate_unit: str | None = None
    rate_device_class: str | None = None
    precision: int | None = None


@dataclass(frozen=True, slots=True)
class ResolvedProfile:
    """Everything a sensor entity needs to render one value."""

    unit: str | None
    device_class: str | None
    state_class: str
    precision: int | None


def _profile(
    unit: str | None = None,
    device_class: str | None = None,
    *,
    rate_unit: str | None = None,
    rate_device_class: str | None = None,
    precision: int | None = None,
) -> MetricProfile:
    return MetricProfile(
        unit=unit,
        device_class=device_class,
        rate_unit=rate_unit,
        rate_device_class=rate_device_class,
        precision=precision,
    )


_BYTES = _profile("B", "data_size", precision=0)
_BYTE_RATES = _profile(
    "B",
    "data_size",
    rate_unit="B/s",
    rate_device_class="data_rate",
    precision=0,
)
_PERCENTS = _profile("%", precision=1)
_COUNTS = _profile(precision=0)
_COUNT_RATES = _profile(precision=2)
_DURATIONS = _profile("s", "duration", precision=3)
_TEMPERATURES = _profile("°C", "temperature", precision=1)
_VOLTAGES = _profile("V", "voltage", precision=3)
_CURRENTS = _profile("A", "current", precision=3)
_POWERS = _profile("W", "power", precision=2)
_ENERGIES = _profile("Wh", "energy", precision=3)
_FREQUENCIES = _profile("Hz", "frequency", precision=0)
_HUMIDITIES = _profile("%", "humidity", precision=1)

PROFILES: dict[str, MetricProfile] = {
    # Bytes and byte rates.
    **dict.fromkeys(
        (
            "bytes",
            "bucket",
            "buffer",
            "cache_size",
            "capacity",
            "df",
            "df_complex",
            "disk_capacity",
            "disk_physical",
            "file_size",
            "media",
            "memory",
            "memory_lua",
            "mysql_bpool_bytes",
            "pg_db_size",
            "ps_code",
            "ps_data",
            "ps_rss",
            "ps_stacksize",
            "ps_vm",
            "swap",
            "vs_memory",
        ),
        _BYTES,
    ),
    **dict.fromkeys(
        (
            "apache_bytes",
            "disk_octets",
            "dns_octets",
            "if_octets",
            "if_rx_octets",
            "if_tx_octets",
            "io_octets",
            "ipt_bytes",
            "memcached_octets",
            "mysql_octets",
            "node_octets",
            "ps_disk_octets",
            "serial_octets",
            "swap_io",
            "total_bytes",
            "vf_bytes",
        ),
        _BYTE_RATES,
    ),
    # Percentages.
    **dict.fromkeys(
        ("cache_ratio", "percent", "percent_bytes", "percent_inodes"),
        _PERCENTS,
    ),
    # Gauges that count things.
    **dict.fromkeys(
        (
            "blocked_clients",
            "conntrack",
            "current_connections",
            "current_sessions",
            "file_handles",
            "files",
            "links",
            "md_disks",
            "objects",
            "pending_operations",
            "players",
            "pools",
            "questions",
            "queue_length",
            "records",
            "routes",
            "satellites",
            "tcp_connections",
            "threads",
            "users",
        ),
        _COUNTS,
    ),
    # Rates that count events per second.
    **dict.fromkeys(
        (
            "apache_requests",
            "contextswitch",
            "disk_merged",
            "disk_ops",
            "disk_ops_complex",
            "dns_answer",
            "dns_notify",
            "dns_qtype",
            "dns_query",
            "dns_question",
            "dns_update",
            "dns_zops",
            "fork_rate",
            "if_collisions",
            "if_dropped",
            "if_errors",
            "if_multicast",
            "if_packets",
            "io_ops",
            "io_packets",
            "irq",
            "nginx_requests",
            "operations",
            "requests",
            "total_requests",
        ),
        _COUNT_RATES,
    ),
    # Durations.
    **dict.fromkeys(
        (("duration", "latency", "ping", "response_time", "timeleft")),
        _DURATIONS,
    ),
    "uptime": _profile("s", "duration", precision=0),
    # Sensor readings.
    **dict.fromkeys(
        ("nvme_temp_sensor", "nvme_temperature", "smart_temperature", "temperature"),
        _TEMPERATURES,
    ),
    "fanspeed": _profile("rpm", precision=0),
    **dict.fromkeys(("voltage", "voltage_threshold"), _VOLTAGES),
    "current": _CURRENTS,
    **dict.fromkeys(("power", "tdp"), _POWERS),
    "energy_wh": _ENERGIES,
    **dict.fromkeys(("cpufreq", "frequency"), _FREQUENCIES),
    "humidity": _HUMIDITIES,
    # Load averages are unitless.
    "load": _profile(precision=2),
}


def resolve_profile(
    type_name: str, dstype: str | None, *, store_rates: bool
) -> ResolvedProfile:
    """Resolve the entity metadata for a value of the given type."""
    profile = PROFILES.get(type_name)
    cumulative = dstype is not None and dstype in CUMULATIVE_DSTYPES

    if cumulative and not store_rates:
        return ResolvedProfile(
            unit=profile.unit if profile else None,
            device_class=profile.device_class if profile else None,
            state_class=STATE_TOTAL_INCREASING,
            precision=profile.precision if profile else None,
        )

    if cumulative:
        return ResolvedProfile(
            unit=profile.rate_unit if profile else None,
            device_class=profile.rate_device_class if profile else None,
            state_class=STATE_MEASUREMENT,
            precision=profile.precision if profile else None,
        )

    return ResolvedProfile(
        unit=profile.unit if profile else None,
        device_class=profile.device_class if profile else None,
        state_class=STATE_MEASUREMENT,
        precision=profile.precision if profile else None,
    )
