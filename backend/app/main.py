"""FastAPI application entrypoint for IntegrationLab."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    audit,
    diagnostics,
    failure_lab,
    github,
    health,
    ingestion_credentials,
    integrations,
    oauth,
    provider_requests,
    reliability,
    stripe_webhooks,
    support_cases,
    telemetry,
)
from app.core.config import get_settings
from app.core.operator_auth import OperatorAuthMiddleware
from app.core.telemetry_body_limit import TelemetryBodyLimitMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()

app = FastAPI(
    title="IntegrationLab",
    description=(
        "Partner integration reliability console (GitHub OAuth, Failure Lab, Stripe webhooks, "
        "SDK-reported HTTP telemetry, reliability dashboard, guided diagnostics, support cases)"
    ),
    version="0.9.0",
)

app.add_middleware(TelemetryBodyLimitMiddleware)
app.add_middleware(OperatorAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(integrations.router)
app.include_router(ingestion_credentials.router)
app.include_router(telemetry.router)
app.include_router(github.router)
app.include_router(oauth.router)
app.include_router(provider_requests.router)
app.include_router(failure_lab.router)
app.include_router(stripe_webhooks.public_router)
app.include_router(stripe_webhooks.router)
app.include_router(reliability.router)
app.include_router(diagnostics.router)
app.include_router(support_cases.router)
app.include_router(audit.router)
