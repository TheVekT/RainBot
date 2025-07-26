import asyncio
from rainbot.discordbot.main_bot import try_connect

async def shutdown(loop):
    current_task = asyncio.current_task()
    tasks = [task for task in asyncio.all_tasks(loop=loop) if task is not current_task]
    if tasks:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(try_connect())
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        loop.run_until_complete(shutdown(loop))
        loop.close()