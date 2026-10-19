# Uptime Monitor

**A self-hosted uptime monitoring platform with a live dashboard, incident tracking, and Slack/Discord alerts.**

Built to explore the scheduling, state-management, and failure-handling problems behind tools like UptimeRobot and Pingdom: how do you check many endpoints on independent schedules, open an incident exactly once when something breaks, and alert the right people when it recovers?

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5-37814A?logo=celery&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

---

## Dashboard

<!-- TODO: add a screenshot at docs/dashboard.png, then uncomment the two lines below. -->
<!-- ![Uptime Monitor dashboard](docs/dashboard.png) -->

> A dark, auto-refreshing dashboard showing monitor health, uptime percentages, a 40-check history timeline per endpoint, and recent incident recoveries.

---

## Table of contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Data model](#data-model)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Testing](#testing)
- [Design decisions](#design-decisions)
- [Known limitations & roadmap](#known-limitations--roadmap)
- [License](#license)
- [Author](#author)

---

## Overview

Uptime Monitor periodically sends HTTP requests to the endpoints you register and records the result of every check. When an endpoint starts failing, the app opens an **incident** and fires a webhook alert. When it recovers, the incident is resolved and a recovery alert is sent.

The UI is server-rendered with **FastAPI + Jinja2 + HTMX** — no SPA, no frontend build step. The dashboard updates itself every 5 seconds, and every action (add, edit, pause, force-check, delete) happens through HTMX partial swaps without a full page reload.

Checks run asynchronously in **Celery workers** backed by **Redis**, scheduled by a single **Celery Beat** heartbeat that polls PostgreSQL for monitors that are due. PostgreSQL is the source of truth for scheduling, so workers can scale horizontally without duplicating schedule state.

---

## Features

- **HTTP/HTTPS monitoring** with configurable intervals (15 seconds, 1 minute, or 5 minutes)
- **Live dashboard** that refreshes every 5 seconds via HTMX polling
- **Per-monitor history** — the last 40 checks rendered as a color-coded timeline with hover details
- **Uptime percentage** calculated from stored check results
- **Incident detection** with automatic open/resolve transitions and duration tracking
- **Incident history** panel showing the 10 most recent recoveries
- **Webhook alerting** compatible with both Slack and Discord
- **Force check** button to run a check immediately, bypassing the schedule
- **Pause / resume / edit / delete** monitors without touching the database
- **Health endpoint** for container and load-balancer probes
- **Alembic migrations** for versioned schema changes
- **Docker Compose** stack (web, worker, beat, PostgreSQL, Redis) for one-command startup
- **Test suite** covering scheduling, failure handling, and incident transitions

---

## Architecture

```mermaid
flowchart LR
    subgraph Client
        B[Browser<br/>HTMX + Tailwind]
    end

    subgraph Application
        W[FastAPI<br/>Jinja2 templates]
    end

    subgraph Data
        DB[(PostgreSQL)]
        R[(Redis<br/>broker + backend)]
    end

    subgraph Workers
        BE[Celery Beat<br/>15s heartbeat]
        CW[Celery Worker<br/>HTTP checks]
    end

    T[Target URLs]
    H[Slack / Discord<br/>webhook]

    B -->|HTTP| W
    W -->|read / write| DB
    W -->|force check| R
    BE -->|dispatch_due_checks| R
    R -->|consume tasks| CW
    CW -->|HTTP GET| T
    CW -->|results + incidents| DB
    CW -->|alerts| H
```

### Components

| Component | Responsibility |
|---|---|
| **FastAPI** (`app/main.py`) | Serves the dashboard, renders Jinja2 templates, returns HTML fragments for HTMX, and enqueues manual checks. |
| **Celery Beat** (`app/celery_app.py`) | Runs one fixed task every 15 seconds (`dispatch_due_checks`) instead of maintaining a schedule per monitor. |
| **Celery Worker** (`app/tasks.py`) | Performs the HTTP checks, writes results, opens/resolves incidents, and sends webhook alerts. |
| **PostgreSQL** | Stores monitors, check results, and incidents; also acts as the scheduling queue via `monitors.next_check_at`. |
| **Redis** | Celery broker and result backend. |
| **HTMX + Tailwind** | Drives the live UI through partial HTML swaps, with no client-side framework or bundler. |

### How a check flows

1. Celery Beat enqueues `dispatch_due_checks` every **15 seconds**.
2. The dispatcher queries for monitors where `is_active = true` **and** `next_check_at <= now()`.
3. Each due monitor gets a `check_url.delay(monitor_id)` task.
4. The worker sends an HTTP `GET` with a **30-second timeout** and redirects followed.
5. The response is stored as a `CheckResult` (`is_up`, `status_code`, `response_time_ms`, or `error_message`).
6. The incident state machine runs (see below), then `next_check_at` is advanced by the monitor's interval.

A response is considered **up** when `status_code < 400`. Timeouts, DNS failures, and connection errors are recorded as failed checks rather than crashing the task.

### Incident lifecycle

An incident is **open** while `resolved_at IS NULL`. Transitions are driven entirely by the latest check result:

| Open incident? | Check result | Action |
|---|---|---|
| No | Up | Record result only |
| No | Down | Record result, **open incident**, send `DOWN` alert |
| Yes | Down | Record result only (no duplicate incidents) |
| Yes | Up | Record result, **resolve incident**, send `UP` alert |

This makes incident creation idempotent under repeated failures — the behavior is covered by a dedicated test.

---

## Tech stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI |
| Templating | Jinja2 |
| UI interactivity | HTMX 1.9, Tailwind CSS (CDN) |
| ORM | SQLAlchemy 2.0 (typed `Mapped` models) |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Task queue | Celery 5 with Redis |
| HTTP client | httpx |
| Configuration | pydantic-settings (`.env`) |
| Containerization | Docker, Docker Compose |
| Testing | pytest, pytest-cov, unittest.mock |
| Linting | Ruff |

---

## Data model

```mermaid
erDiagram
    MONITORS ||--o{ CHECK_RESULTS : records
    MONITORS ||--o{ INCIDENTS : opens

    MONITORS {
        int id PK
        string name
        string url
        int check_interval_seconds
        datetime next_check_at
        bool is_active
        datetime created_at
    }

    CHECK_RESULTS {
        int id PK
        int monitor_id FK
        datetime checked_at
        bool is_up
        int status_code
        int response_time_ms
        string error_message
    }

    INCIDENTS {
        int id PK
        int monitor_id FK
        datetime started_at
        datetime resolved_at
    }
```

The `next_check_at` column is the heart of the scheduler: the dispatcher reads it, the worker advances it. `resolved_at` being `NULL` is the single source of truth for an active outage.

---

## API reference

All routes return HTML (full pages or HTMX fragments) except `/health`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Full dashboard page |
| `GET` | `/health` | JSON liveness probe: `{"status": "ok", "timestamp": ...}` |
| `GET` | `/monitors/fragment` | HTML fragment of all monitors, polled every 5s |
| `POST` | `/monitors` | Create a monitor (`name`, `url`, `interval` form fields) |
| `POST` | `/monitors/{id}/check-now` | Enqueue an immediate check |
| `POST` | `/monitors/{id}/pause` | Toggle a monitor between active and paused |
| `DELETE` | `/monitors/{id}` | Delete a monitor and its results/incidents |
| `GET` | `/monitors/{id}/edit` | Edit modal fragment |
| `POST` | `/monitors/{id}/edit` | Update `name`, `url`, `interval` |
| `GET` | `/worker-status` | Worker status badge fragment |

> Interactive OpenAPI docs are available at `/docs` while the server is running.

---

## Project structure

```
uptime-monitor/
├── app/
│   ├── main.py                  # FastAPI routes, dashboard context, HTMX fragments
│   ├── tasks.py                 # check_url + dispatch_due_checks Celery tasks
│   ├── celery_app.py            # Celery configuration and beat schedule
│   ├── core/
│   │   └── config.py            # pydantic-settings configuration
│   ├── db/
│   │   ├── base.py              # SQLAlchemy declarative base
│   │   └── session.py           # Engine and session factory
│   ├── models/
│   │   ├── monitor.py           # Monitored endpoint + schedule state
│   │   ├── check_result.py      # Individual check outcome
│   │   └── incident.py          # Outage open/resolve state
│   └── templates/
│       ├── index.html           # Dashboard shell, HTMX setup
│       ├── _monitor_list.html   # Stats, monitor cards, sparkline, incidents
│       └── _edit_modal.html     # Edit dialog fragment
├── alembic/
│   ├── env.py                   # Reads DATABASE_URL from app settings
│   └── versions/                # Initial schema migration
├── tests/
│   ├── conftest.py              # Celery eager mode fixture
│   └── test_tasks.py            # Check, incident, and dispatcher tests
├── docker-compose.yml           # web, worker, beat, db, redis
├── Dockerfile                   # python:3.13-slim image
├── alembic.ini
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

---

## Getting started

### Prerequisites

- Docker and Docker Compose **or** Python 3.13+, PostgreSQL 16, and Redis 7

### Run with Docker (recommended)

```bash
git clone https://github.com/hamilwt/uptime-monitor.git
cd uptime-monitor

cp .env.example .env          # PowerShell: Copy-Item .env.example .env

docker compose up --build -d
docker compose exec web alembic upgrade head
```

Open **http://localhost:8000**.

Migrations are not run automatically. If the web container starts before PostgreSQL is ready, rerun `alembic upgrade head` once the database is up.

Useful commands:

```bash
docker compose logs -f web worker beat   # follow logs
docker compose down                      # stop the stack
docker compose down -v                   # stop and delete the database volume
```

> The app, worker, and beat services share one image with no source bind mount, so code changes require `docker compose up --build`.

### Run locally (without Docker)

```bash
python -m venv venv
# Windows:        venv\Scripts\activate
# macOS / Linux:  source venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
```

Start the dependencies (or point the URLs at your own instances):

```bash
docker compose up -d db redis
```

Create a `.env` file with local hostnames:

```env
DATABASE_URL=postgresql://admin:local_dev_password@localhost:5432/uptime_db
REDIS_URL=redis://localhost:6379/0
```

Then apply migrations and start each process in its own terminal:

```bash
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info
```

> **Windows:** run the worker with `--pool=solo`:
> `celery -A app.celery_app worker --loglevel=info --pool=solo`

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string. Use host `db` inside Compose, `localhost` for local development. |
| `REDIS_URL` | Yes | Redis connection string used as both Celery broker and result backend. |
| `WEBHOOK_URL` | No | Slack or Discord incoming webhook. Alerts are skipped when unset. |
| `SECRET_KEY` | No | Reserved for future session/auth signing; not used yet. |

The webhook payload includes both `text` and `content` keys so the same alert works with Slack and Discord.

---

## Testing

```bash
pytest -q
pytest --cov=app --cov-report=term-missing
ruff check .
```

The suite covers:

- Successful checks creating results and advancing `next_check_at`
- Network failures creating failed results and opening an incident
- Consecutive failures **not** duplicating an open incident
- Recovery resolving the existing incident
- The dispatcher skipping paused and not-yet-due monitors

`tests/conftest.py` enables Celery **eager mode**, so `.delay()` executes synchronously and the tests need no Redis or running worker. Outbound HTTP calls are mocked with `unittest.mock.patch`.

> **Warning:** tests use the database from your `.env` and delete all rows from `monitors`, `check_results`, and `incidents` before each test. Point `DATABASE_URL` at a dedicated test database — never at production.

---

## Design decisions

**Dispatcher instead of per-monitor schedules.** Rather than creating a dynamic Celery Beat entry for every monitor, one fixed 15-second heartbeat queries PostgreSQL for due work. Adding, pausing, or rescheduling a monitor is a database write, not a scheduler mutation. The tradeoff is 15-second scheduling granularity and one cheap polling query per heartbeat.

**PostgreSQL as the source of truth for scheduling.** `next_check_at` lives with the monitor row. Any worker can process any task, and adding workers requires no coordination — which is what makes the worker tier horizontally scalable.

**Server-rendered UI with HTMX.** Every mutation returns a fresh HTML fragment that HTMX swaps into the page. There is no JSON API layer, no client state duplication, and no Node build pipeline. One artifact is deployed, and every route is inspectable with `curl`.

**Incidents as state, not event spam.** The `resolved_at IS NULL` check makes incident opening idempotent: a monitor that fails ten times in a row still produces exactly one incident and exactly one alert. Recovery closes that same row, giving an accurate outage duration for free.

**Network failures are data, not crashes.** `httpx.RequestError` is caught and persisted as a failed `CheckResult` with the error message. A timeout is exactly the condition the system exists to observe, so it must not be swallowed as a worker exception.

**Fast, deterministic tests.** Celery eager mode plus a mocked HTTP client means the entire scheduling and incident logic is tested in-process, with no broker, no worker, and no network.

---

## Known limitations & roadmap

Current limitations, stated deliberately:

- **No authentication.** The dashboard and all mutating routes are open. Intended for trusted networks or local use.
- **`/worker-status` is a placeholder.** It always returns "Workers Active" and does not inspect Celery heartbeats.
- **Check results are never pruned.** `check_results` grows without bound, and uptime percentages are computed over the full history in the template.
- **Schedule drift.** The next check is scheduled from task completion time, so intervals are "at least N seconds," not wall-clock aligned.
- **HTTP GET only, 2xx/3xx = up.** No custom methods, headers, request bodies, expected status codes, or response-content assertions.
- **Single shared alert channel.** One `WEBHOOK_URL` applies to every monitor.

Planned improvements:

- [ ] User accounts, sessions, and per-user monitors
- [ ] Real worker heartbeat backed by Celery `inspect().ping()`
- [ ] Check-result retention policy and hourly/daily rollups
- [ ] Per-monitor configuration: method, headers, body, expected status, keyword assertions
- [ ] Per-monitor alert channels (Slack, Discord, email)
- [ ] Latency percentiles (p50/p95/p99) and uptime windows (24h / 7d / 30d)
- [ ] SSL certificate expiry monitoring
- [ ] Readiness probe that verifies database and Redis connectivity
- [ ] GitHub Actions CI pipeline with coverage reporting
- [ ] Prometheus metrics endpoint

---

## License

Released under the MIT License.

---

## Author

**Mohammed Hamil P R**

- GitHub: [@hamilwt](https://github.com/hamilwt)
- Email: [mohammedhamil100@gmail.com](mailto:mohammedhamil100@gmail.com)
