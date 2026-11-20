"""Constants for the collectd MQTT integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "collectd_mqtt"
NAME = "collectd MQTT"

PLATFORMS: list[Platform] = [Platform.SENSOR]

# collectd's mqtt plugin uses "collectd" as the default Topic Prefix.
CONF_TOPIC_PREFIX = "topic_prefix"
DEFAULT_TOPIC_PREFIX = "collectd"

CONF_HOSTS = "hosts"
CONF_INCLUDE = "include"
CONF_EXCLUDE = "exclude"
CONF_STORE_RATES = "store_rates"
CONF_STALE_AFTER = "stale_after"

# collectd's StoreRates option defaults to true, so counter and derive values
# arrive as per-second rates unless the publisher disables it.
DEFAULT_STORE_RATES = True
# The publisher interval is not part of the PLAIN payload, so staleness is a
# fixed wall-clock timeout in seconds.
DEFAULT_STALE_AFTER = 180

STALE_CHECK_INTERVAL = 30
NEW_ENTITY_FLUSH_DELAY = 0.5

# collectd's mqtt plugin publishes notifications below "<NotificationPrefix>",
# which defaults to "collectd/event".
NOTIFICATION_SEGMENT = "event"
