"""Small helpers shared by the API routers (issue #190).

Kept free of router imports so any router can import it without a cycle.
"""
from __future__ import annotations

from typing import Callable, Sequence, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def call_or_http(
    fn: Callable[[], T],
    errors: Sequence[tuple[type[Exception], int]],
    detail: Callable[[Exception], str] = str,
) -> T:
    """Run ``fn`` and turn a service exception into an HTTPException.

    ``errors`` pairs an exception type with an HTTP status. Pairs are tried in
    order, so list a subclass before its base class. An exception that matches
    no pair propagates unchanged. ``detail`` builds the response detail.
    """
    try:
        return fn()
    except tuple(exc_type for exc_type, _ in errors) as exc:
        for exc_type, status_code in errors:
            if isinstance(exc, exc_type):
                raise HTTPException(status_code=status_code, detail=detail(exc))
        raise
