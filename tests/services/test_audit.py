"""Issue #190 (D-08): the one JSON-safe conversion for ModificationsLog payloads."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from backend.services.audit import audit_jsonable, audit_values
from database.models.enums import ExperimentStatus, NoteType


@pytest.mark.parametrize("value", [None, True, 0, 7, 1.5, "text", ""])
def test_json_primitives_pass_through_unchanged(value):
    assert audit_jsonable(value) is value


def test_dates_and_datetimes_become_iso_strings():
    assert audit_jsonable(date(2026, 11, 13)) == "2026-11-13"
    assert audit_jsonable(datetime(2026, 11, 13, 9, 30, tzinfo=timezone.utc)) == "2026-11-13T09:30:00+00:00"


def test_a_pandas_timestamp_becomes_its_iso_string_not_its_nanoseconds():
    """pd.Timestamp has a `.value` attribute (integer nanoseconds). The upload
    parsers hand these to the scalar service, so the date check must win."""
    stamp = pd.Timestamp("2026-11-13 09:30:00")
    assert audit_jsonable(stamp) == "2026-11-13T09:30:00"


def test_an_enum_member_becomes_its_value():
    assert audit_jsonable(NoteType.modification) == "modification"
    assert json.dumps(audit_jsonable(ExperimentStatus.ONGOING)) == json.dumps(ExperimentStatus.ONGOING.value)


def test_anything_else_becomes_text():
    assert audit_jsonable(Decimal("1.50")) == "1.50"


def test_audit_values_converts_every_value_and_is_json_serializable():
    converted = audit_values({
        "measurement_date": datetime(2026, 11, 13, 9, 30),
        "event_date": date(2026, 11, 13),
        "note_type": NoteType.result_note,
        "final_ph": 7.1,
        "sample_tube_number": None,
    })
    assert converted == {
        "measurement_date": "2026-11-13T09:30:00",
        "event_date": "2026-11-13",
        "note_type": "result_note",
        "final_ph": 7.1,
        "sample_tube_number": None,
    }
    json.dumps(converted)
