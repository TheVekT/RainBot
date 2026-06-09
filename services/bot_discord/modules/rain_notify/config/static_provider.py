from typing import Any

class ConfigField:
    def __init__(self, default_value: Any) -> None:
        self._value = default_value

    async def get(self) -> Any:
        return self._value

    async def set(self, value: Any) -> None:
        self._value = value


class StaticNotifyConfigProvider:
    """
    Fallback or testing configuration provider.
    """
    def __init__(self) -> None:
        self._rain_channel_id = ConfigField(None)
        self._voice_notify_enabled = ConfigField(True)
        self._text_notify_enabled = ConfigField(True)

    @property
    def rain_channel_id(self) -> ConfigField:
        return self._rain_channel_id

    @property
    def voice_notify_enabled(self) -> ConfigField:
        return self._voice_notify_enabled

    @property
    def text_notify_enabled(self) -> ConfigField:
        return self._text_notify_enabled