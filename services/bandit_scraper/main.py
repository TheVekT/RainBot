import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.scraper_core.parser import RainParser
from modules.rain_stats.stats import RainStatsRecorder
from config import ScraperConfigManager
from grpc_client import OrchestratorNotifier

async def main():
    """
    Main entrypoint. Initializes components, wires up signals, and starts the scrapper loop.
    """
    print("[INIT] Initializing Bandit Scraper service...")

    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/rainbot_db")
    grpc_address = os.getenv("ORCHESTRATOR_GRPC_HOST", "web_backend:50051")
    
    config_manager = ScraperConfigManager(db_url=db_url)
    
    if await config_manager.load():
        print(f"[INIT] Config loaded. Retention days: {config_manager.rain_stats_retention_days}")
    else:
        print(f"[INIT] Using fallback default retention days: {config_manager.rain_stats_retention_days}")
        
    parser = RainParser()
    tracker = RainStatsRecorder(db_url=db_url, retention_days=config_manager.rain_stats_retention_days)
    notifier = OrchestratorNotifier(grpc_address=grpc_address)

    # Wire up signals
    parser.on_rain_started.connect(notifier.notify_start)
    parser.on_rain_updated.connect(notifier.notify_update)
    parser.on_rain_ended.connect(notifier.notify_end)
    parser.on_rain_ended.connect(tracker.record_rain_end)

    print("[INIT] Components connected. Starting background tasks...")
    await tracker.start()

    try:
        await parser.run()
    except asyncio.CancelledError:
        print("[SHUTDOWN] Shutdown signal received...")
    finally:
        await tracker.stop()
        await notifier.close()
        await parser.close_browsers()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[SHUTDOWN] Execution interrupted by user (Ctrl+C)")