import types
import pytest
from backend.services.calculations import registry


class FakeModel:
    pass


class OtherModel:
    pass


def test_register_and_dispatch():
    """Registered function is called with instance and session."""
    called_with = {}

    @registry.register(FakeModel)
    def recalc(instance, session):
        called_with['instance'] = instance
        called_with['session'] = session

    instance = FakeModel()
    session = types.SimpleNamespace()
    registry.recalculate(instance, session)

    assert called_with['instance'] is instance
    assert called_with['session'] is session

    # Cleanup: remove registration so other tests are not affected
    registry._REGISTRY.pop(FakeModel, None)


def test_unregistered_model_is_noop():
    """recalculate silently does nothing for unregistered model types."""
    instance = OtherModel()
    session = types.SimpleNamespace()
    # Should not raise
    registry.recalculate(instance, session)


def test_register_overwrites_previous():
    """Re-registering a model class replaces the previous function."""
    results = []

    @registry.register(FakeModel)
    def first(instance, session):
        results.append('first')

    @registry.register(FakeModel)
    def second(instance, session):
        results.append('second')

    registry.recalculate(FakeModel(), types.SimpleNamespace())
    assert results == ['second']

    registry._REGISTRY.pop(FakeModel, None)
