# Gotham Emergency Services Dispatch System — Backend Vertical Prototype

A high-performance Python/FastAPI backend vertical slice powering Gotham City's next-generation Emergency Services Dispatch System.

Supports real-time reporting of **FIRE**, **POLICE**, and **MEDICAL** emergencies by citizens, interactive dispatcher unit assignment and status lifecycle tracking, and real-time updates broadcast to dispatcher clients via WebSockets.

---

## Architecture Overview

```text
+---------------------+               +---------------------------+
|    Citizen Client   |               |     Dispatcher Client     |
|   (Mobile / Web)    |               |  (Real-Time Dashboard)    |
+----------+----------+               +-------------+-------------+
           |                                        ^
    REST   | Submit Report                          | WebSocket Stream
           v                                        | /ws/dispatch
+---------------------------------------------------+-------------+
|                                                                 |
|                         FastAPI Backend                         |
|                                                                 |
|  +---------------------+   +---------------------------------+  |
|  |  Citizen Service    |   |       Dispatcher Service        |  |
|  +----------+----------+   +----------------+----------------+  |
|             |                               |                   |
|             v                               v                   |
|  +-----------------------------------------------------------+  |
|  |                   WebSocket Broadcaster                   |  |
|  +-----------------------------------------------------------+  |
|                                                                 |
+--------------------------------+--------------------------------+
                                 |
                                 v SQLAlchemy 2.0 ORM
                    +--------------------------+
                    | SQLite / PostgreSQL DB   |
                    +--------------------------+
```

---

## Features & Technology Stack

* **Language & Framework**: Python 3.11+ / FastAPI
* **Database**: SQLite (`gotham_dispatch.db`) with SQLAlchemy 2.x ORM & Pydantic 2.x schemas (abstracted for seamless PostgreSQL migration)
* **Real-Time Dispatch**: WebSockets (`/ws/dispatch`) with initial state snapshot on connect and broadcast event channels
* **Validation**: Coordinates (-90 to 90 lat, -180 to 180 lon), emergency types (`FIRE`, `POLICE`, `MEDICAL`), priorities (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
* **State Machine Enforcer**: Strictly controls status transitions (`REPORTED` -> `ACKNOWLEDGED` -> `DISPATCHED` -> `EN_ROUTE` -> `ON_SCENE` -> `RESOLVED` / `CANCELLED`), rejecting invalid state mutations with HTTP 409 Conflict
* **Transactional Unit Assignment**: Atomic assignment of `AVAILABLE` units to incidents, updating unit status to `DISPATCHED` and advancing incident status

---

## Project Structure

```text
gotham-dispatch/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app definition, CORS, & routers
│   ├── database.py          # SQLAlchemy engine, session maker, DB dependency
│   ├── models.py            # SQLAlchemy 2.0 ORM models (Incident, Unit, Assignment)
│   ├── schemas.py           # Pydantic v2 schemas and Enums
│   ├── websocket.py         # ConnectionManager for WebSocket broadcasting
│   ├── seed.py              # Initial seed script for Gotham response units
│   └── services/
│       ├── __init__.py
│       ├── incident_service.py # Report lifecycle & broadcast logic
│       └── dispatch_service.py # Unit creation & transactional assignment logic
├── tests/
│   ├── __init__.py
│   └── test_api.py          # Pytest suite (18 automated tests)
├── requirements.txt
├── Makefile
├── README.md
└── .gitignore
```

---

## Installation & Quickstart

### Prerequisites

* Python 3.11+

### Step 1: Clone & Setup Environment

```bash
# Setup virtual environment
py -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Seed Initial Gotham Units

Populates default response units (`FIRE-01`, `FIRE-02`, `POLICE-01`, `POLICE-02`, `MED-01`, `MED-02`):

```bash
python -m app.seed
```

### Step 3: Run Server

```bash
uvicorn app.main:app --reload --port 8000
```

The service will start at `http://localhost:8000`.

---

## API Endpoints & Usage Examples

### Interactive Documentation

* **Swagger UI**: `http://localhost:8000/docs`
* **ReDoc**: `http://localhost:8000/redoc`
* **OpenAPI Spec**: `http://localhost:8000/openapi.json`

---

### 1. Health Check

```http
GET /health
```

**Response (HTTP 200)**:
```json
{
  "status": "ok",
  "service": "gotham-emergency-dispatch"
}
```

---

### 2. Citizen Emergency Report Submission

```http
POST /api/v1/reports
Content-Type: application/json
```

**Request**:
```json
{
  "type": "MEDICAL",
  "description": "Person collapsed outside Gotham Central Bank.",
  "latitude": 14.5995,
  "longitude": 120.9842,
  "address": "123 Gotham Avenue",
  "priority": "HIGH"
}
```

**Response (HTTP 201)**:
```json
{
  "id": "e3b8a1c9-7d84-47b2-9d33-9118c4e402a1",
  "type": "MEDICAL",
  "description": "Person collapsed outside Gotham Central Bank.",
  "latitude": 14.5995,
  "longitude": 120.9842,
  "address": "123 Gotham Avenue",
  "priority": "HIGH",
  "status": "REPORTED",
  "created_at": "2026-08-13T10:50:00Z",
  "updated_at": "2026-08-13T10:50:00Z"
}
```

---

### 3. Dispatcher Reports Listing & Status Update

#### List Reports (Filtered)

```http
GET /api/v1/dispatch/reports?status=REPORTED
```

#### Update Incident Status

```http
PATCH /api/v1/dispatch/reports/{incident_id}/status
Content-Type: application/json

{
  "status": "ACKNOWLEDGED"
}
```

---

### 4. Response Units & Assignments

#### Register Unit

```http
POST /api/v1/units
Content-Type: application/json

{
  "type": "MEDICAL",
  "call_sign": "MED-12",
  "latitude": 14.6000,
  "longitude": 120.9850
}
```

#### List Units (Filtered by Type)

```http
GET /api/v1/dispatch/units?unit_type=MEDICAL
```

#### Assign Unit to Incident

```http
POST /api/v1/dispatch/reports/{incident_id}/units/{unit_id}
```

**Response (HTTP 200)**:
```json
{
  "id": "a90184b2-0041-48e1-a20c-7b249001f3e1",
  "incident_id": "e3b8a1c9-7d84-47b2-9d33-9118c4e402a1",
  "unit_id": "b18274a1-1122-3344-5566-77889900aabb",
  "assigned_at": "2026-08-13T10:52:00Z",
  "unassigned_at": null
}
```

---

## Real-Time Dispatcher WebSocket (`/ws/dispatch`)

Connect dispatcher clients to:
```text
ws://localhost:8000/ws/dispatch
```

### 1. Initial Snapshot Event (Sent on Connection)

```json
{
  "event": "INITIAL_SNAPSHOT",
  "incidents": [
    {
      "id": "e3b8a1c9-7d84-47b2-9d33-9118c4e402a1",
      "type": "MEDICAL",
      "status": "REPORTED",
      "priority": "HIGH",
      "...": "..."
    }
  ]
}
```

### 2. Event Types Broadcasted in Real Time

* **`INCIDENT_CREATED`**: Broadcast when a citizen submits a new report.
* **`INCIDENT_STATUS_UPDATED`**: Broadcast when a dispatcher advances report status.
* **`UNIT_ASSIGNED`**: Broadcast when a unit is assigned to an incident.

Example `UNIT_ASSIGNED` payload:
```json
{
  "event": "UNIT_ASSIGNED",
  "incident_id": "e3b8a1c9-7d84-47b2-9d33-9118c4e402a1",
  "unit_id": "b18274a1-1122-3344-5566-77889900aabb",
  "unit_call_sign": "MED-12",
  "status": "DISPATCHED"
}
```

---

## Running Automated Tests

Run the full pytest suite:

```bash
pytest tests/ -v
```

Output:
```text
======================== 18 passed in 1.16s ========================
```

---

## Database Information

* Prototype uses SQLite database `gotham_dispatch.db`.
* SQLAlchemy 2.0 ORM abstractions guarantee compatibility with PostgreSQL (switch by setting `DATABASE_URL=postgresql://user:password@localhost/gotham_dispatch`).

---

## Security Scope & Limitations

* **Auth**: Currently unauthenticated for vertical prototype testing. A `TODO` tag marks requirements for OAuth2 / JWT authentication before production.
* **WebSocket In-Memory Manager**: Connected clients are tracked in memory. For multi-node deployment, replace with Redis Pub/Sub.

---

## Future Backlog

1. **Dispatcher Auth**: Add JWT role-based authorization for dispatcher endpoints.
2. **Automated Nearest-Unit Selection**: Spatial query (e.g. PostGIS / Haversine distance) to suggest nearest available unit.
3. **Redis Event Bus**: Scale real-time WebSockets horizontally using Redis Pub/Sub.
4. **PostgreSQL Migration**: Move database engine to PostgreSQL with alembic migrations.
