import types
import pytest
from backend.services.calculations import registry


class FakeModel:
    pass


class OtherModel:
    pass


@pytest.fixture
def clean_fake_model():
    """Ensure FakeModel is removed from registry after each test that uses it."""
    yield
    registry._REGISTRY.pop(FakeModel, None)


def test_register_and_dispatch(clean_fake_model):
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


def test_unregistered_model_is_noop():
    """recalculate silently does nothing for unregistered model types."""
    instance = OtherModel()
    session = types.SimpleNamespace()
    # Should not raise
    registry.recalculate(instance, session)


def test_register_overwrites_previous(clean_fake_model):
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
