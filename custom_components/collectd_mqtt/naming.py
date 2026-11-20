"""Build stable entity names and identifiers for collectd metrics."""

from __future__ import annotations

from .parser import MetricKey

PLUGIN_LABELS: dict[str, str] = {
    "cpu": "CPU",
    "df": "DF",
    "disk": "Disk",
    "interface": "Interface",
    "irq": "IRQ",
    "load": "Load",
    "memory": "Memory",
    "ps": "Processes",
    "swap": "Swap",
    "thermal": "Thermal",
    "uptime": "Uptime",
    "vmem": "Virtual Memory",
}

TYPE_LABELS: dict[str, str] = {
    "percent": "Percent",
    "percent_bytes": "Percent",
    "if_octets": "Octets",
    "if_packets": "Packets",
    "if_errors": "Errors",
    "if_dropped": "Dropped",
    "if_collisions": "Collisions",
    "if_multicast": "Multicast",
    "disk_ops": "Ops",
    "disk_time": "Time",
    "disk_merged": "Merged",
    "df_inodes": "Inodes",
    "ps_state": "State",
    "ps_count": "Count",
    "ps_cputime": "CPU Time",
}

# Types that repeat the plugin name or add nothing to the entity name.
#
# Only the primary type of a family may drop its label: the interface, disk
# and df families share the data source names rx/tx and read/write, so giving
# the label up for several types of the same family makes entity names depend
# on which message arrives first.
OMITTED_TYPES: dict[str, frozenset[str]] = {
    "cpu": frozenset({"cpu"}),
    "df": frozenset({"df_complex"}),
    "disk": frozenset({"disk_octets"}),
    "interface": frozenset({"if_octets"}),
    "load": frozenset({"load"}),
    "memory": frozenset({"memory"}),
    "swap": frozenset({"swap", "swap_io"}),
}

INSTANCE_LABELS: dict[str, str] = {
    "syst": "System",
}

DS_LABELS: dict[str, str] = {
    "rx": "RX",
    "tx": "TX",
    "read": "Read",
    "write": "Write",
    "shortterm": "Shortterm",
    "midterm": "Midterm",
    "longterm": "Longterm",
}


def _label(value: str) -> str:
    """Turn a collectd identifier into title-cased words."""
    return value.replace("_", " ").title()


def type_label(type_name: str) -> str:
    """Return the display label for a collectd type."""
    return TYPE_LABELS.get(type_name, _label(type_name))


def entity_name(key: MetricKey, dsname: str) -> str:
    """Build the entity name for one data source of a metric."""
    parts = [PLUGIN_LABELS.get(key.plugin, _label(key.plugin))]
    if key.plugin_instance:
        parts.append(key.plugin_instance)

    omitted = OMITTED_TYPES.get(key.plugin, frozenset())
    if key.type != key.plugin and key.type not in omitted:
        parts.append(type_label(key.type))

    if key.type_instance:
        parts.append(INSTANCE_LABELS.get(key.type_instance, _label(key.type_instance)))

    # A data source that only repeats the type or the type instance adds no
    # information, e.g. df_inodes publishes an "inodes" data source.
    if (
        dsname
        and dsname != "value"
        and dsname != key.type_instance
        and dsname != key.type
        and not key.type.endswith(f"_{dsname}")
    ):
        parts.append(DS_LABELS.get(dsname, _label(dsname)))

    return " ".join(parts)


def unique_id(key: MetricKey, dsname: str) -> str:
    """Build the stable unique ID for one data source of a metric."""
    return f"{key.unique_id}|{dsname}"
