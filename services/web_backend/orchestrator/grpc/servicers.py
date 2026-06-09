import os
import logging
import grpc
import rain_service_pb2
import rain_service_pb2_grpc
import discord_bot_pb2
import discord_bot_pb2_grpc
import telegram_bot_pb2
import telegram_bot_pb2_grpc

logger = logging.getLogger(__name__)

class OrchestratorServicer(rain_service_pb2_grpc.OrchestratorServiceServicer):
    """
    gRPC handler class for incoming orchestrator service calls.
    
    Implements RPC procedures specified in rain_service.proto.
    """
    
    def __init__(self) -> None:
        super().__init__()
        discord_addr = os.getenv("DISCORD_BOT_GRPC_ADDR", "bot_discord:50053")
        telegram_addr = os.getenv("TELEGRAM_BOT_GRPC_ADDR", "bot_telegram:50052")

        self.discord_channel = grpc.aio.insecure_channel(discord_addr)
        self.discord_stub = discord_bot_pb2_grpc.DiscordNotificationServiceStub(self.discord_channel)

        self.telegram_channel = grpc.aio.insecure_channel(telegram_addr)
        self.telegram_stub = telegram_bot_pb2_grpc.TelegramNotificationServiceStub(self.telegram_channel)

        logger.info(f"Orchestrator stubs initialized connecting to Discord ({discord_addr}) and Telegram ({telegram_addr})")

    async def SendRainUpdate(self, request, context):
        """
        Processes incoming rain state updates from the parser.
        """
        scrap = request.scrap_amount
        users = request.user_count
        event_type = request.event_type
        
        broadcast_request = discord_bot_pb2.RainBroadcastRequest(scrap_amount=scrap)
        
        try:
            if event_type == rain_service_pb2.RainEvent.STARTED:
                event_name = "STARTED"
                await self.discord_stub.BroadcastRainStarted(broadcast_request)
                await self.telegram_stub.BroadcastRainStarted(broadcast_request)
            
            elif event_type == rain_service_pb2.RainEvent.IN_PROGRESS:
                event_name = "UPDATED"
                await self.discord_stub.BroadcastRainUpdated(broadcast_request)
                await self.telegram_stub.BroadcastRainUpdated(broadcast_request)
            
            elif event_type == rain_service_pb2.RainEvent.ENDED:
                event_name = "ENDED"
                await self.discord_stub.BroadcastRainEnded(broadcast_request)
                await self.telegram_stub.BroadcastRainEnded(broadcast_request)
            
            else:
                event_name = "UNKNOWN"

            logger.info(f"[Orchestrator] Received signal from parser: Rain {event_name} (Scrap: {scrap}, Users: {users})")
            return rain_service_pb2.BaseResponse(success=True, error_message="")

        except grpc.RpcError as e:
            logger.error(f"[Orchestrator] Forwarding error: {e}")
            return rain_service_pb2.BaseResponse(success=False, error_message=str(e))