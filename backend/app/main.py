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
from app.core.config import Settings, get_settings
from app.core.operator_auth import OperatorAuthMiddleware
from app.core.telemetry_body_limit import TelemetryBodyLimitMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application (used by tests and the module-level ``app``)."""
    resolved = settings or get_settings()
    docs_on = resolved.api_docs_enabled()
    application = FastAPI(
        title="IntegrationLab",
        description=(
            "Partner integration reliability console (GitHub OAuth, Failure Lab, Stripe webhooks, "
            "SDK-reported HTTP telemetry, reliability dashboard, guided diagnostics, support cases)"
        ),
        version="0.9.0",
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    application.add_middleware(TelemetryBodyLimitMiddleware)
    application.add_middleware(OperatorAuthMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(integrations.router)
    application.include_router(ingestion_credentials.router)
    application.include_router(telemetry.router)
    application.include_router(github.router)
    application.include_router(oauth.router)
    application.include_router(provider_requests.router)
    application.include_router(failure_lab.router)
    application.include_router(stripe_webhooks.public_router)
    application.include_router(stripe_webhooks.router)
    application.include_router(reliability.router)
    application.include_router(diagnostics.router)
    application.include_router(support_cases.router)
    application.include_router(audit.router)
    return application


app = create_app()
