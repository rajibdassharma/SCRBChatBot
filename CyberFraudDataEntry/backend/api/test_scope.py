"""Keep test fixtures out of dashboard figures.

`TestDistrict` / `Test PS` exist so an administrator can verify the app
end to end without touching a real police station's data (see
add_test_users.py). They are genuine rows and must keep working for
login, data entry and their own reports — but they should never appear
in a dashboard, where they inflate totals, occupy a ranking row and
shade a district on the map.

WHY A SUBQUERY AND NOT AN ID LOOKUP
-----------------------------------
Resolving the ids first would mean an extra await in every one of ~39
endpoints, and an id cached at import time goes stale the moment the
fixture is re-seeded. Expressed as a correlated subquery this is a pure
SQLAlchemy expression: no async, no cache, no staleness, and each call
site becomes a single `.where(...)`. `police_stations` and `units` are
tiny, so the cost is nil.

CONFIGURABLE
------------
Set CFDSR_TEST_UNITS / CFDSR_TEST_STATIONS (comma-separated) to change
the list per environment, or to empty to disable the exclusion
entirely — useful on a dev box where the fixture IS the only data and
hiding it would leave every dashboard blank.
"""
from __future__ import annotations

import os

from sqlalchemy import select

from models.police_station import PoliceStation
from models.unit import Unit


def _names(env_key: str, default: str) -> list[str]:
    raw = os.getenv(env_key)
    if raw is None:
        raw = default
    return [n.strip() for n in raw.split(",") if n.strip()]


#: District(s) whose rows never appear in a dashboard.
TEST_UNIT_NAMES: list[str] = _names("CFDSR_TEST_UNITS", "TestDistrict")
#: Station(s) whose rows never appear in a dashboard.
TEST_STATION_NAMES: list[str] = _names("CFDSR_TEST_STATIONS", "Test PS")


def test_ps_ids_subq():
    """SELECT of police_station ids belonging to the test fixture."""
    return select(PoliceStation.id).where(
        PoliceStation.station_name.in_(TEST_STATION_NAMES)
    )


def test_unit_ids_subq():
    """SELECT of unit ids belonging to the test fixture."""
    return select(Unit.id).where(Unit.name.in_(TEST_UNIT_NAMES))


def exclude_test_ps(ps_id_col):
    """Predicate excluding the test station, by ps_id column.

    Use on any fact table carrying ps_id — cases, all_accounts,
    daily_work_entries, portals_dsr_entries:

        q = q.where(exclude_test_ps(Case.ps_id))

    Returns None when the exclusion is switched off, so callers should
    guard with `where_not_test(...)` below rather than passing None to
    .where().
    """
    if not TEST_STATION_NAMES:
        return None
    return ps_id_col.notin_(test_ps_ids_subq())


def exclude_test_unit(unit_id_col):
    """Predicate excluding the test district, by unit_id column."""
    if not TEST_UNIT_NAMES:
        return None
    return unit_id_col.notin_(test_unit_ids_subq())


def exclude_test_station_row():
    """Predicate for queries that enumerate police_stations directly.

    Different from exclude_test_ps: those filter a fact table by its
    ps_id, this filters the station list itself — the queries that
    LEFT JOIN from police_stations so silent stations still appear.
    Without this the test station shows as a permanent zero row.
    """
    if not TEST_STATION_NAMES:
        return None
    return PoliceStation.station_name.notin_(TEST_STATION_NAMES)


def exclude_test_unit_row():
    """Predicate for queries that enumerate units directly."""
    if not TEST_UNIT_NAMES:
        return None
    return Unit.name.notin_(TEST_UNIT_NAMES)


def where_not_test(q, *predicates):
    """Apply each predicate that is not None.

    Lets a call site stay a one-liner regardless of whether the
    exclusion is configured on or off:

        q = where_not_test(q, exclude_test_ps(Case.ps_id))
    """
    for pred in predicates:
        if pred is not None:
            q = q.where(pred)
    return q
