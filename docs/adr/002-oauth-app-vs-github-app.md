# ADR 002: GitHub OAuth App (not GitHub App)

## Context
We need user-level GitHub identity/scopes for a reliability console demo, not
installation-wide repository permissions.

## Decision
Use a **GitHub OAuth App** with state + PKCE, encrypt tokens at rest, and probe
with `GET /user`.

## Alternatives
- GitHub App (installations, webhooks, fine-grained repo access)
- Personal access tokens pasted into the UI

## Tradeoffs
+ Matches "connect my account" UX  
+ Smaller permission surface for this milestone  
− No installation webhooks or repo admin features
