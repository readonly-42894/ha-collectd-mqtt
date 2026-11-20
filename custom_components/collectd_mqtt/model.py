"""Value objects shared by the runtime and the entity layer."""

from __future__ import annotations

from dataclasses import dataclass

from .parser import MetricKey
from .profiles import ResolvedProfile


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One data source value decoded from an MQTT message."""

    key: MetricKey
    dsname: str
    index: int
    value: float
    timestamp: float
    profile: ResolvedProfile
    name: str
    unique_id: str
