from __future__ import annotations

from typing import Any, Callable
from sqlalchemy.orm import Session

_REGISTRY: dict[type, Callable] = {}


def register(model_class: type) -> Callable:
    """Decorator: register a recalculate function for a model class.

    Usage::

        @registry.register(ScalarResults)
        def recalculate_scalar(instance: ScalarResults, session: Session) -> None:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[model_class] = fn
        return fn
    return decorator


def recalculate(instance: Any, session: Session) -> None:
    """Call the registered recalculate function for this model instance.

    If no function is registered for the instance's type, this is a no-op.
    Called by M3 API write endpoints after every DB commit.
    """
    fn = _REGISTRY.get(type(instance))
    if fn is not None:
        fn(instance, session)
