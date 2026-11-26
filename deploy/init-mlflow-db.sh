#!/bin/sh
set -eu

if [ "$PGDATABASE" = "$MLFLOW_POSTGRES_DB" ]; then
    echo "MLflow must use a separate database from Atlas." >&2
    exit 1
fi

psql --no-psqlrc --set=ON_ERROR_STOP=1 --set=mlflow_db="$MLFLOW_POSTGRES_DB" <<'SQL'
SELECT format('CREATE DATABASE %I', :'mlflow_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'mlflow_db') \gexec
SQL
