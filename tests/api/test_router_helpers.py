"""Issue #190 (backend sweep PR 2): shared router helpers."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.api.routers._helpers import call_or_http


class _Base(Exception):
    pass


class _Missing(_Base):
    pass


def _raise(exc: Exception):
    raise exc


def test_call_or_http_returns_the_value():
    assert call_or_http(lambda: 7, ((_Base, 422),)) == 7


def test_call_or_http_maps_the_first_matching_type():
    """A subclass listed before its base wins; the base still maps the rest."""
    errors = ((_Missing, 404), (_Base, 422))
    with pytest.raises(HTTPException) as missing:
        call_or_http(lambda: _raise(_Missing("gone")), errors)
    assert (missing.value.status_code, missing.value.detail) == (404, "gone")
    with pytest.raises(HTTPException) as invalid:
        call_or_http(lambda: _raise(_Base("bad")), errors)
    assert (invalid.value.status_code, invalid.value.detail) == (422, "bad")


def test_call_or_http_lets_an_unlisted_exception_through():
    with pytest.raises(KeyError):
        call_or_http(lambda: _raise(KeyError("x")), ((_Base, 422),))


def test_call_or_http_uses_the_detail_builder():
    with pytest.raises(HTTPException) as exc:
        call_or_http(lambda: _raise(_Missing("HPHT_1")), ((_Missing, 404),),
                     detail=lambda e: f"No run {e}")
    assert exc.value.detail == "No run HPHT_1"
