# ADR 004: CloudFront as the Single HTTPS Origin

## Context
The SPA and API should share one public URL for production demos without
managing a custom domain/ACM for the portfolio environment.

## Decision
CloudFront serves S3 (OAC) for static assets and routes `/api/*`, `/webhooks/*`,
`/health`, `/ready`, `/auth/operator` to an ALB origin with caching disabled.
Frontend builds with
`VITE_API_URL=""`.

## Alternatives
- Separate API subdomain + broad CORS
- Put the SPA on the ALB/nginx in ECS

## Tradeoffs
+ One origin; simpler CORS; edge HTTPS via default cert  
+ Must forward `Stripe-Signature` and raw body correctly  
− CloudFront→ALB is HTTP in the portfolio setup (not end-to-end TLS)
