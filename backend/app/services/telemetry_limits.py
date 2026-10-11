"""Closed bounds for universal telemetry ingestion.

These limits are part of the v1 contract. They keep one self-hosted API process
from accepting unbounded payloads, timestamps, or credential fan-out.
"""

from datetime import timedelta

MAX_BATCH_EVENTS = 100
MAX_BODY_BYTES = 262144
MAX_DURATION_MS = 300_000
MAX_ROUTE_TEMPLATE_LENGTH = 200
MAX_EVENT_AGE = timedelta(hours=24)
MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_ACTIVE_CREDENTIALS = 5

AUTH_FAILURES_PER_WINDOW = 30
INGEST_REQUESTS_PER_WINDOW = 60
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_RETRY_AFTER_SECONDS = 60
