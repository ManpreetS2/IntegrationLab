/**
 * Bounded delivery of SDK-reported HTTP observations.
 * Delivery failures stay inside the client and do not change the host call.
 */

export const SDK_NAME = "integrationlab-node";
export const SDK_VERSION = "0.1.0";

const ENVIRONMENTS = new Set(["local", "test", "staging", "production"]);
const METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]);
const DROP_STATUSES = new Set([400, 401, 403, 413, 422]);
const RETRY_AFTER_STATUSES = new Set([429, 503]);
export const MAX_RETRY_AFTER_MS = 120_000;
/** Floor when Retry-After is 0 / a past HTTP-date — avoids a busy spin. */
export const MIN_RETRY_AFTER_MS = 50;
/** Separate budget so Retry-After waits cannot loop forever. */
export const MAX_RATE_LIMITED_ATTEMPTS = 5;
const RETRY_AFTER_SECONDS_RE = /^[0-9]{1,10}$/;
/** IMF-fixdate (RFC 7231), e.g. Sun, 06 Nov 1994 08:49:37 GMT */
const IMF_FIXDATE_RE = /^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT$/;

export class IntegrationLabConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "IntegrationLabConfigError";
  }
}

export interface ClientStats {
  queued: number;
  dropped: number;
  rejected: number;
  accepted: number;
  duplicates: number;
  deliveryFailures: number;
  rateLimited: number;
}

export interface FlushResult {
  delivered: boolean;
  accepted: number;
  duplicates: number;
  dropped: number;
  rejected: number;
  lastError: string | null;
}

export interface HttpObservationInput {
  service: string;
  method: string;
  routeTemplate: string;
  statusCode: number | null;
  durationMs: number;
  errorCategory?: string | null;
  occurredAt?: Date;
  environment?: string;
}

export type TransportResult = {
  status: number;
  body: string;
  headers?: Record<string, string>;
};

export type Transport = (
  url: string,
  body: string,
  headers: Record<string, string>,
  timeoutMs: number,
) => Promise<TransportResult>;

export type InstrumentedRequestInit = RequestInit & {
  integrationlabRouteTemplate?: string;
};

export interface ClientConfig {
  baseUrl: string;
  integrationId: string;
  credential: string;
  environment?: string;
  timeoutMs?: number;
  maxQueue?: number;
  batchSize?: number;
  maxRetries?: number;
  retryBackoffMs?: number;
  transport?: Transport;
  fetchImpl?: typeof fetch;
  /** Injectable sleep for tests (milliseconds). */
  sleep?: (ms: number) => Promise<void>;
}

interface EventBody {
  event_id: string;
  integration_id: string;
  occurred_at: string;
  kind: "http_observation";
  service: string;
  method: string;
  route_template: string;
  status_code: number | null;
  duration_ms: number;
  error_category: string | null;
  environment: string;
  provenance: "sdk_reported";
  sdk: { name: string; version: string };
}

export class IntegrationLabClient {
  readonly stats: ClientStats = {
    queued: 0,
    dropped: 0,
    rejected: 0,
    accepted: 0,
    duplicates: 0,
    deliveryFailures: 0,
    rateLimited: 0,
  };

  private readonly baseUrl: string;
  private readonly integrationId: string;
  private readonly credential: string;
  private readonly environment: string;
  private readonly timeoutMs: number;
  private readonly maxQueue: number;
  private readonly batchSize: number;
  private readonly maxRetries: number;
  private readonly retryBackoffMs: number;
  private readonly transport: Transport;
  private readonly sleepFn: (ms: number) => Promise<void>;
  private readonly customSleep: boolean;
  private readonly buffer: EventBody[] = [];
  private tail: Promise<void> = Promise.resolve();
  private stopped = false;
  private lastError: string | null = null;
  private activeDelay: { cancel: () => void } | null = null;

  constructor(config: ClientConfig) {
    assertServerSide();
    const parsed = parseBaseUrl(config.baseUrl);
    if (!isUuid(config.integrationId)) {
      throw new IntegrationLabConfigError("integrationId must be a UUID");
    }
    if (!config.credential.startsWith("ilk_v1_")) {
      throw new IntegrationLabConfigError(
        "credential must be an IntegrationLab ingestion credential. Do not use the operator API key.",
      );
    }
    const environment = config.environment ?? "local";
    if (!ENVIRONMENTS.has(environment)) {
      throw new IntegrationLabConfigError("environment must be local, test, staging, or production");
    }
    this.baseUrl = parsed;
    this.integrationId = config.integrationId;
    this.credential = config.credential;
    this.environment = environment;
    this.timeoutMs = config.timeoutMs ?? 2000;
    this.maxQueue = config.maxQueue ?? 1000;
    this.batchSize = Math.min(config.batchSize ?? 50, 100);
    this.maxRetries = config.maxRetries ?? 3;
    this.retryBackoffMs = config.retryBackoffMs ?? 200;
    this.transport = config.transport ?? defaultTransport(config.fetchImpl ?? fetch);
    this.customSleep = config.sleep !== undefined;
    this.sleepFn = config.sleep ?? sleep;
    if (this.timeoutMs <= 0 || this.maxQueue < 1 || this.batchSize < 1 || this.maxRetries < 1) {
      throw new IntegrationLabConfigError("timeout, queue, batch size, and retries must be positive");
    }
  }

  static fromEnv(env: NodeJS.ProcessEnv = process.env, overrides: Partial<ClientConfig> = {}): IntegrationLabClient {
    const missing = [
      "INTEGRATIONLAB_BASE_URL",
      "INTEGRATIONLAB_INTEGRATION_ID",
      "INTEGRATIONLAB_INGESTION_CREDENTIAL",
    ].filter((name) => !env[name]);
    if (missing.length) {
      throw new IntegrationLabConfigError(`Missing IntegrationLab configuration: ${missing.join(", ")}`);
    }
    return new IntegrationLabClient({
      baseUrl: env.INTEGRATIONLAB_BASE_URL as string,
      integrationId: env.INTEGRATIONLAB_INTEGRATION_ID as string,
      credential: env.INTEGRATIONLAB_INGESTION_CREDENTIAL as string,
      environment: env.INTEGRATIONLAB_ENVIRONMENT ?? "local",
      ...overrides,
    });
  }

  recordHttp(input: HttpObservationInput): boolean {
    const event = buildEvent(this.integrationId, this.environment, input);
    if (!event) {
      this.stats.rejected += 1;
      return false;
    }
    if (this.stopped || this.buffer.length >= this.maxQueue) {
      this.stats.dropped += 1;
      return false;
    }
    this.buffer.push(event);
    this.stats.queued += 1;
    this.tail = this.tail.then(() => this.drain()).catch(() => undefined);
    return true;
  }

  instrumentFetch(
    fetchImpl: typeof fetch,
    options: { service: string; routeTemplate?: string },
  ): (input: string | URL | Request, init?: InstrumentedRequestInit) => Promise<Response> {
    const lab = this;
    return async (input, init) => {
      const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
      const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const template = init?.integrationlabRouteTemplate ?? options.routeTemplate ?? sanitizeRoute(rawUrl);
      const started = Date.now();
      try {
        const response = await fetchImpl(input, init);
        const category = categoryForStatus(response.status);
        if (category === undefined) {
          lab.stats.rejected += 1;
        } else {
          lab.recordHttp({
            service: options.service,
            method,
            routeTemplate: template,
            statusCode: response.status,
            durationMs: elapsed(started),
            errorCategory: category,
          });
        }
        return response;
      } catch (error) {
        lab.recordHttp({
          service: options.service,
          method,
          routeTemplate: template,
          statusCode: null,
          durationMs: elapsed(started),
          errorCategory: isTimeout(error) ? "timeout" : "transport_error",
        });
        throw error;
      }
    };
  }

  async flush(timeoutMs = 5000): Promise<FlushResult> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const tail = this.tail;
      const remaining = Math.max(0, deadline - Date.now());
      const timer = delay(remaining);
      const finished = await Promise.race([tail.then(() => true), timer.promise.then(() => false)]);
      timer.cancel();
      if (finished && this.buffer.length === 0 && tail === this.tail) {
        break;
      }
      if (!finished) break;
    }
    return {
      delivered: this.buffer.length === 0,
      accepted: this.stats.accepted,
      duplicates: this.stats.duplicates,
      dropped: this.stats.dropped,
      rejected: this.stats.rejected,
      lastError: this.lastError,
    };
  }

  async close(timeoutMs = 5000): Promise<FlushResult> {
    // Signal stop before flush so in-flight Retry-After loops abort promptly.
    this.stopped = true;
    this.activeDelay?.cancel();
    this.activeDelay = null;
    return this.flush(timeoutMs);
  }

  private async drain(): Promise<void> {
    while (this.buffer.length > 0 && !this.stopped) {
      const batch = this.buffer.splice(0, this.batchSize);
      try {
        await this.deliver(batch);
      } catch {
        this.lastError = "delivery_error";
        this.stats.dropped += batch.length;
        this.stats.deliveryFailures += 1;
      }
    }
  }

  private async waitOrStop(ms: number): Promise<boolean> {
    if (this.stopped) return true;
    if (this.customSleep) {
      await this.sleepFn(ms);
      return this.stopped;
    }
    const handle = delay(ms);
    this.activeDelay = handle;
    try {
      await handle.promise;
    } finally {
      if (this.activeDelay === handle) this.activeDelay = null;
    }
    return this.stopped;
  }

  private async deliver(batch: EventBody[]): Promise<void> {
    let attempt = 0;
    let rateLimitedAttempts = 0;
    while (attempt < this.maxRetries) {
      if (this.stopped) break;
      try {
        const response = await this.transport(
          `${this.baseUrl}/api/telemetry/v1/events`,
          JSON.stringify({ events: batch }),
          {
            Authorization: `Bearer ${this.credential}`,
            "Content-Type": "application/json",
            "User-Agent": `${SDK_NAME}/${SDK_VERSION}`,
          },
          this.timeoutMs,
        );
        if (response.status === 200) {
          const counts = ackCounts(response.body, batch.length);
          this.stats.accepted += counts.accepted;
          this.stats.duplicates += counts.duplicates;
          this.lastError = null;
          return;
        }
        this.lastError = `http_${response.status}`;
        if (DROP_STATUSES.has(response.status)) {
          this.stats.rejected += batch.length;
          return;
        }
        if (RETRY_AFTER_STATUSES.has(response.status)) {
          const retryAfterMs = parseRetryAfterMs(headerValue(response.headers, "Retry-After"));
          if (retryAfterMs !== null) {
            rateLimitedAttempts += 1;
            this.stats.rateLimited += 1;
            if (rateLimitedAttempts >= MAX_RATE_LIMITED_ATTEMPTS) {
              break;
            }
            const waitMs = Math.min(Math.max(retryAfterMs, MIN_RETRY_AFTER_MS), MAX_RETRY_AFTER_MS);
            if (await this.waitOrStop(waitMs)) break;
            continue;
          }
        }
      } catch {
        this.lastError = "transport_error";
      }
      attempt += 1;
      if (attempt < this.maxRetries && this.retryBackoffMs > 0) {
        if (await this.waitOrStop(this.retryBackoffMs * 2 ** (attempt - 1))) break;
      }
    }
    this.stats.dropped += batch.length;
    this.stats.deliveryFailures += 1;
  }
}

export function categoryForStatus(statusCode: number): string | null | undefined {
  if (statusCode >= 200 && statusCode <= 399) return null;
  if (statusCode === 429) return "rate_limited";
  if (statusCode >= 400 && statusCode <= 499) return "http_client_error";
  if (statusCode >= 500 && statusCode <= 599) return "http_server_error";
  return undefined;
}

export function sanitizeRoute(url: string): string {
  let path = "/";
  try {
    path = new URL(url).pathname || "/";
  } catch {
    path = url.split("?")[0]?.split("#")[0] ?? "/";
  }
  const segments = path
    .split("/")
    .filter((segment) => segment && segment !== "." && segment !== "..")
    .map((segment) => (looksLikeIdentifier(segment) ? "{id}" : segment.replace(/[^\w.~!$&'()*+,;=-]/g, "").slice(0, 64) || "{id}"));
  const route = `/${segments.join("/")}` || "/";
  return route.slice(0, 200);
}

function looksLikeIdentifier(segment: string): boolean {
  if (/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(segment)) {
    return true;
  }
  if (/^\d+$/.test(segment) && segment.length > 6) return true;
  return segment.length >= 16 && /^[0-9a-fA-F]+$/.test(segment);
}

function buildEvent(integrationId: string, environment: string, input: HttpObservationInput): EventBody | null {
  const method = input.method.trim().toUpperCase();
  const service = input.service;
  const route = input.routeTemplate;
  const duration = input.durationMs;
  const statusCode = input.statusCode;
  const category = input.errorCategory ?? null;
  const occurred = input.occurredAt ?? new Date();
  const env = input.environment ?? environment;
  if (!METHODS.has(method)) return null;
  if (!/^[a-z0-9][a-z0-9._-]{0,62}$/.test(service)) return null;
  if (!route.startsWith("/") || route.length > 200 || /[ ?#\\@%]/.test(route) || route.includes("://")) return null;
  if (!Number.isInteger(duration) || duration < 0 || duration > 300_000) return null;
  if (!ENVIRONMENTS.has(env)) return null;
  if (statusCode === null) {
    if (category !== "timeout" && category !== "transport_error") return null;
  } else {
    if (!Number.isInteger(statusCode)) return null;
    const expected = categoryForStatus(statusCode);
    if (expected === undefined || category !== expected) return null;
  }
  return {
    event_id: crypto.randomUUID(),
    integration_id: integrationId,
    occurred_at: occurred.toISOString(),
    kind: "http_observation",
    service,
    method,
    route_template: route,
    status_code: statusCode,
    duration_ms: duration,
    error_category: category,
    environment: env,
    provenance: "sdk_reported",
    sdk: { name: SDK_NAME, version: SDK_VERSION },
  };
}

function ackCounts(body: string, batchSize: number): { accepted: number; duplicates: number } {
  try {
    const parsed = JSON.parse(body) as { accepted?: number; duplicates?: number };
    return {
      accepted: Number.isInteger(parsed.accepted) ? (parsed.accepted as number) : batchSize,
      duplicates: Number.isInteger(parsed.duplicates) ? (parsed.duplicates as number) : 0,
    };
  } catch {
    return { accepted: batchSize, duplicates: 0 };
  }
}

export function parseRetryAfterMs(value: string | null | undefined, nowMs: number = Date.now()): number | null {
  /** Accept only plain non-negative integer seconds (≤10 digits) or IMF-fixdate. */
  if (value === null || value === undefined) return null;
  const text = value.trim();
  if (!text) return null;
  if (RETRY_AFTER_SECONDS_RE.test(text)) {
    return Number.parseInt(text, 10) * 1000;
  }
  if (!IMF_FIXDATE_RE.test(text)) return null;
  const when = Date.parse(text);
  if (Number.isNaN(when)) return null;
  return Math.max(0, when - nowMs);
}

function headerValue(headers: Record<string, string> | undefined, name: string): string | null {
  if (!headers) return null;
  const target = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === target) return value;
  }
  return null;
}

function defaultTransport(fetchImpl: typeof fetch): Transport {
  return async (url, body, headers, timeoutMs) => {
    const response = await fetchImpl(url, {
      method: "POST",
      headers,
      body,
      signal: AbortSignal.timeout(timeoutMs),
    });
    const text = await response.text();
    const responseHeaders: Record<string, string> = {};
    response.headers.forEach((value, key) => {
      responseHeaders[key] = value;
    });
    return { status: response.status, body: text.slice(0, 2048), headers: responseHeaders };
  };
}

function parseBaseUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new IntegrationLabConfigError("baseUrl must be an http or https URL");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new IntegrationLabConfigError("baseUrl must be an http or https URL");
  }
  return value.replace(/\/+$/, "");
}

function isUuid(value: string): boolean {
  return /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(value);
}

function assertServerSide(): void {
  const browser = typeof globalThis !== "undefined" && "window" in globalThis && "document" in globalThis;
  if (browser) {
    throw new IntegrationLabConfigError(
      "The IntegrationLab SDK is server-side only and must not run in a browser bundle.",
    );
  }
}

function elapsed(started: number): number {
  return Math.min(300_000, Math.max(0, Date.now() - started));
}

function isTimeout(error: unknown): boolean {
  return error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
}

function sleep(ms: number): Promise<void> {
  return delay(ms).promise;
}

function delay(ms: number): { promise: Promise<void>; cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let resolveFn: (() => void) | undefined;
  let settled = false;
  const promise = new Promise<void>((resolve) => {
    resolveFn = resolve;
    timer = setTimeout(() => {
      settled = true;
      resolve();
    }, ms);
    // Allow Node to exit while a Retry-After wait is outstanding.
    timer.unref?.();
  });
  return {
    promise,
    cancel: () => {
      if (timer !== undefined) clearTimeout(timer);
      if (!settled && resolveFn) {
        settled = true;
        resolveFn();
      }
    },
  };
}
