"""Independent application that reports real HTTP outcomes to IntegrationLab.

Run this only after an instrumented integration and ingestion credential exist.
Configuration comes from the environment. The ingestion credential is sent as
an Authorization header by the SDK and is never printed.
"""

from __future__ import annotations

import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from integrationlab import IntegrationLabClient


def main() -> int:
    upstream = os.environ["DEMO_UPSTREAM"].rstrip("/")
    lab = IntegrationLabClient.from_env()
    calls = (
        ("/ok", "/ok", 2.0),
        ("/limited", "/limited", 2.0),
        ("/fail", "/fail", 2.0),
        ("/hang", "/hang", 0.3),
        ("/ok", "/ok", 2.0),
    )
    for path, template, timeout in calls:
        print(f"GET {path} -> {perform(lab, f'{upstream}{path}', template, timeout)}", flush=True)
    result = lab.close()
    print(
        "flush "
        f"accepted={result.accepted} duplicates={result.duplicates} "
        f"dropped={result.dropped} rejected={result.rejected}",
        flush=True,
    )
    return 0 if result.delivered and result.dropped == 0 and result.accepted == 5 else 1


def perform(lab: IntegrationLabClient, url: str, template: str, timeout: float) -> str:
    """Make one real request. Exceptions still leave observe(); this function classifies them."""
    try:
        with lab.observe(service="local-fixture", method="GET", route_template=template) as observation:
            try:
                with urlopen(url, timeout=timeout) as response:
                    response.read()
                    observation.set_status(response.status)
                    return str(response.status)
            except HTTPError as exc:
                exc.read()
                observation.set_status(exc.code)
                raise
            except TimeoutError:
                observation.set_timeout()
                raise
            except URLError as exc:
                if isinstance(getattr(exc, "reason", None), TimeoutError):
                    observation.set_timeout()
                raise
    except HTTPError as exc:
        return str(exc.code)
    except TimeoutError:
        return "timeout"
    except URLError as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError):
            return "timeout"
        return "transport_error"


if __name__ == "__main__":
    sys.exit(main())
