import asyncio
import os
import logging
import grpc
import httpx
import rain_service_pb2
import rain_service_pb2_grpc
import discord_bot_pb2
import discord_bot_pb2_grpc
import telegram_bot_pb2
import telegram_bot_pb2_grpc

logger = logging.getLogger(__name__)

RPC_TIMEOUT = 3.0


class OrchestratorServicer(rain_service_pb2_grpc.OrchestratorServiceServicer):
    EVENTS = {
        rain_service_pb2.RainEvent.STARTED: ("rain_start", "BroadcastRainStarted"),
        rain_service_pb2.RainEvent.IN_PROGRESS: ("rain_now", "BroadcastRainUpdated"),
        rain_service_pb2.RainEvent.ENDED: ("rain_ended", "BroadcastRainEnded"),
    }

    def __init__(self) -> None:
        super().__init__()
        discord_addr = os.getenv("DISCORD_BOT_GRPC_ADDR", "bot_discord:50053")
        telegram_addr = os.getenv("TELEGRAM_BOT_GRPC_ADDR", "bot_telegram:50052")

        self.discord_channel = grpc.aio.insecure_channel(discord_addr)
        self.telegram_channel = grpc.aio.insecure_channel(telegram_addr)
        self.discord_stub = discord_bot_pb2_grpc.DiscordNotificationServiceStub(self.discord_channel)
        self.telegram_stub = telegram_bot_pb2_grpc.TelegramNotificationServiceStub(self.telegram_channel)

        self.django_secret_key = os.getenv("DJANGO_SECRET_KEY")
        port = os.getenv("DJANGO_PORT", "8000")
        self.internal_api_url = f"http://web-backend:{port}/api/v1/internal/rain-event/"

        logger.info("Orchestrator initialized: Discord=%s, Telegram=%s", discord_addr, telegram_addr)

    async def _send_sse(self, event: str, scrap: float, users: int) -> None:
        async with httpx.AsyncClient(timeout=RPC_TIMEOUT) as client:
            response = await client.post(
                self.internal_api_url,
                json={"event": event, "scrap": scrap, "users": users},
                headers={"Authorization": f"Bearer {self.django_secret_key}"}
            )
            response.raise_for_status()

    async def SendRainUpdate(self, request, context):
        event_info = self.EVENTS.get(request.event_type)
        if event_info is None:
            return rain_service_pb2.BaseResponse(
                success=False, error_message=f"Unknown event type: {request.event_type}"
            )

        event_name, method = event_info
        scrap = round(request.scrap_amount, 2)
        users = request.user_count

        logger.info("[Orchestrator] Rain %s (Scrap: %.2f, Users: %d)", event_name, scrap, users)

        results = await asyncio.gather(
            getattr(self.discord_stub, method)(
                discord_bot_pb2.RainBroadcastRequest(scrap_amount=scrap),
                timeout=RPC_TIMEOUT
            ),
            getattr(self.telegram_stub, method)(
                telegram_bot_pb2.RainBroadcastRequest(scrap_amount=scrap),
                timeout=RPC_TIMEOUT
            ),
            self._send_sse(event_name, scrap, users),
            return_exceptions=True
        )

        errors = []
        for service, result in zip(("Discord", "Telegram", "SSE"), results):
            if isinstance(result, asyncio.CancelledError):
                raise result

            if isinstance(result, BaseException):
                error = str(result)
            elif service != "SSE" and not result.success:
                error = result.error_message or "Service returned success=False"
            else:
                logger.info("[Orchestrator] %s accepted %s", service, event_name)
                continue

            logger.error("[Orchestrator] %s failed: %s", service, error)
            errors.append(f"{service}: {error}")

        if errors:
            logger.warning(
                "[Orchestrator] Partial delivery: %d/3 destinations failed",
                len(errors)
            )

        return rain_service_pb2.BaseResponse(
            success=not errors,
            error_message="; ".join(errors)
        )