import pytest

from app.application.registry import BotRegistry
from app.domain.contracts import BotDescriptor, BotResult, RunStatus


class Example:
    descriptor = BotDescriptor("example", "Example", "Test bot")

    def run(self, ctx):
        return BotResult(RunStatus.SUCCEEDED, evidence="observed_text")


def test_registration_and_new_instances():
    registry = BotRegistry()
    registry.register(Example)
    assert [bot.bot_id for bot in registry.list()] == ["example"]
    assert registry.get("example") is not registry.get("example")
    assert registry.get("example").run(None).status == RunStatus.SUCCEEDED


def test_duplicate_ids_and_unknown_bots():
    registry = BotRegistry()
    registry.register(Example)
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(Example)
    with pytest.raises(KeyError, match="Unknown bot"):
        registry.get("not-registered")
