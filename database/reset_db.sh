#!/bin/bash
# Reset database for Compliance Screening System

# Default environment variables
export PGPASSWORD="${PGPASSWORD:-Vipul@#\$187}"
export PGUSER="${PGUSER:-postgres}"
export PGPORT="${PGPORT:-5432}"
export PGHOST="${PGHOST:-localhost}"

DB_NAME="compliance_screening"

# Standard paths for Windows PostgreSQL 18 installations (adjust if needed)
PSQL_CMD="psql"
DROPDB_CMD="dropdb"
CREATEDB_CMD="createdb"

if [ -f "/c/Program Files/PostgreSQL/18/bin/psql.exe" ]; then
    PSQL_CMD="/c/Program Files/PostgreSQL/18/bin/psql.exe"
    DROPDB_CMD="/c/Program Files/PostgreSQL/18/bin/dropdb.exe"
    CREATEDB_CMD="/c/Program Files/PostgreSQL/18/bin/createdb.exe"
elif [ -f "C:\\Program Files\\PostgreSQL\\18\\bin\\psql.exe" ]; then
    PSQL_CMD="C:\\Program Files\\PostgreSQL\\18\\bin\\psql.exe"
    DROPDB_CMD="C:\\Program Files\\PostgreSQL\\18\\bin\\dropdb.exe"
    CREATEDB_CMD="C:\\Program Files\\PostgreSQL\\18\\bin\\createdb.exe"
fi

echo "Dropping database ${DB_NAME}..."
"$DROPDB_CMD" --if-exists "$DB_NAME"

echo "Creating database ${DB_NAME}..."
"$CREATEDB_CMD" "$DB_NAME"

echo "Applying schema..."
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$PSQL_CMD" -d "$DB_NAME" -f "$DIR/schema_v1_draft.sql"

echo "Seeding data..."
"$PSQL_CMD" -d "$DB_NAME" -f "$DIR/seed_data.sql"

echo "Database reset complete."
