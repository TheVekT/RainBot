import grpc
import logging
import asyncio
from .servicers import OrchestratorServicer
import rain_service_pb2_grpc

logger = logging.getLogger(__name__)

async def serve(port="50051"):
    """
    Starts the gRPC server listening on the specified port.
    """
    server = grpc.aio.server()
    
    rain_service_pb2_grpc.add_OrchestratorServiceServicer_to_server(
        OrchestratorServicer(), server
    )
    
    server.add_insecure_port(f'[::]:{port}')
    await server.start()
    
    logger.info(f"[gRPC] Orchestrator is running and listening on port {port}...")
    
    await server.wait_for_termination()