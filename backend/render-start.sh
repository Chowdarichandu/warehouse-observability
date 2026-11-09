#!/bin/sh
# Single-service demo start for free-tier hosting (e.g. Render):
# migrate + seed, then run the demo ticker and alerter beside the API.
set -e
python -m obs.migrate
python -m obs.demo.seed
python -m obs.collector &
python -m obs.alerter &
exec uvicorn obs.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log
