/**
 * Server-side client for IntegrationLab universal telemetry.
 * This package is not published to npm and must not be shipped in a browser bundle.
 */

export {
  IntegrationLabClient,
  IntegrationLabConfigError,
  MAX_RATE_LIMITED_ATTEMPTS,
  MAX_RETRY_AFTER_MS,
  MIN_RETRY_AFTER_MS,
  categoryForStatus,
  parseRetryAfterMs,
  sanitizeRoute,
} from "./client.js";
export type {
  ClientStats,
  FlushResult,
  HttpObservationInput,
  InstrumentedRequestInit,
  Transport,
  TransportResult,
} from "./client.js";
