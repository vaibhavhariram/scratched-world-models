#!/usr/bin/env bash
# Run the P0.3 read-only audit against the select-only role. See prompts/P0.3a-db-audit.md.
#
# Never echoes the credential or any PG* value. Nothing secret reaches argv: a connection string
# passed as an argument is world-readable via `ps`, so the URL is decomposed into PG* environment
# variables and psql is invoked with no connection argument at all.
#
# Usage: scripts/run_db_audit.sh [outdir]     (default outdir: audit-output/)

set -euo pipefail
set +x                      # never trace: expansions below carry the password
umask 077                   # captured output is 0600

cd "$(dirname "$0")/.."
ENV_FILE="workers/.env"
OUTDIR="${1:-audit-output}"

[ -f "$ENV_FILE" ] || { echo "error: $ENV_FILE not found. See prompts/P0.3a-db-audit.md part A." >&2; exit 1; }

# Read ONLY the DATABASE_URL_RO key. Deliberately not `set -a; . workers/.env`: sourcing the whole
# file would also export DATABASE_URL, the write credential, into this process and every child.
RO_URL="$(sed -n 's/^[[:space:]]*DATABASE_URL_RO[[:space:]]*=[[:space:]]*//p' "$ENV_FILE" | head -n1)"
RO_URL="${RO_URL%\"}"; RO_URL="${RO_URL#\"}"; RO_URL="${RO_URL%\'}"; RO_URL="${RO_URL#\'}"

if [ -z "$RO_URL" ]; then
  echo "error: DATABASE_URL_RO is absent from $ENV_FILE." >&2
  echo "Not falling back to DATABASE_URL. Produce nothing and stop — see prompts/P0.3a-db-audit.md." >&2
  exit 1
fi

command -v psql >/dev/null 2>&1 || { echo "error: psql not installed (brew install libpq)." >&2; exit 1; }

# Decompose into PG* vars. Parsed with urllib so percent-encoded passwords survive intact.
# The assignments are eval'd from a command substitution and never printed.
eval "$(RO_URL="$RO_URL" python3 -c '
import os, shlex, sys
from urllib.parse import urlsplit, unquote
u = urlsplit(os.environ["RO_URL"])
if u.scheme not in ("postgres", "postgresql"):
    sys.stderr.write("error: DATABASE_URL_RO is not a postgres:// URL\n"); sys.exit(1)
out = {
    "PGHOST": u.hostname or "",
    "PGPORT": str(u.port or 5432),
    "PGUSER": unquote(u.username or ""),
    "PGPASSWORD": unquote(u.password or ""),
    "PGDATABASE": unquote((u.path or "/postgres").lstrip("/")) or "postgres",
}
for k, v in out.items():
    print("export %s=%s" % (k, shlex.quote(v)))
')"
unset RO_URL

mkdir -p "$OUTDIR"
echo "connecting as ${PGUSER} to ${PGHOST}:${PGPORT}/${PGDATABASE}"   # no password, by construction

# ON_ERROR_STOP=0: a permission error on one statement is recorded, not worked around (see the
# credential rules in prompts/P0.3a-db-audit.md). Migration state runs first — it certifies 003.
rc=0
for f in sql/audit/p0_migration_state.sql sql/audit/p0_db_state.sql; do
  out="$OUTDIR/$(basename "${f%.sql}").txt"
  echo "--- $f -> $out"
  psql -v ON_ERROR_STOP=0 -f "$f" > "$out" 2>&1 || rc=$?
done

unset PGPASSWORD
echo "done. output in $OUTDIR/ (mode 0600). rc=$rc"
echo "Paste these into AUDIT.md verbatim; do not summarise or infer."
exit "$rc"
