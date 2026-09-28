"""Process due webhook events once, then exit.

    python -m app.scripts.process_webhooks [--limit 25]

Run it from cron/a loop for a simple worker. Multiple concurrent runs are
safe: rows are claimed with SELECT ... FOR UPDATE SKIP LOCKED.
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.core.database import SessionLocal
from app.services.webhook_processor import MAX_BATCH, stripe_webhook_processor

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process due Stripe webhook events once.")
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help=f"Maximum events to process in this run (1-{MAX_BATCH}).",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_BATCH:
        parser.error(f"--limit must be between 1 and {MAX_BATCH}")

    session = SessionLocal()
    try:
        counts = stripe_webhook_processor.process_due(session, limit=args.limit)
    finally:
        session.close()

    print(f"Processed: {counts.processed}")
    print(f"Retry scheduled: {counts.retry_scheduled}")
    print(f"Failed: {counts.failed}")
    print(f"Ignored: {counts.ignored}")
    if counts.skipped:
        print(f"Skipped (locked elsewhere or no longer due): {counts.skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
