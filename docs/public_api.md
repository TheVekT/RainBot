# RainBot Public API Specification

This document provides a technical reference for the public HTTP API endpoints.

---

## Rain Event Stream

Exposes a real-time event stream consumed by clients to receive live updates of active rain events.

* **Endpoint**: `/api/v1/rain/stream/`
* **Method**: `GET`
* **Access Control**: Public (No authentication required)
* **Protocol**: Server-Sent Events (SSE)

### Responses

| Status | Description |
| :--- | :--- |
| `200` | SSE stream established successfully |

### Response Headers

| Header | Value | Description |
| :--- | :--- | :--- |
| `Content-Type` | `text/event-stream` | Identifies response as an SSE stream |
| `Cache-Control` | `no-cache` | Prevents intermediate caching |
| `X-Accel-Buffering` | `no` | Disables proxy-level buffering |

### Stream Lifecycle and Behavior

* The connection remains open until the client disconnects or the server closes the stream.
* Events are sent only when a rain event update occurs. No periodic keep-alive or heartbeat messages are emitted.

### SSE Event Format

Updates are emitted as standard SSE data chunks with double-newline terminators (`\n\n`):

```event-stream
data: {"event": "rain_start", "scrap": 12.34, "users": 5}

data: {"event": "rain_now", "scrap": 15.67, "users": 10}

data: {"event": "rain_ended", "scrap": 15.67, "users": 10}
```

* `event` (string): One of: `rain_start`, `rain_now`, `rain_ended`.
* `scrap` (number): The current amount of scrap collected.
* `users` (integer): The number of active users participating.
