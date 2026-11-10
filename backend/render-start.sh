#!/bin/sh
# Single-service demo start for free-tier hosting (e.g. Render):
# migrate + seed, then run the demo ticker and alerter beside the API.
set -e
# This entry point hosts the public demo (mode=demo, local auth): let the
# login page's self-service reset issue a temporary password there, as its
# copy promises. The API still refuses this in live mode or with SSO.
export DEMO_UNSAFE_SELF_SERVICE_PASSWORD_RESET="${DEMO_UNSAFE_SELF_SERVICE_PASSWORD_RESET:-true}"
python -m obs.migrate
python -m obs.demo.seed
python -m obs.collector &
python -m obs.alerter &
exec uvicorn obs.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log
