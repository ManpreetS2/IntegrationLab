COMPOSE := docker compose -f docker-compose.full.yml
OPERATOR_API_KEY ?= local-demo-operator-key-change-me

.PHONY: help compose-up compose-down smoke demo backend-test frontend-check terraform-check verify full-verify

help:
	@printf '%s\n' \
	  'IntegrationLab developer targets:' \
	  '  make compose-up      Build/start the full local Compose stack' \
	  '  make smoke           Boot the stack and run end-to-end smoke checks' \
	  '  make demo            Start the stack and populate deterministic demo data' \
	  '  make compose-down    Stop stack and remove local Compose volumes' \
	  '  make verify          Backend + frontend + Terraform static gates' \
	  '  make full-verify     Static gates plus the assembled-stack smoke test'

compose-up:
	OPERATOR_API_KEY="$(OPERATOR_API_KEY)" $(COMPOSE) up -d --build

compose-down:
	OPERATOR_API_KEY="$(OPERATOR_API_KEY)" $(COMPOSE) down -v --remove-orphans

smoke:
	@set -eu; \
	trap 'OPERATOR_API_KEY="$(OPERATOR_API_KEY)" $(COMPOSE) down -v --remove-orphans >/dev/null 2>&1 || true' EXIT; \
	OPERATOR_API_KEY="$(OPERATOR_API_KEY)" $(COMPOSE) up -d --build; \
	OPERATOR_API_KEY="$(OPERATOR_API_KEY)" python3 scripts/ci/full_stack_smoke.py

demo: compose-up
	OPERATOR_API_KEY="$(OPERATOR_API_KEY)" python3 scripts/demo/populate_demo.py
	@printf '%s\n' 'Local demo ready at http://localhost:8080'
	@printf '%s\n' 'Enter OPERATOR_API_KEY in the console unlock screen.'

backend-test:
	cd backend && pytest -q

frontend-check:
	cd frontend && npm run lint && VITE_API_URL= npm run build

terraform-check:
	cd infra/terraform && terraform fmt -check -recursive && terraform init -backend=false && terraform validate

verify: backend-test frontend-check terraform-check

full-verify: verify smoke
