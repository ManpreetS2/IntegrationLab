/**
 * Server-side client for IntegrationLab universal telemetry.
 * This package is not published to npm and must not be shipped in a browser bundle.
 */

export {
  IntegrationLabClient,
  IntegrationLabConfigError,
  categoryForStatus,
  sanitizeRoute,
} from "./client.js";
export type {
  ClientStats,
  FlushResult,
  HttpObservationInput,
  InstrumentedRequestInit,
  Transport,
} from "./client.js";
