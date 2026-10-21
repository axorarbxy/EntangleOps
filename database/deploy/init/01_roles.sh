#!/bin/sh
set -eu
OWNER_PW="$(cat /run/secrets/db_owner_password)"
APP_PW="$(cat /run/secrets/db_app_password)"
for pw in "$OWNER_PW" "$APP_PW"; do
  case "$pw" in *[!A-Za-z0-9_-]*|"") echo "database passwords must be URL-safe" >&2; exit 1;; esac
done
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE eo_owner LOGIN PASSWORD '${OWNER_PW}';
CREATE ROLE eo_app LOGIN PASSWORD '${APP_PW}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE entangleops OWNER eo_owner;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname entangleops <<SQL
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO eo_app;
SQL
