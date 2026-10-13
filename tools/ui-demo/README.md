# UI showcase helper

`prepare_showcase.py` talks to a running IntegrationLab API. It does not modify
backend code, migrations, or Stripe verification.

It creates or reuses:

- Failure Lab simulations (explicitly simulated)
- Locally HMAC-signed synthetic Stripe test events (not Stripe infrastructure deliveries)
- One support case pinned to the simulated rate-limit run
- A Stripe diagnostic run when none exists yet

Required environment variables (never commit them):

- `OPERATOR_API_KEY`
- `STRIPE_WEBHOOK_SECRET`

See `docs/assets/portfolio/ui-redesign/DEMO_GUIDE.md` for the operator walkthrough.
