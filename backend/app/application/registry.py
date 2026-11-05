from collections.abc import Callable

from app.domain.contracts import Bot, BotDescriptor


class BotRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Bot]] = {}
        self._descriptors: dict[str, BotDescriptor] = {}

    def register(self, factory: Callable[[], Bot]) -> None:
        instance = factory()
        name = instance.descriptor.bot_id
        if not name or name in self._factories:
            raise ValueError(f"Missing or duplicate bot id: {name}")
        self._factories[name] = factory
        self._descriptors[name] = instance.descriptor

    def get(self, bot_id: str) -> Bot:
        try:
            return self._factories[bot_id]()
        except KeyError as error:
            raise KeyError("Unknown bot") from error

    def list(self) -> list[BotDescriptor]:
        return list(self._descriptors.values())


def build_registry() -> BotRegistry:
    from app.bots.arcaptcha.bot import ArcaptchaBot
    from app.bots.examples.example_bot import ExampleBot

    registry = BotRegistry()
    registry.register(ArcaptchaBot)
    registry.register(ExampleBot)
    return registry
