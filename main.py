import asyncio
from rainbot.discordbot.main_bot import try_connect

if __name__ == "__main__":
    # Используем собственный цикл событий для управления переподключениями
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(try_connect())
    finally:
        loop.close()