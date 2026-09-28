"""FastAPI application entrypoint for IntegrationLab."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import failure_lab, github, health, integrations, oauth, provider_requests
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()

app = FastAPI(
    title="IntegrationLab",
    description="Partner-integration reliability console (Failure Lab + GitHub OAuth)",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(integrations.router)
app.include_router(github.router)
app.include_router(oauth.router)
app.include_router(provider_requests.router)
app.include_router(failure_lab.router)
