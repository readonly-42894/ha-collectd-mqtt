"""Tests for the bundled collectd types.db."""

from __future__ import annotations

import pytest

from custom_components.collectd_mqtt.types_db import (
    DSTYPE_DERIVE,
    DSTYPE_GAUGE,
    DataSource,
    TypeDefinition,
    datasource_dstype,
    datasource_names,
    load_types_db,
    parse_types_db,
)


def test_parse_types_db_handles_comments_and_columns() -> None:
    """Comments, blank lines and aligned columns are ignored."""
    text = """
# a comment
cpu                     value:DERIVE:0:U
load                    shortterm:GAUGE:0:5000, midterm:GAUGE:0:5000,
                        longterm:GAUGE:0:5000
"""
    # Continuation lines are not valid types.db syntax, so the parser must not
    # turn them into a bogus type.
    definitions = parse_types_db(text)
    assert definitions["cpu"] == TypeDefinition((DataSource("value", DSTYPE_DERIVE),))

    text = "load shortterm:GAUGE:0:5000,midterm:GAUGE:0:5000,longterm:GAUGE:0:5000\n"
    definitions = parse_types_db(text)
    assert definitions["load"] == TypeDefinition(
        (
            DataSource("shortterm", DSTYPE_GAUGE),
            DataSource("midterm", DSTYPE_GAUGE),
            DataSource("longterm", DSTYPE_GAUGE),
        )
    )


def test_parse_types_db_rejects_unknown_dstype() -> None:
    """A data source type we cannot interpret is a real error."""
    with pytest.raises(ValueError, match="unknown data source type"):
        parse_types_db("broken value:WHATEVER:0:U\n")


def test_bundled_types_db_contains_common_metrics() -> None:
    """The shipped catalogue covers the common collectd plugins."""
    load_types_db()
    assert datasource_names("load") == ("shortterm", "midterm", "longterm")
    assert datasource_names("df") == ("used", "free")
    assert datasource_names("if_octets") == ("rx", "tx")
    assert datasource_names("cpu") == ("value",)
    assert datasource_dstype("cpu", 0) == DSTYPE_DERIVE
    assert datasource_dstype("if_octets", 1) == DSTYPE_DERIVE
    assert datasource_dstype("memory", 0) == DSTYPE_GAUGE


def test_unknown_type_has_no_sources() -> None:
    """Unknown types degrade to unnamed data sources."""
    assert datasource_names("does_not_exist") == ()
    assert datasource_dstype("does_not_exist", 0) is None
