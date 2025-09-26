# Alerting & Notification Platform

## Setup with `uv`

```bash
# Install dependencies (uv will read from pyproject.toml)
uv sync

# Start RabbitMQ (required for Celery)
docker run -d --name rabbitmq -p 5672:5672 rabbitmq:3

# Run app
uv run uvicorn app:app --reload

# In another terminal: start Celery worker
uv run celery -A tasks.celery_app worker --loglevel=info

# In another terminal: start Celery beat (every 2 hours)
uv run celery -A tasks.celery_app beat -s celerybeat-schedule --max-interval=1
```

> **Note**: For demo, beat interval is 1s. In prod, use `--max-interval=7200`.

## Usage

- Admin UI: http://localhost:8000
- Get user token: `GET /token/alice`
- User alerts: `GET /user/alerts` with `Authorization: Bearer <token>`
- Snooze: `POST /user/alerts/1/snooze`
- Analytics: `GET /analytics`

## Seed Users

- `alice` (Engineering)
- `bob` (Marketing)
- `charlie` (Engineering)

## To-do

- use websockets
