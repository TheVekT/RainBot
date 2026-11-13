"""Read the public lifecycle state of the Discord client."""


class DiscordBotAdapter:
    def __init__(self, bot):
        self.bot = bot

    def snapshot(self):
        if self.bot.is_closed():
            return {'client': 'closed', 'gateway': 'disconnected'}
        if not self.bot.is_ready():
            return {'client': 'starting_or_reconnecting', 'gateway': 'not_ready'}

        # Client.is_ready() alone may be stale during a gateway disconnect. When
        # the websocket exposes its transport, include that independent signal.
        ws = getattr(self.bot, 'ws', None)
        socket = getattr(ws, 'socket', None) if ws is not None else None
        if socket is not None and getattr(socket, 'closed', None) is not None:
            gateway = 'disconnected' if socket.closed else 'connected'
        elif ws is not None and getattr(ws, 'open', None) is not None:
            gateway = 'connected' if ws.open else 'disconnected'
        else:
            gateway = 'ready_unverified'
        return {'client': 'ready', 'gateway': gateway}
