"""Server-side client for IntegrationLab universal telemetry.

This package is not published to PyPI. Install it from a local checkout.
It must not be bundled into browser JavaScript.
"""

from integrationlab.client import (
    ClientStats,
    FlushResult,
    IntegrationLabClient,
    IntegrationLabConfigError,
)

__all__ = [
    "ClientStats",
    "FlushResult",
    "IntegrationLabClient",
    "IntegrationLabConfigError",
]
__version__ = "0.1.0"
