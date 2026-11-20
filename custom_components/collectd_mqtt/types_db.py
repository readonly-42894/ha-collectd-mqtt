"""Parser for collectd's bundled types.db.

collectd ships a plain-text catalogue that maps every metric type to its data
sources. The MQTT plugin's PLAIN payload only carries raw numbers, so this
catalogue is what turns them into named sensors and tells us whether a value is
a gauge or a counter/derive.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

TYPES_DB_PATH = Path(__file__).parent / "data" / "types.db"

DSTYPE_GAUGE = "GAUGE"
DSTYPE_COUNTER = "COUNTER"
DSTYPE_DERIVE = "DERIVE"
DSTYPE_ABSOLUTE = "ABSOLUTE"

DSTYPES = frozenset({DSTYPE_GAUGE, DSTYPE_COUNTER, DSTYPE_DERIVE, DSTYPE_ABSOLUTE})

# DS_TYPE_* values that accumulate over time instead of sampling a value.
CUMULATIVE_DSTYPES = frozenset({DSTYPE_COUNTER, DSTYPE_DERIVE, DSTYPE_ABSOLUTE})


@dataclass(frozen=True, slots=True)
class DataSource:
    """One data source of a collectd type."""

    name: str
    dstype: str


@dataclass(frozen=True, slots=True)
class TypeDefinition:
    """The data sources belonging to a collectd type."""

    sources: tuple[DataSource, ...]


def parse_types_db(text: str) -> dict[str, TypeDefinition]:
    """Parse the contents of a types.db file."""
    definitions: dict[str, TypeDefinition] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        type_name = fields[0]
        sources: list[DataSource] = []
        for spec in " ".join(fields[1:]).split(","):
            parts = spec.split(":")
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            dstype = parts[1].strip().upper()
            if not name:
                continue
            if dstype not in DSTYPES:
                raise ValueError(
                    f"types.db line {line_number}: unknown data source type "
                    f"{dstype!r} for {type_name!r}"
                )
            sources.append(DataSource(name=name, dstype=dstype))
        if sources:
            definitions[type_name] = TypeDefinition(sources=tuple(sources))
    return definitions


@cache
def load_types_db() -> dict[str, TypeDefinition]:
    """Load the bundled types.db once per process."""
    return parse_types_db(TYPES_DB_PATH.read_text(encoding="utf-8"))


def datasource_names(type_name: str) -> tuple[str, ...]:
    """Return the data source names for a collectd type, if known."""
    definition = load_types_db().get(type_name)
    if definition is None:
        return ()
    return tuple(source.name for source in definition.sources)


def datasource_dstype(type_name: str, index: int) -> str | None:
    """Return the data source type of the index-th value of a type."""
    definition = load_types_db().get(type_name)
    if definition is None or index >= len(definition.sources):
        return None
    return definition.sources[index].dstype
