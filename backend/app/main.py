"""FastAPI application entrypoint for IntegrationLab Day 1."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, integrations
from app.core.config import CORS_ORIGINS

app = FastAPI(
    title="IntegrationLab",
    description="Partner-integration reliability console (Day 1 foundation)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(integrations.router)
