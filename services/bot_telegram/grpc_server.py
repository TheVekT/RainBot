"""
Asynchronous gRPC Server implementation for receiving orchestrator commands.
Runs completely inside the main asyncio event loop alongside the Telegram bot.
"""

import logging
import grpc

import telegram_bot_pb2
import telegram_bot_pb2_grpc
from utils.signal import Signal

logger = logging.getLogger(__name__)


class TelegramServicer(telegram_bot_pb2_grpc.TelegramNotificationServiceServicer):
    """gRPC Servicer class handling incoming notifications from the Orchestrator."""

    def __init__(self) -> None:
        super().__init__()
        self.on_rain_started = Signal()
        self.on_rain_updated = Signal()
        self.on_rain_ended = Signal()

    async def BroadcastRainStarted(
        self,
        request: telegram_bot_pb2.RainBroadcastRequest,
        context: grpc.aio.ServicerContext,
    ) -> telegram_bot_pb2.CommandResponse:
        """Trigger rain started broadcast notification."""
        logger.info("[gRPC] Command received: Rain STARTED (%s scrap)", request.scrap_amount)
        self.on_rain_started.emit(request.scrap_amount)
        return telegram_bot_pb2.CommandResponse(success=True, error_message="")

    async def BroadcastRainUpdated(
        self,
        request: telegram_bot_pb2.RainBroadcastRequest,
        context: grpc.aio.ServicerContext,
    ) -> telegram_bot_pb2.CommandResponse:
        """Trigger rain updated broadcast notification."""
        self.on_rain_updated.emit(request.scrap_amount)
        return telegram_bot_pb2.CommandResponse(success=True, error_message="")

    async def BroadcastRainEnded(
        self,
        request: telegram_bot_pb2.RainBroadcastRequest,
        context: grpc.aio.ServicerContext,
    ) -> telegram_bot_pb2.CommandResponse:
        """Trigger rain ended broadcast notification."""
        logger.info("[gRPC] Command received: Rain ENDED (%s scrap)", request.scrap_amount)
        self.on_rain_ended.emit(request.scrap_amount)
        return telegram_bot_pb2.CommandResponse(success=True, error_message="")


async def start_grpc_server(
    servicer: TelegramServicer,
    port: str = "50052",
) -> None:
    """Start the asynchronous gRPC server listening for notification requests."""
    server = grpc.aio.server()
    telegram_bot_pb2_grpc.add_TelegramNotificationServiceServicer_to_server(
        servicer, server
    )
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info("[gRPC] Telegram Listener running on port %s...", port)
    
    try:
        await server.wait_for_termination()
    finally:
        logger.info("[gRPC] Stopping asynchronous server...")
        await server.stop(grace=5)