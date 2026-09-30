#!/usr/bin/env bash
# Populate the IntegrationLab application secret in AWS Secrets Manager.
#
# Usage (values from the environment — never echoed):
#   export APP_SECRET_ARN=arn:aws:secretsmanager:...
#   export GITHUB_CLIENT_ID=...
#   export GITHUB_CLIENT_SECRET=...
#   export TOKEN_ENCRYPTION_KEY=...
#   export STRIPE_WEBHOOK_SECRET=...
#   ./scripts/aws/put-app-secrets.sh
#
# Or prompt interactively when a variable is unset.
#
# Never commit secret values. Never print them.

set -euo pipefail

if [[ -z "${APP_SECRET_ARN:-}" ]]; then
  echo "APP_SECRET_ARN is required (terraform output app_secret_arn)" >&2
  exit 1
fi

prompt_if_empty() {
  local var_name="$1"
  local prompt="$2"
  local silent="${3:-0}"
  if [[ -n "${!var_name:-}" ]]; then
    return 0
  fi
  if [[ "${silent}" == "1" ]]; then
    read -r -s -p "${prompt}: " value
    echo >&2
  else
    read -r -p "${prompt}: " value
  fi
  printf -v "${var_name}" '%s' "${value}"
}

prompt_if_empty GITHUB_CLIENT_ID "GITHUB_CLIENT_ID"
prompt_if_empty GITHUB_CLIENT_SECRET "GITHUB_CLIENT_SECRET" 1
prompt_if_empty TOKEN_ENCRYPTION_KEY "TOKEN_ENCRYPTION_KEY" 1
prompt_if_empty STRIPE_WEBHOOK_SECRET "STRIPE_WEBHOOK_SECRET" 1

TMP="$(mktemp)"
cleanup() { rm -f "${TMP}"; }
trap cleanup EXIT

export GITHUB_CLIENT_ID GITHUB_CLIENT_SECRET TOKEN_ENCRYPTION_KEY STRIPE_WEBHOOK_SECRET

# Write JSON without printing secret values to the terminal.
python3 - <<'PY' >"${TMP}"
import json
import os

payload = {
    "GITHUB_CLIENT_ID": os.environ["GITHUB_CLIENT_ID"],
    "GITHUB_CLIENT_SECRET": os.environ["GITHUB_CLIENT_SECRET"],
    "TOKEN_ENCRYPTION_KEY": os.environ["TOKEN_ENCRYPTION_KEY"],
    "STRIPE_WEBHOOK_SECRET": os.environ["STRIPE_WEBHOOK_SECRET"],
}
print(json.dumps(payload))
PY

aws secretsmanager put-secret-value \
  --secret-id "${APP_SECRET_ARN}" \
  --secret-string "file://${TMP}" \
  >/dev/null

echo "Updated secret ${APP_SECRET_ARN} (values not printed)."
