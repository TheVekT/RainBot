import json
import asyncio
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

# Global state to keep track of all active client SSE connections
class EventBroadcaster:
    def __init__(self):
        self.listeners = set()

    def add_listener(self, queue: asyncio.Queue):
        self.listeners.add(queue)

    def remove_listener(self, queue: asyncio.Queue):
        self.listeners.discard(queue)

    def broadcast(self, data: dict):
        payload = json.dumps(data)
        for queue in self.listeners:
            queue.put_nowait(payload)

broadcaster = EventBroadcaster()


@csrf_exempt
async def internal_rain_event(request):
    """
    Internal secure endpoint invoked via HTTP POST by the Orchestrator container.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    # Token authentication check using DJANGO_SECRET_KEY
    auth_header = request.headers.get("Authorization", "")
    expected_token = f"Bearer {settings.SECRET_KEY}"
    
    if auth_header != expected_token:
        return JsonResponse({"error": "Forbidden"}, status=403)

    try:
        body = json.loads(request.body)
        event_type = body.get("event")
        scrap = float(body.get("scrap", 0.0))
        users = int(body.get("users", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "Bad request payload"}, status=400)

    # Dispatches payload across all active SSE consumer queues
    broadcaster.broadcast({
        "event": event_type,
        "scrap": scrap,
        "users": users
    })

    return JsonResponse({"success": True})


async def rain_stream(request):
    """
    Public SSE connection endpoint consumed by external RainCollector clients.
    """
    async def event_generator():
        queue = asyncio.Queue()
        broadcaster.add_listener(queue)
        try:
            while True:
                # Execution suspends until a new message arrives in the queue
                payload = await queue.get()
                yield f"data: {payload}\n\n"
                queue.task_done()
        except asyncio.CancelledConnectionError:
            # Safely handled when client disconnects or connection drops
            pass
        finally:
            broadcaster.remove_listener(queue)

    response = StreamingHttpResponse(event_generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # Prevents Nginx/Proxy from buffering the stream
    return response