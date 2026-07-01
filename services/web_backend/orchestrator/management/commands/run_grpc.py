from django.core.management.base import BaseCommand
import asyncio
import os
from orchestrator.grpc.serve import serve

class Command(BaseCommand):
    """
    Django management command to start the gRPC Orchestrator server.
    """
    help = 'Starts the gRPC Orchestrator server'

    def handle(self, *args, **options):
        port = os.getenv("GRPC_PORT", "50051")
        self.stdout.write(self.style.SUCCESS(f"Starting gRPC server on port {port}..."))
        
        try:
            asyncio.run(serve(port=port))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nStopping gRPC server..."))