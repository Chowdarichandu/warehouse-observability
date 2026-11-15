#!/bin/sh
# Single-service demo start for free-tier hosting (e.g. Render):
# migrate, start the API, then seed and run the demo ticker and alerter
# beside it. The API starts before the seed on purpose: seeding a fresh
# database takes minutes over the network, and the host healthcheck must
# pass while it runs (the health endpoint needs only the migrated
# schema; demo data fills in as the seed completes).
set -e
# This entry point hosts the public demo (mode=demo, local auth): let the
# login page's self-service reset issue a temporary password there, as its
# copy promises. The API still refuses this in live mode or with SSO.
export DEMO_UNSAFE_SELF_SERVICE_PASSWORD_RESET="${DEMO_UNSAFE_SELF_SERVICE_PASSWORD_RESET:-true}"
python -m obs.migrate
uvicorn obs.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log &
server_pid=$!
python -m obs.demo.seed
python -m obs.collector &
python -m obs.alerter &
wait "$server_pid"
