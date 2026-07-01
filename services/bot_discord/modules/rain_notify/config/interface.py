from typing import Protocol, Any

class ConfigField(Protocol):
    """
    Interface for an individual configuration parameter.
    """
    async def get(self) -> Any: ...
    async def set(self, value: Any) -> None: ...


class NotifyConfigProvider(Protocol):
    """
    Interface defining the structured fields that a configuration provider must supply.
    """
    @property
    def rain_channel_id(self) -> ConfigField: ...

    @property
    def voice_notify_enabled(self) -> ConfigField: ...

    @property
    def text_notify_enabled(self) -> ConfigField: ...