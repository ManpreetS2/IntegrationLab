#!/bin/bash
# Runs once when the Postgres data volume is first initialized.
# Creates a dedicated test database so pytest never touches development data.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE integrationlab_test;
EOSQL
