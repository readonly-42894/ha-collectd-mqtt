"""Parse collectd MQTT topics and PLAIN payloads.

collectd's mqtt plugin publishes one value list per message. The topic is
``<prefix>/<host>/<plugin>-<plugin_instance>/<type>-<type_instance>`` (empty
instances omit the dash) and the payload is ``<time>:<value>[:<value>...]``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import NOTIFICATION_SEGMENT


@dataclass(frozen=True, slots=True)
class MetricKey:
    """Identity of one collectd metric, independent of the topic prefix."""

    host: str
    plugin: str
    plugin_instance: str
    type: str
    type_instance: str

    @property
    def unique_id(self) -> str:
        """Return the stable identity shared by all data sources."""
        return "|".join(
            (
                self.host,
                self.plugin,
                self.plugin_instance,
                self.type,
                self.type_instance,
            )
        )

    @property
    def canonical(self) -> str:
        """Return the instance-aware name used by include/exclude filters."""
        plugin = self.plugin
        if self.plugin_instance:
            plugin = f"{plugin}-{self.plugin_instance}"
        type_name = self.type
        if self.type_instance:
            type_name = f"{type_name}-{self.type_instance}"
        return f"{plugin}/{type_name}"


@dataclass(frozen=True, slots=True)
class ParsedPayload:
    """The numeric part of a collectd PLAIN payload."""

    timestamp: float
    values: tuple[float, ...]


def _split_instance(component: str) -> tuple[str, str]:
    """Split ``name-instance`` the same way collectd's parser does."""
    name, _, instance = component.partition("-")
    return name, instance


def parse_topic(topic: str, prefix: str) -> MetricKey | None:
    """Turn an MQTT topic into a metric key, or return None if it is not one."""
    prefix = prefix.strip("/")
    if not prefix or not topic.startswith(f"{prefix}/"):
        return None

    segments = topic[len(prefix) + 1 :].split("/")
    if len(segments) < 3 or not segments[0]:
        return None
    # "collectd/event/..." carries notifications, not metrics.
    if segments[0] == NOTIFICATION_SEGMENT:
        return None

    host = segments[0]
    plugin, plugin_instance = _split_instance(segments[1])
    type_name, type_instance = _split_instance("/".join(segments[2:]))
    if not plugin or not type_name:
        return None

    return MetricKey(
        host=host,
        plugin=plugin,
        plugin_instance=plugin_instance,
        type=type_name,
        type_instance=type_instance,
    )


def parse_payload(payload: bytes | str) -> ParsedPayload | None:
    """Parse a collectd PLAIN payload, or return None if it is not one."""
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace")
    else:
        text = payload
    text = text.strip()
    if not text:
        return None
    # Notifications are plain text and other producers may publish JSON; both
    # start with a non-numeric character and are rejected below. Bail out early
    # so a JSON array never gets mistaken for a value list.
    if text[0] in "[{":
        return None

    fields = text.split(":")
    if len(fields) < 2:
        return None

    timestamp = _parse_float(fields[0])
    if timestamp is None:
        return None

    values: list[float] = []
    for field in fields[1:]:
        value = _parse_float(field)
        if value is None:
            return None
        values.append(value)

    return ParsedPayload(timestamp=timestamp, values=tuple(values))


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
