# RainBot Public API Specification

This document provides a technical reference for the public HTTP API endpoints.

---

## Rain Event Stream

Exposes a real-time event stream consumed by clients to receive live updates of active rain events.

- **Endpoint:** `/api/v1/rain/stream/`
- **Method:** `GET`
- **Access Control:** Public (no authentication required)
- **Protocol:** Server-Sent Events (SSE)

### Responses

| Status | Description |
| :--- | :--- |
| `200` | SSE stream established successfully |

### Response Headers

| Header | Value | Description |
| :--- | :--- | :--- |
| `Content-Type` | `text/event-stream` | Identifies the response as an SSE stream |
| `Cache-Control` | `no-cache` | Prevents intermediate caching |
| `X-Accel-Buffering` | `no` | Disables proxy-level buffering |

### Stream Lifecycle and Behavior

- The connection remains open until the client disconnects or the server closes the stream.
- Upon connection, the server sends the initial `: connected` SSE comment.
- Rain updates are transmitted when received by the API server.
- If no data has been transmitted for **20 seconds**, the server sends a heartbeat comment (`: ping`).
- Receiving a rain update resets the idle heartbeat timer.
- SSE comments do not trigger the browser `EventSource.onmessage` handler.
- Disconnected clients are removed from the active listener registry.
- Browser `EventSource` clients automatically attempt to reconnect after a connection loss.
- Events published while a client is disconnected are **not buffered or replayed**.

### SSE Event Format

Rain updates are standard SSE `data:` messages terminated by a double newline (`\n\n`):

```text
data: {"event": "rain_start", "scrap": 32.34, "users": 17}

data: {"event": "rain_now", "scrap": 45.67, "users": 304}

data: {"event": "rain_ended", "scrap": 45.67, "users": 304}

```

#### Event Payload Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `event` | `string` | One of `rain_start`, `rain_now`, `rain_ended` |
| `scrap` | `number` | Current amount of scrap collected |
| `users` | `integer` | Number of active users participating |

### Heartbeat Mechanism

When no rain updates are available, the server periodically transmits a lightweight SSE comment to keep the connection active.

- **Idle interval:** 20 seconds
- **Format:** SSE comment (`: ping`)
- **Client action required:** None

```text
: ping

```

Lines beginning with `:` are SSE comments, ignored by standard event handlers. Heartbeats contain no application data and require no acknowledgment.

#### Example Stream

```text
: connected

: ping

: ping

data: {"event": "rain_start", "scrap": 32.34, "users": 17}

: ping

data: {"event": "rain_now", "scrap": 45.67, "users": 304}

data: {"event": "rain_ended", "scrap": 45.67, "users": 304}

: ping

```

### Connection Reliability

- Heartbeats help prevent idle connection timeouts imposed by proxies and network infrastructure, but do not guarantee availability.
- Clients supporting SSE reconnection (such as browser `EventSource`) reconnect automatically after a dropped connection.
- The API currently does not provide event IDs, `Last-Event-ID` recovery, or replay of missed events.
- Applications requiring guaranteed event delivery must implement additional recovery mechanisms.
