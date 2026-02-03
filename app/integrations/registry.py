from typing import Optional

from app.integrations.base import BaseIntegration


class IntegrationRegistry:
    _instance: Optional["IntegrationRegistry"] = None
    _integrations: dict[str, BaseIntegration]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._integrations = {}
        return cls._instance

    def register(self, integration: BaseIntegration):
        self._integrations[integration.name] = integration

    def get(self, name: str) -> Optional[BaseIntegration]:
        return self._integrations.get(name)

    def list_all(self) -> list[BaseIntegration]:
        return list(self._integrations.values())

    def list_configured(self) -> list[BaseIntegration]:
        return [i for i in self._integrations.values() if i.is_configured()]


integration_registry = IntegrationRegistry()


def register_integrations():
    from app.integrations.teamwork import TeamworkIntegration
    from app.integrations.slack import SlackIntegration
    from app.integrations.miro import MiroIntegration
    from app.integrations.telegram import TelegramIntegration

    integration_registry.register(TeamworkIntegration())
    integration_registry.register(SlackIntegration())
    integration_registry.register(MiroIntegration())
    integration_registry.register(TelegramIntegration())
