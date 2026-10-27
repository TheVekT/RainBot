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

class OrchestratorServicer(rain_service_pb2_grpc.OrchestratorServiceServicer):
    def __init__(self) -> None:
        super().__init__()
        discord_addr = os.getenv("DISCORD_BOT_GRPC_ADDR", "bot_discord:50053")
        telegram_addr = os.getenv("TELEGRAM_BOT_GRPC_ADDR", "bot_telegram:50052")

        self.discord_channel = grpc.aio.insecure_channel(discord_addr)
        self.discord_stub = discord_bot_pb2_grpc.DiscordNotificationServiceStub(self.discord_channel)

        self.telegram_channel = grpc.aio.insecure_channel(telegram_addr)
        self.telegram_stub = telegram_bot_pb2_grpc.TelegramNotificationServiceStub(self.telegram_channel)
        
        # Internal configuration variables
        self.django_secret_key = os.getenv("DJANGO_SECRET_KEY")
        self.django_port = os.getenv("DJANGO_PORT", "8000")
        self.internal_api_url = f"http://web-backend:{self.django_port}/api/v1/internal/rain-event/"

        logger.info(f"Orchestrator stubs initialized connecting to Discord ({discord_addr}) and Telegram ({telegram_addr})")

    async def SendRainUpdate(self, request, context):
        scrap = round(request.scrap_amount, 2) # fix: deserealization from 32-bit float (protobuf) to 64-bit float (python) breaks the float precision
        users = request.user_count
        event_type = request.event_type
        
        broadcast_request = discord_bot_pb2.RainBroadcastRequest(scrap_amount=scrap)
        
        try:
            if event_type == rain_service_pb2.RainEvent.STARTED:
                event_name = "rain_start"
                await self.discord_stub.BroadcastRainStarted(broadcast_request)
                await self.telegram_stub.BroadcastRainStarted(broadcast_request)
            
            elif event_type == rain_service_pb2.RainEvent.IN_PROGRESS:
                event_name = "rain_now"
                await self.discord_stub.BroadcastRainUpdated(broadcast_request)
                await self.telegram_stub.BroadcastRainUpdated(broadcast_request)
            
            elif event_type == rain_service_pb2.RainEvent.ENDED:
                event_name = "rain_ended"
                await self.discord_stub.BroadcastRainEnded(broadcast_request)
                await self.telegram_stub.BroadcastRainEnded(broadcast_request)
            
            else:
                event_name = "unknown"

            logger.info(f"[Orchestrator] Received signal from parser: Rain {event_name.upper()} (Scrap: {scrap}, Users: {users})")

            if event_name != "unknown":
                async with httpx.AsyncClient() as client:
                    headers = {
                        "Authorization": f"Bearer {self.django_secret_key}",
                        "Content-Type": "application/json"
                    }
                    logger.info(f"[Orchestrator] Sending POST to {self.internal_api_url}")
                    payload = {
                        "event": event_name,
                        "scrap": float(scrap),
                        "users": int(users)
                    }
                    response = await client.post(self.internal_api_url, json=payload, headers=headers, timeout=5.0)
                    
                    if response.status_code != 200:
                        logger.error(f"[Orchestrator] Django webhook failed with status: {response.status_code}")

            return rain_service_pb2.BaseResponse(success=True, error_message="")

        except grpc.RpcError as e:
            logger.error(f"[Orchestrator] Forwarding error: {e}")
            return rain_service_pb2.BaseResponse(success=False, error_message=str(e))
        except Exception as ex:
            logger.error(f"[Orchestrator] Webhook processing exception: {ex}")
            return rain_service_pb2.BaseResponse(success=False, error_message=str(ex))