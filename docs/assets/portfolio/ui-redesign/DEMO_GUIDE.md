# IntegrationLab local demo

Use this on branch `feat/final-ui-ux-polish`. The console is the real React app, FastAPI API, and PostgreSQL database. It is not a mock.

Another worktree may be building Universal Monitoring v2. Do not start a second Compose stack. This repo hard-codes container names (`integrationlab-full-*`) and binds `127.0.0.1:8080` and `127.0.0.1:8000`.

## 1. What you need

- Docker Desktop (or another Docker engine) with Compose v2
- A browser
- This git checkout

Node and Python on the host are only needed if you rebuild the frontend or rerun the showcase script. The running containers already include the app.

## 2. The stack that is already running

From this directory the full stack is up:

- Frontend: http://localhost:8080
- API: http://127.0.0.1:8000
- Postgres data volume is kept. Do not run `make compose-down` or `docker compose down -v`.

If the containers are stopped, start them again **without deleting volumes**:

```bash
docker compose -f docker-compose.full.yml up -d
```

`make demo` is safe only when this is the only IntegrationLab Compose project. It rebuilds and then runs `scripts/demo/populate_demo.py`. It does not remove volumes. Prefer the showcase command below if the stack is already up.

## 3. Open the app

http://localhost:8080

## 4. Unlock

The operator key is the `OPERATOR_API_KEY` already loaded in the backend container. Print it locally (do not commit it):

```bash
docker compose -f docker-compose.full.yml exec backend printenv OPERATOR_API_KEY
```

Paste that value into **Unlock console**. It stays in this tab's session storage only.

## 5. Refresh showcase data

This is idempotent. Failure Lab scenarios that already exist are skipped. Stripe event ids are stable, so a second run is recorded as a duplicate delivery.

```bash
export OPERATOR_API_KEY="$(docker compose -f docker-compose.full.yml exec -T backend printenv OPERATOR_API_KEY | tr -d '\r')"
export STRIPE_WEBHOOK_SECRET="$(docker compose -f docker-compose.full.yml exec -T backend printenv STRIPE_WEBHOOK_SECRET | tr -d '\r')"
python3 tools/ui-demo/prepare_showcase.py
```

Requires `STRIPE_WEBHOOK_SECRET` to be set on the running backend. The script signs payloads with that secret and posts them to the real webhook endpoint. These are **locally signed synthetic test events**, not deliveries from Stripe's infrastructure.

## 6. Five-minute walkthrough

1. **Overview** (`#/overview`) — Stripe Billing Sandbox should be **Degraded** because of the failed webhook queue. GitHub cards stay **Not configured**. The page states that simulated failures do not change live health.
2. **Failures** (`#/failures`) — Open Failure Lab, choose **429 Rate Limited** on GitHub Developer Integration, and open a recent run (or click **Run Simulation**). The result says latency is simulated. Live GitHub health stays not-configured.
3. **Webhooks** (`#/webhooks`) — Counters show received, processed, failed, and duplicate deliveries. Open `pi_ui_showcase_usd_2400` (delivery count 2, Processed). Scroll to **Failed events** for `webhook_invalid_event_data` with Retry and Dismiss. Do not Dismiss if you still want that row in the queue.
4. **Diagnostics** (`#/diagnostics`) — Select **Stripe Billing Sandbox**. Review current health, the previous run, and checks. Stripe diagnostics read stored webhook evidence. They do not call Stripe. Avoid **Run diagnostics** on GitHub unless you intend a real `GET /user` after OAuth is connected.
5. **Support Cases** (`#/support?case=5d87a075-5475-4a47-ab5f-829db136f2ec`) — **CASE-00007** is pinned to a Failure Lab rate-limit run and labeled simulated. The timeline separates when the evidence occurred from when it was pinned.

Then look at **Requests** with Source = **Simulated only**, and **Audit** for `support_case_created` / `diagnostic_started`.

## 7. What to expect

| Page | What you should see |
|------|---------------------|
| Overview | Degraded Stripe card, unconnected GitHub, database reachable |
| Integrations | Connect GitHub buttons, Stripe endpoint, verification **Configured**, no signing secret |
| Requests, Real only | Empty, unless you have completed GitHub OAuth |
| Requests, Simulated only | Rows badged **Simulated** (401, 429, 500, timeout) |
| Webhooks | Locally signed events, duplicate count, processed and failed badges |
| Failures | Deterministic diagnosis; simulated latency called out |
| Diagnostics | Stripe checks from stored evidence |
| Support | CASE-00007 note, timeline, simulated evidence |
| Audit | Operator actions with correlation ids, no payloads |

Creating a support case with an empty title is blocked by the required-field check.

## 8. What is simulated or synthetic

- **Failure Lab / Requests "Simulated"** — application-generated simulations. Not GitHub traffic.
- **Stripe webhook rows** — HMAC-signed on this machine with the local webhook secret, then verified by the real receiver. Not Stripe CLI or Stripe infrastructure deliveries.
- **Support case CASE-00007** — created by the app and pinned to the simulated 429 run.
- **Audit rows** — real records of those local operator actions.
- **GitHub "Not connected"** — no OAuth credential. No real provider request was invented.

## 9. Mobile layout

In the browser device toolbar use about **390×844**. Under 1024px the sidebar becomes a menu button. Open it and confirm Overview stays the current item. Tables scroll inside their own containers.

## 10. Stop without deleting the database

```bash
docker compose -f docker-compose.full.yml stop
```

Do **not** use `make compose-down` or `docker compose down -v`. Those remove the Postgres volume.

## 11. Start again

```bash
docker compose -f docker-compose.full.yml start
```

If a container is missing:

```bash
docker compose -f docker-compose.full.yml up -d
```

Unlock again with the same operator key. Showcase data remains in Postgres.

## 12. What you cannot test without provider credentials

- GitHub OAuth (**Connect GitHub**) and real rows on Requests → Real only
- A webhook that Stripe's own infrastructure signed (`stripe listen` / Dashboard)

Local signing and Failure Lab do not require those accounts.

## 13. Universal Monitoring v2

That work is on a separate branch and is not in this UI. After it is integrated, new monitoring surfaces would show up as additional navigation and pages. This demo does not invent those screens.
