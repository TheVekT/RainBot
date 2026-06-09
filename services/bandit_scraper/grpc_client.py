import grpc
import asyncio

import rain_service_pb2
import rain_service_pb2_grpc

class OrchestratorNotifier:
    """
    gRPC client that notifies the Orchestrator service of rain events.
    """
    def __init__(self, grpc_address: str):
        self.grpc_address = grpc_address
        self.channel = grpc.aio.insecure_channel(self.grpc_address)
        self.stub = rain_service_pb2_grpc.OrchestratorServiceStub(self.channel)
        print(f"[gRPC] Client initialized. Orchestrator address: {self.grpc_address}")

    async def close(self):
        """
        Safely closes the network connection channel.
        """
        if self.channel:
            await self.channel.close()
            print("[gRPC] Connection channel closed.")

    async def _send_event(self, event_type, scrap_amount: float, user_count: int):
        """
        Base method to send a rain event via gRPC.
        """
        try:
            request = rain_service_pb2.RainEvent(
                event_type=event_type,
                scrap_amount=float(scrap_amount),
                user_count=int(user_count)
            )
            
            response = await self.stub.SendRainUpdate(request, timeout=5.0)
            
            if not response.success:
                print(f"[gRPC-WARN] Django returned logical error: {response.error_message}")
                
        except grpc.RpcError as e:
            print(f"[gRPC-ERROR] Network error when contacting Django: {e.details()} (code: {e.code()})")
        except Exception as e:
            print(f"[gRPC-ERROR] Unexpected error: {e}")

    async def notify_start(self, scrap_amount: float, user_count: int):
        """
        Sends a rain started notification.
        """
        print("[gRPC] Sending signal: Rain STARTED")
        await self._send_event(
            event_type=rain_service_pb2.RainEvent.STARTED, 
            scrap_amount=scrap_amount, 
            user_count=user_count
        )

    async def notify_update(self, scrap_amount: float, user_count: int):
        """
        Sends a rain updated notification.
        """
        await self._send_event(
            event_type=rain_service_pb2.RainEvent.IN_PROGRESS, 
            scrap_amount=scrap_amount, 
            user_count=user_count
        )

    async def notify_end(self, scrap_amount: float, user_count: int):
        """
        Sends a rain ended notification.
        """
        print("[gRPC] Sending signal: Rain ENDED")
        await self._send_event(
            event_type=rain_service_pb2.RainEvent.ENDED, 
            scrap_amount=scrap_amount, 
            user_count=user_count
        )