# Universal monitoring example

This directory is a separate application. It does not import IntegrationLab's frontend. It performs real HTTP calls against a local fixture and reports sanitized outcomes with the Python SDK.

The fixture is not GitHub, Stripe, or a customer service. It returns HTTP 200, HTTP 429, HTTP 500, and a hang that the client times out.

## Run the acceptance script

From this directory, with PostgreSQL available at the test database:

```bash
python accept.py
```

The script uses `TEST_DATABASE_URL` when set. Otherwise it uses:

`postgresql+psycopg://integrationlab:integrationlab@127.0.0.1:5432/integrationlab_test`

It refuses any database name that does not end in `_test`. It migrates that database, starts this branch's API on `127.0.0.1:8010`, and does not call the UI agent's API on port 8000.

Expected app output:

```text
GET /ok -> 200
GET /limited -> 429
GET /fail -> 500
GET /hang -> timeout
GET /ok -> 200
flush accepted=5 duplicates=0 dropped=0 rejected=0
```

Expected health: `degraded`, with 5 SDK-reported observations, 3 errors (`http_server_error`, `rate_limited`, `timeout`), `independently_verified: false`, and `p95_latency_ms: null` because the sample is smaller than 20. Provider request metrics for the integration stay at 0.

The local API is started with operator key `integrationlab-accept-operator-key`. The demo process does not receive that key. The ingestion credential is printed by IntegrationLab only in the create response inside the script and is not written to the demo output.

## Run the application by hand

1. Register `provider=instrumented_http` with the operator API.
2. Create an ingestion credential and keep the one-time secret.
3. Install the SDK from the repo:

```bash
python -m pip install -e ../../sdk/python
```

4. Export the server-side variables and point `DEMO_UPSTREAM` at the fixture:

```bash
export INTEGRATIONLAB_BASE_URL=http://127.0.0.1:8010
export INTEGRATIONLAB_INTEGRATION_ID=<integration-uuid>
export INTEGRATIONLAB_INGESTION_CREDENTIAL=ilk_v1_...
export INTEGRATIONLAB_ENVIRONMENT=local
python test_service.py &
export DEMO_UPSTREAM=http://127.0.0.1:<port-printed-by-the-fixture>
python app.py
```

`test_service.py` prints the port it bound. Do not put the ingestion credential in a shell history file you plan to share.
