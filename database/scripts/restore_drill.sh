#!/bin/sh
set -eu
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.db.yml"
mkdir -p backups
chmod 700 backups
DUMP="backups/entangleops-restore-drill.dump"
trap 'rm -f "$DUMP"; $COMPOSE exec -T db psql -U eo_admin -d postgres -c "DROP DATABASE IF EXISTS entangleops_restore" >/dev/null 2>&1 || true' EXIT
$COMPOSE exec -T db pg_dump -U eo_admin -Fc entangleops > "$DUMP"
chmod 600 "$DUMP"
$COMPOSE exec -T db psql -U eo_admin -d postgres -c "DROP DATABASE IF EXISTS entangleops_restore"
$COMPOSE exec -T db psql -U eo_admin -d postgres -c "CREATE DATABASE entangleops_restore OWNER eo_owner"
$COMPOSE exec -T db pg_restore -U eo_admin -d entangleops_restore < "$DUMP"
for table in api_keys runs audit_log; do
  source_count="$($COMPOSE exec -T db psql -U eo_admin -d entangleops -Atc "SELECT count(*) FROM $table")"
  restored_count="$($COMPOSE exec -T db psql -U eo_admin -d entangleops_restore -Atc "SELECT count(*) FROM $table")"
  test "$source_count" = "$restored_count"
done
$COMPOSE exec -T backend sh -c 'EO_DATABASE_URL=postgresql+psycopg://eo_app@db:5432/entangleops_restore python scripts/verify_audit.py'
printf 'Restore drill passed: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
