import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import {
  IntegrationLabClient,
  IntegrationLabConfigError,
  MAX_RATE_LIMITED_ATTEMPTS,
  MAX_RETRY_AFTER_MS,
  MIN_RETRY_AFTER_MS,
  isValidRouteTemplate,
  parseRetryAfterMs,
  sanitizeRoute,
} from "../dist/index.js";

const INTEGRATION_ID = "5c1e1b3a-1b2c-4d5e-8f90-123456789abc";
const CREDENTIAL = `ilk_v1_0123456789ab_${"a".repeat(43)}`;

function client(transport, overrides = {}) {
  return new IntegrationLabClient({
    baseUrl: "http://127.0.0.1:8010",
    integrationId: INTEGRATION_ID,
    credential: CREDENTIAL,
    timeoutMs: 200,
    maxRetries: 3,
    retryBackoffMs: 0,
    transport,
    ...overrides,
  });
}

function ok() {
  return Promise.resolve({ status: 200, body: '{"accepted":1,"duplicates":0,"results":[]}' });
}

test("records a successful call without putting the credential in the body", async () => {
  const calls = [];
  const lab = client(async (url, body, headers, timeoutMs) => {
    calls.push({ url, body, headers, timeoutMs });
    return ok();
  });
  assert.equal(
    lab.recordHttp({
      service: "orders-api",
      method: "get",
      routeTemplate: "/v1/orders/{id}",
      statusCode: 200,
      durationMs: 15,
    }),
    true,
  );
  const result = await lab.flush(2000);
  assert.equal(result.delivered, true);
  assert.equal(lab.stats.accepted, 1);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].headers.Authorization, `Bearer ${CREDENTIAL}`);
  const event = JSON.parse(calls[0].body).events[0];
  assert.equal(event.provenance, "sdk_reported");
  assert.equal(event.status_code, 200);
  assert.equal(event.error_category, null);
  assert.equal(calls[0].body.includes(CREDENTIAL), false);
  await lab.close();
});

test("records HTTP 500, timeout, and transport failure", async () => {
  const calls = [];
  const lab = client(async (_url, body) => {
    calls.push(JSON.parse(body));
    return ok();
  });
  const wrapped = lab.instrumentFetch(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/fail")) return new Response("nope", { status: 500 });
    if (url.endsWith("/slow")) throw Object.assign(new Error("timed out"), { name: "TimeoutError" });
    if (url.endsWith("/down")) throw new Error("ECONNREFUSED");
    return new Response("ok", { status: 200 });
  }, { service: "orders-api", routeTemplate: "/v1/items/{id}" });

  const success = await wrapped("https://upstream.test/ok");
  assert.equal(success.status, 200);
  const failed = await wrapped("https://upstream.test/fail");
  assert.equal(failed.status, 500);
  await assert.rejects(() => wrapped("https://upstream.test/slow"), { name: "TimeoutError" });
  await assert.rejects(() => wrapped("https://upstream.test/down"), /ECONNREFUSED/);
  await lab.flush(2000);
  const events = calls.flatMap((batch) => batch.events);
  assert.deepEqual(
    events.map((event) => event.error_category).sort(),
    ["http_server_error", "timeout", "transport_error", null].sort(),
  );
  assert.equal(events.every((event) => event.route_template === "/v1/items/{id}"), true);
  await lab.close();
});

test("ingestion outage retries then drops without throwing", async () => {
  let calls = 0;
  const lab = client(async () => {
    calls += 1;
    throw new Error("integrationlab down");
  });
  assert.equal(
    lab.recordHttp({
      service: "orders-api",
      method: "GET",
      routeTemplate: "/health",
      statusCode: 200,
      durationMs: 4,
    }),
    true,
  );
  const result = await lab.flush(2000);
  assert.equal(calls, 3);
  assert.equal(lab.stats.dropped, 1);
  assert.equal(lab.stats.deliveryFailures, 1);
  assert.equal(result.lastError, "transport_error");
  await lab.close();
});

test("HTTP 422 is not retried", async () => {
  let calls = 0;
  const lab = client(async () => {
    calls += 1;
    return { status: 422, body: "{\"detail\":\"no\"}" };
  });
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 200,
    durationMs: 4,
  });
  await lab.flush(2000);
  assert.equal(calls, 1);
  assert.equal(lab.stats.rejected, 1);
  assert.equal(lab.stats.dropped, 0);
  await lab.close();
});

test("retries a 503 and then accepts the event", async () => {
  let calls = 0;
  const lab = client(async () => {
    calls += 1;
    if (calls < 3) return { status: 503, body: "" };
    return { status: 200, body: '{"accepted":1,"duplicates":0}' };
  });
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 204,
    durationMs: 1,
  });
  await lab.flush(2000);
  assert.equal(calls, 3);
  assert.equal(lab.stats.accepted, 1);
  assert.equal(lab.stats.dropped, 0);
  await lab.close();
});

test("queue overflow drops the newest event", async () => {
  let release;
  let entered = false;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const lab = client(
    async () => {
      entered = true;
      await gate;
      return { status: 200, body: '{"accepted":1,"duplicates":0}' };
    },
    { maxQueue: 2 },
  );
  assert.equal(
    lab.recordHttp({ service: "orders-api", method: "GET", routeTemplate: "/health", statusCode: 200, durationMs: 1 }),
    true,
  );
  await waitFor(() => entered);
  assert.equal(
    lab.recordHttp({ service: "orders-api", method: "GET", routeTemplate: "/health", statusCode: 200, durationMs: 1 }),
    true,
  );
  assert.equal(
    lab.recordHttp({ service: "orders-api", method: "GET", routeTemplate: "/health", statusCode: 200, durationMs: 1 }),
    true,
  );
  assert.equal(
    lab.recordHttp({ service: "orders-api", method: "GET", routeTemplate: "/health", statusCode: 200, durationMs: 1 }),
    false,
  );
  assert.equal(lab.stats.dropped, 1);
  release();
  await lab.close(2000);
});

test("invalid routes are not sent and the wrapped error is unchanged", async () => {
  const calls = [];
  const lab = client(async (_url, body) => {
    calls.push(body);
    return ok();
  });
  assert.equal(
    lab.recordHttp({
      service: "orders-api",
      method: "GET",
      routeTemplate: "https://example.com/orders?token=secret",
      statusCode: 200,
      durationMs: 1,
    }),
    false,
  );
  assert.equal(calls.length, 0);
  const hostError = new Error("host failed");
  const wrapped = lab.instrumentFetch(async () => {
    throw hostError;
  }, { service: "orders-api", routeTemplate: "/health" });
  await assert.rejects(() => wrapped("https://upstream.test/health"), (error) => error === hostError);
  await lab.flush(2000);
  assert.equal(calls.length, 1);
  await lab.close();
});

test("sanitizeRoute removes queries and identifiers", () => {
  const route = sanitizeRoute(
    "https://user:pw@example.com/v1/orders/123e4567-e89b-12d3-a456-426614174000?token=abc",
  );
  assert.equal(route, "/v1/orders/{id}");
  assert.equal(route.includes("token"), false);
  assert.equal(route.includes("pw"), false);
});

test("sanitizeRoute root URL is server-valid", () => {
  assert.equal(sanitizeRoute("https://api.example.com/"), "/{root}");
  assert.equal(sanitizeRoute("https://api.example.com"), "/{root}");
  assert.equal(isValidRouteTemplate("/{root}"), true);
  assert.equal(isValidRouteTemplate("/"), false);
});

test("recordHttp rejects invalid route without queueing", async () => {
  const calls = [];
  const lab = client(async (url, body) => {
    calls.push(body);
    return ok();
  });
  assert.equal(
    lab.recordHttp({
      service: "orders-api",
      method: "GET",
      routeTemplate: "/",
      statusCode: 200,
      durationMs: 1,
    }),
    false,
  );
  assert.equal(
    lab.recordHttp({
      service: "orders-api",
      method: "GET",
      routeTemplate: "/orders/12345678",
      statusCode: 200,
      durationMs: 1,
    }),
    false,
  );
  assert.equal(lab.stats.rejected, 2);
  assert.equal(
    lab.recordHttp({
      service: "orders-api",
      method: "GET",
      routeTemplate: "/v1/orders/{id}",
      statusCode: 200,
      durationMs: 1,
    }),
    true,
  );
  await lab.flush(2000);
  assert.equal(lab.stats.accepted, 1);
  assert.equal(lab.stats.dropped, 0);
  assert.equal(calls.length, 1);
  await lab.close();
});

test("instrumentFetch root URL does not poison the batch", async () => {
  const calls = [];
  const lab = client(async (url, body) => {
    calls.push(JSON.parse(body));
    return {
      status: 200,
      body: JSON.stringify({ accepted: JSON.parse(body).events.length, duplicates: 0, results: [] }),
    };
  });
  const wrapped = lab.instrumentFetch(async () => new Response("ok", { status: 200 }), {
    service: "orders-api",
  });
  await wrapped("https://api.example.com/");
  assert.equal(
    lab.recordHttp({
      service: "orders-api",
      method: "GET",
      routeTemplate: "/v1/orders/{id}",
      statusCode: 200,
      durationMs: 1,
    }),
    true,
  );
  const result = await lab.close(2000);
  assert.equal(result.accepted, 2);
  assert.equal(result.dropped, 0);
  const routes = calls.flatMap((batch) => batch.events.map((event) => event.route_template));
  assert.deepEqual(routes.sort(), ["/{root}", "/v1/orders/{id}"].sort());
});

test("honors Retry-After seconds without consuming the retry budget", async () => {
  let calls = 0;
  const sleeps = [];
  const lab = client(
    async () => {
      calls += 1;
      if (calls === 1) {
        return { status: 429, body: '{"detail":"slow down"}', headers: { "Retry-After": "2" } };
      }
      return { status: 200, body: '{"accepted":1,"duplicates":0}' };
    },
    {
      sleep: async (ms) => {
        sleeps.push(ms);
      },
    },
  );
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 200,
    durationMs: 1,
  });
  const result = await lab.flush(2000);
  assert.equal(result.delivered, true);
  assert.equal(calls, 2);
  assert.deepEqual(sleeps, [2000]);
  assert.equal(lab.stats.accepted, 1);
  assert.equal(lab.stats.dropped, 0);
  assert.equal(lab.stats.rateLimited, 1);
  assert.equal(lab.stats.deliveryFailures, 0);
  await lab.close();
});

test("honors Retry-After HTTP-date and caps the wait", async () => {
  assert.equal(parseRetryAfterMs("2"), 2000);
  const future = new Date(Date.now() + 500_000).toUTCString();
  assert.ok(parseRetryAfterMs(future) >= 400_000);

  let calls = 0;
  const sleeps = [];
  const lab = client(
    async () => {
      calls += 1;
      if (calls === 1) {
        return { status: 429, body: "", headers: { "Retry-After": future } };
      }
      return { status: 200, body: '{"accepted":1,"duplicates":0}' };
    },
    {
      sleep: async (ms) => {
        sleeps.push(ms);
      },
    },
  );
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 200,
    durationMs: 1,
  });
  await lab.flush(2000);
  assert.equal(calls, 2);
  assert.deepEqual(sleeps, [MAX_RETRY_AFTER_MS]);
  assert.equal(lab.stats.rateLimited, 1);
  assert.equal(lab.stats.accepted, 1);
  await lab.close();
});

test("parseRetryAfterMs rejects junk and oversized digit strings", () => {
  assert.equal(parseRetryAfterMs("2"), 2000);
  assert.equal(parseRetryAfterMs("0"), 0);
  assert.equal(parseRetryAfterMs("-5"), null);
  assert.equal(parseRetryAfterMs("1.5"), null);
  assert.equal(parseRetryAfterMs("abc 2"), null);
  assert.equal(parseRetryAfterMs("²"), null);
  assert.equal(parseRetryAfterMs("1".repeat(11)), null);
  assert.equal(parseRetryAfterMs("1".repeat(400)), null);
  assert.equal(parseRetryAfterMs("not-a-date"), null);
});

test("repeated Retry-After eventually drops the batch", async () => {
  let calls = 0;
  const sleeps = [];
  const lab = client(
    async () => {
      calls += 1;
      return { status: 429, body: "", headers: { "Retry-After": "0" } };
    },
    {
      sleep: async (ms) => {
        sleeps.push(ms);
      },
    },
  );
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 200,
    durationMs: 1,
  });
  const result = await lab.flush(2000);
  assert.equal(calls, MAX_RATE_LIMITED_ATTEMPTS);
  assert.equal(sleeps.length, MAX_RATE_LIMITED_ATTEMPTS - 1);
  assert.ok(sleeps.every((ms) => ms === MIN_RETRY_AFTER_MS));
  assert.equal(lab.stats.dropped, 1);
  assert.equal(lab.stats.accepted, 0);
  assert.equal(lab.stats.rateLimited, MAX_RATE_LIMITED_ATTEMPTS);
  assert.equal(lab.stats.deliveryFailures, 1);
  assert.equal(result.lastError, "http_429");
  await lab.close();
});

test("close stops the Retry-After retry loop", async () => {
  let calls = 0;
  let resolveSleep;
  const firstSleep = new Promise((resolve) => {
    resolveSleep = resolve;
  });
  const lab = client(
    async () => {
      calls += 1;
      return { status: 429, body: "", headers: { "Retry-After": "60" } };
    },
    {
      sleep: async () => {
        await firstSleep;
      },
    },
  );
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 200,
    durationMs: 1,
  });
  await waitFor(() => calls >= 1);
  const closePromise = lab.close(500);
  resolveSleep();
  await closePromise;
  const callsAtClose = calls;
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(calls <= callsAtClose + 1);
  assert.ok(lab.stats.dropped >= 1);
});

test("429 without Retry-After keeps exponential backoff", async () => {
  let calls = 0;
  const sleeps = [];
  const lab = client(
    async () => {
      calls += 1;
      if (calls < 3) return { status: 429, body: "" };
      return { status: 200, body: '{"accepted":1,"duplicates":0}' };
    },
    {
      retryBackoffMs: 200,
      sleep: async (ms) => {
        sleeps.push(ms);
      },
    },
  );
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 200,
    durationMs: 1,
  });
  await lab.flush(2000);
  assert.equal(calls, 3);
  assert.deepEqual(sleeps, [200, 400]);
  assert.equal(lab.stats.accepted, 1);
  assert.equal(lab.stats.rateLimited, 0);
  await lab.close();
});

test("rejects an operator key and loads server environment", async () => {
  assert.throws(
    () =>
      new IntegrationLabClient({
        baseUrl: "http://127.0.0.1:8010",
        integrationId: INTEGRATION_ID,
        credential: "operator-key-not-an-ingestion-credential",
      }),
    IntegrationLabConfigError,
  );
  const calls = [];
  const lab = IntegrationLabClient.fromEnv(
    {
      INTEGRATIONLAB_BASE_URL: "http://127.0.0.1:8010",
      INTEGRATIONLAB_INTEGRATION_ID: INTEGRATION_ID,
      INTEGRATIONLAB_INGESTION_CREDENTIAL: CREDENTIAL,
    },
    {
      retryBackoffMs: 0,
      transport: async (_url, body) => {
        calls.push(body);
        return ok();
      },
    },
  );
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 200,
    durationMs: 1,
  });
  await lab.flush(2000);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].includes(CREDENTIAL), false);
  await lab.close();
});

test("delivers to a local HTTP server and preserves the upstream result", async () => {
  const received = [];
  const ingest = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      received.push({
        authorization: req.headers.authorization,
        body: Buffer.concat(chunks).toString("utf8"),
      });
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end('{"accepted":1,"duplicates":0}');
    });
  });
  await new Promise((resolve) => ingest.listen(0, "127.0.0.1", resolve));
  const address = ingest.address();
  const lab = new IntegrationLabClient({
    baseUrl: `http://127.0.0.1:${address.port}`,
    integrationId: INTEGRATION_ID,
    credential: CREDENTIAL,
    retryBackoffMs: 0,
    timeoutMs: 1000,
  });
  const upstream = http.createServer((req, res) => {
    if (req.url === "/fail") {
      res.writeHead(503);
      res.end("unavailable");
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end('{"ok":true}');
  });
  await new Promise((resolve) => upstream.listen(0, "127.0.0.1", resolve));
  const upstreamPort = upstream.address().port;
  try {
    const wrapped = lab.instrumentFetch(fetch, {
      service: "orders-api",
      routeTemplate: "/demo/{id}",
    });
    const success = await wrapped(`http://127.0.0.1:${upstreamPort}/ok`);
    assert.equal(success.status, 200);
    assert.equal(await success.text(), '{"ok":true}');
    const failure = await wrapped(`http://127.0.0.1:${upstreamPort}/fail`);
    assert.equal(failure.status, 503);
    await lab.flush(2000);
    assert.equal(received.length, 2);
    assert.equal(received[0].authorization, `Bearer ${CREDENTIAL}`);
    assert.equal(received[0].body.includes(CREDENTIAL), false);
    const categories = received
      .flatMap((item) => JSON.parse(item.body).events)
      .map((event) => event.error_category);
    assert.deepEqual(categories, [null, "http_server_error"]);
  } finally {
    await lab.close();
    ingest.close();
    upstream.close();
  }
});

test("close flushes a multi-batch queue", async () => {
  const calls = [];
  const lab = client(
    async (url, body) => {
      const n = JSON.parse(body).events.length;
      calls.push(n);
      return {
        status: 200,
        body: JSON.stringify({ accepted: n, duplicates: 0, results: [] }),
      };
    },
    { batchSize: 10 },
  );
  for (let i = 0; i < 25; i += 1) {
    assert.equal(
      lab.recordHttp({
        service: "orders-api",
        method: "GET",
        routeTemplate: "/health",
        statusCode: 200,
        durationMs: 1,
      }),
      true,
    );
  }
  const result = await lab.close(5000);
  assert.equal(result.accepted, 25);
  assert.equal(result.dropped, 0);
  assert.equal(lab.stats.dropped, 0);
  assert.equal(result.delivered, true);
  assert.deepEqual(calls, [10, 10, 5]);
});

test("close during Retry-After returns promptly", async () => {
  let calls = 0;
  const lab = client(async () => {
    calls += 1;
    return { status: 429, body: "", headers: { "Retry-After": "60" } };
  });
  lab.recordHttp({
    service: "orders-api",
    method: "GET",
    routeTemplate: "/health",
    statusCode: 200,
    durationMs: 1,
  });
  await waitFor(() => calls >= 1);
  const started = Date.now();
  await lab.close(2000);
  assert.ok(Date.now() - started < 2000);
  assert.ok(lab.stats.dropped >= 1);
});

test("warns once for plain HTTP to a non-loopback host", () => {
  const messages = [];
  const original = console.warn;
  console.warn = (message) => {
    messages.push(String(message));
  };
  try {
    client(ok, { baseUrl: "http://telemetry.example.com" });
    assert.equal(messages.length, 1);
    assert.match(messages[0], /plain HTTP/i);
  } finally {
    console.warn = original;
  }
});

test("does not warn for HTTPS or loopback HTTP", () => {
  const messages = [];
  const original = console.warn;
  console.warn = (message) => {
    messages.push(String(message));
  };
  try {
    client(ok, { baseUrl: "https://telemetry.example.com" });
    client(ok, { baseUrl: "http://127.0.0.1:8010" });
    client(ok, { baseUrl: "http://localhost:8010" });
    assert.equal(messages.length, 0);
  } finally {
    console.warn = original;
  }
});

function waitFor(predicate) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (predicate()) {
        clearInterval(timer);
        resolve();
      } else if (Date.now() - started > 2000) {
        clearInterval(timer);
        reject(new Error("timed out waiting"));
      }
    }, 5);
  });
}
