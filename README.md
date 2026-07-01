# RainBot

RainBot is a comprehensive multi-service application featuring Discord and Telegram bots, a dedicated data scraper, and a Django-powered web backend. It provides detailed statistics, chronologies, and real-time updates.

> **Note:** This is a personal project built for private use with highly specific internal logic and configurations.

---

## Architecture & Service Structure

The project is built on a microservices architecture orchestrated via Docker Compose. 

* **db**: PostgreSQL 17 database serving as the primary centralized data store for all services.
* **orchestrator**: A standalone coordinator container acting as the central gRPC server. It manages cross-process data flows, processes incoming metrics from the scraper, and triggers notification states.
* **web-backend**: A Django ASGI (Uvicorn) web server providing the public-facing web interface and streaming API endpoints.
  * *Naming Convention:* The physical source files reside in the `services/web_backend/` directory, while the Docker service and network hostname are strictly defined as `web-backend` (with a hyphen) to comply with RFC 1034/1035 and prevent `Invalid HTTP_HOST` exceptions in Django.
* **caddy**: A reverse proxy and web server handling HTTPS (via DuckDNS), serving static assets, and routing public traffic to the `web-backend`.
* **bandit_scraper**: A data scraping service that collects information and feeds it to the orchestrator via gRPC.
* **bot_telegram**: The Telegram bot service, connecting directly to the database and reacting to orchestrator commands.
* **bot_discord**: A robust Discord bot service built with `disnake`. Contains internal expansion packages for audio streaming and high-frequency user presence tracking.

---

## Service Communication & Security

* **gRPC**: Internal service-to-service communication between the bots, scraper, and the standalone `orchestrator` runs over high-performance gRPC channels.
* **Internal Secure Webhook (Orchestrator ──► Django)**: To pass active rain events down to the web streaming layer, the orchestrator dispatches an internal HTTP POST request to `/api/v1/internal/rain-event/`. 
  * *Ingress Block:* Caddy is configured to drop any external traffic targeting the `/internal/*` URL path with a `403 Forbidden` response at the gate.
  * *Token Auth:* The endpoint is cryptographically secured inside the Docker network using token-based authentication verified against the shared `DJANGO_SECRET_KEY`.
* **Direct Database Access (Raw SQL)**: High-frequency analytical modules (such as the user presence tracker inside `bot_discord`) bypass the heavy Django runtime entirely. They write data directly into PostgreSQL via raw SQL queries over the async **`asyncpg`** driver to minimize server overhead.
* **HTTP/Web**: External web requests are managed by Caddy, which handles edge routing and proxies dynamic queries to the Django ASGI backend.

---

## Public API

RainBot provides a public HTTP API, including real-time event streaming via Server-Sent Events (SSE). 

For a complete specification of the available streaming frames, events, and parameters, please refer to the separate [Public API Documentation](docs/public_api.md).

---

## Web Interface

The Django backend serves a modern web interface for viewing charts, rooms grid matrices, and historical records. The backend serves raw UTC Unix timestamps, allowing the client-side JavaScript to dynamically render timelines adjusted to the viewer's local device timezone.

### Personal User Statistics with Timeline

<img width="1903" height="940" alt="Personal User Statistics" src="https://github.com/user-attachments/assets/d4c35601-9356-47f1-b6e8-96fbd555999f" />

### Voice Channels Timeline

<img width="1917" height="943" alt="Voice Channels Timeline" src="https://github.com/user-attachments/assets/622e23d6-b5b9-4cdf-9df1-abecc36c7944" />