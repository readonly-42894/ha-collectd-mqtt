"""Runtime data collection for collectd MQTT."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable
from datetime import timedelta
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

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
    NEW_ENTITY_FLUSH_DELAY,
    STALE_CHECK_INTERVAL,
)
from .entity import CollectdSensor
from .model import MetricSample
from .naming import entity_name, type_label, unique_id
from .parser import MetricKey, parse_payload, parse_topic
from .profiles import resolve_profile
from .types_db import load_types_db

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

EntityAdder = Callable[[list[CollectdSensor]], None]


def as_pattern_list(value: Any) -> list[str]:
    """Normalize an option value into a list of glob patterns."""
    if value is None:
        return []
    if isinstance(value, str):
        items: Iterable[str] = value.replace(",", "\n").splitlines()
    elif isinstance(value, Iterable):
        items = (str(item) for item in value)
    else:
        return []
    return [item.strip() for item in items if item.strip()]


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except TypeError, ValueError:
        return default
    return number if number > 0 else default


class CollectdCollector:
    """Own the MQTT subscription and the entity bookkeeping."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Read the options once; changing them reloads the config entry."""
        self.hass = hass
        self.entry = entry
        options = entry.options

        prefix = str(options.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX))
        self.prefix = prefix.strip("/") or DEFAULT_TOPIC_PREFIX
        self.hosts = as_pattern_list(options.get(CONF_HOSTS))
        self.include = as_pattern_list(options.get(CONF_INCLUDE)) or ["*"]
        self.exclude = as_pattern_list(options.get(CONF_EXCLUDE))
        self.store_rates = bool(options.get(CONF_STORE_RATES, DEFAULT_STORE_RATES))
        self.stale_after = _positive_int(
            options.get(CONF_STALE_AFTER), DEFAULT_STALE_AFTER
        )

        self._types = load_types_db()
        self._entities: dict[str, CollectdSensor] = {}
        self._pending: dict[str, MetricSample] = {}
        self._last_seen: dict[str, datetime] = {}
        self._names: dict[str, str] = {}
        self._name_owners: dict[tuple[str, str], str] = {}
        self._dropped: set[str] = set()
        self._warned: set[str] = set()
        self._connected = True
        self._add_entities: EntityAdder | None = None
        self._unsub_subscribe: Callable[[], None] | None = None
        self._unsub_connection: Callable[[], None] | None = None
        self._unsub_stale: Callable[[], None] | None = None
        self._cancel_flush: Callable[[], None] | None = None

    @property
    def entity_count(self) -> int:
        """Return the number of created entities."""
        return len(self._entities)

    async def async_start(self) -> None:
        """Subscribe to the configured topic tree and start the stale check."""
        self._unsub_connection = transport.async_subscribe_connection_status(
            self.hass, self._on_connection_status
        )
        self._unsub_stale = async_track_time_interval(
            self.hass,
            self._async_check_stale,
            timedelta(seconds=STALE_CHECK_INTERVAL),
        )
        self._unsub_subscribe = await transport.async_subscribe(
            self.hass, f"{self.prefix}/#", self._on_message
        )

    async def async_stop(self) -> None:
        """Release the subscription, timers and pending entity flush."""
        for unsubscribe in (
            self._unsub_subscribe,
            self._unsub_connection,
            self._unsub_stale,
        ):
            if unsubscribe is not None:
                unsubscribe()
        self._unsub_subscribe = None
        self._unsub_connection = None
        self._unsub_stale = None
        if self._cancel_flush is not None:
            self._cancel_flush()
            self._cancel_flush = None
        self._pending.clear()

    @callback
    def async_set_entity_adder(self, add_entities: EntityAdder) -> None:
        """Register the sensor platform's entity adder."""
        self._add_entities = add_entities
        if self._pending:
            self._schedule_flush()

    @callback
    def _on_message(self, message: Any) -> None:
        """Decode one MQTT message and route its values to entities."""
        key = parse_topic(message.topic, self.prefix)
        if key is None:
            return

        if not self._is_allowed(key):
            self._drop_metric(key)
            return

        parsed = parse_payload(message.payload)
        if parsed is None:
            self._warn_once(
                f"payload:{message.topic}",
                "Ignoring a non-plain payload on topic %s",
                message.topic,
            )
            return

        now = dt_util.utcnow()
        for index, value in enumerate(parsed.values):
            if not math.isfinite(value):
                continue
            dsname, dstype = self._datasource(key, index)
            uid = unique_id(key, dsname)
            self._last_seen[uid] = now
            sample = MetricSample(
                key=key,
                dsname=dsname,
                index=index,
                value=value,
                timestamp=parsed.timestamp,
                profile=resolve_profile(key.type, dstype, store_rates=self.store_rates),
                name=self._name_for(key, dsname, uid),
                unique_id=uid,
            )

            entity = self._entities.get(uid)
            if entity is not None:
                entity.update_sample(sample)
                continue
            if uid not in self._pending:
                self._pending[uid] = sample
                self._schedule_flush()

    def _is_allowed(self, key: MetricKey) -> bool:
        """Apply the host, include and exclude filters."""
        if self.hosts and not any(
            fnmatchcase(key.host, pattern) for pattern in self.hosts
        ):
            return False
        canonical = key.canonical
        if not any(fnmatchcase(canonical, pattern) for pattern in self.include):
            return False
        return not any(fnmatchcase(canonical, pattern) for pattern in self.exclude)

    def _datasource(self, key: MetricKey, index: int) -> tuple[str, str | None]:
        """Return the data source name and type for one value position."""
        definition = self._types.get(key.type)
        if definition is not None and index < len(definition.sources):
            source = definition.sources[index]
            return source.name, source.dstype
        return ("value" if index == 0 else f"value_{index}"), None

    def _name_for(self, key: MetricKey, dsname: str, uid: str) -> str:
        """Return the entity name, disambiguating rare cross-type collisions."""
        cached = self._names.get(uid)
        if cached is not None:
            return cached

        name = entity_name(key, dsname)
        owner = self._name_owners.get((key.host, name))
        if owner is not None and owner != uid:
            name = f"{name} {type_label(key.type)}"

        self._name_owners[(key.host, name)] = uid
        self._names[uid] = name
        return name

    @callback
    def _schedule_flush(self) -> None:
        """Batch new entities so the first burst is not added one by one."""
        if self._cancel_flush is not None or self._add_entities is None:
            return
        self._cancel_flush = async_track_point_in_utc_time(
            self.hass,
            self._flush_pending,
            dt_util.utcnow() + timedelta(seconds=NEW_ENTITY_FLUSH_DELAY),
        )

    @callback
    def _flush_pending(self, _now: datetime | None = None) -> None:
        """Create and add the entities collected since the last flush."""
        self._cancel_flush = None
        if not self._pending or self._add_entities is None:
            return

        samples = list(self._pending.values())
        self._pending.clear()
        entities = [CollectdSensor(sample.key.host, sample) for sample in samples]
        for entity in entities:
            self._entities[entity.unique_id] = entity
        self._add_entities(entities)

    @callback
    def _drop_metric(self, key: MetricKey) -> None:
        """Remove entities of a metric that a filter now excludes."""
        prefix = f"{key.unique_id}|"
        if key.unique_id in self._dropped:
            return
        self._dropped.add(key.unique_id)
        _LOGGER.debug("Removing entities of excluded metric %s", key.canonical)

        for uid in [uid for uid in self._entities if uid.startswith(prefix)]:
            entity = self._entities.pop(uid)
            self._last_seen.pop(uid, None)
            self._names.pop(uid, None)
            for owner, owner_uid in list(self._name_owners.items()):
                if owner_uid == uid:
                    self._name_owners.pop(owner)
            self.hass.async_create_task(entity.async_remove(force_remove=True))

        for uid in [uid for uid in self._pending if uid.startswith(prefix)]:
            self._pending.pop(uid, None)

        registry = er.async_get(self.hass)
        for entry in er.async_entries_for_config_entry(registry, self.entry.entry_id):
            if entry.unique_id.startswith(prefix):
                registry.async_remove(entry.entity_id)

    @callback
    def _on_connection_status(self, connected: bool) -> None:
        """Mark everything unavailable while the broker connection is down."""
        self._connected = connected
        if connected:
            return
        for entity in self._entities.values():
            entity.mark_unavailable()

    @callback
    def _async_check_stale(self, _now: datetime) -> None:
        """Mark entities unavailable when their metric stopped publishing."""
        if not self._connected:
            return
        cutoff = _now - timedelta(seconds=self.stale_after)
        for uid, entity in self._entities.items():
            last_seen = self._last_seen.get(uid)
            if last_seen is not None and last_seen < cutoff:
                entity.mark_unavailable()

    def _warn_once(self, key: str, message: str, *args: Any) -> None:
        """Log a repeated problem only once per topic or pattern."""
        if key in self._warned:
            return
        self._warned.add(key)
        _LOGGER.warning(message, *args)
