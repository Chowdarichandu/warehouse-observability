.PHONY: install up demo live down reset seed types test e2e lint build verify load-test recovery-drill
PY := .venv/bin/python

install:
	python3 -m venv .venv
	.venv/bin/pip install -e './backend[dev]'
	cd frontend && npm ci --no-audit --no-fund

up demo live down reset seed:
	$(PY) scripts/stack.py $@

types:
	$(PY) scripts/openapi.py
	cd frontend && npm run types

test:
	$(PY) -m pytest tests/backend -q
	cd frontend && npm test

e2e:
	cd frontend && npm run e2e

lint:
	.venv/bin/ruff check backend/obs tests/backend scripts
	.venv/bin/ruff format --check backend/obs tests/backend scripts
	cd frontend && npm run lint

# Offline release gate used before opening a promotion record. It deliberately
# excludes AWS and staging-only checks; those remain explicit checklist items.
verify: lint test build
	$(PY) scripts/openapi.py
	git diff --exit-code -- backend/openapi.json frontend/src/api/generated.ts docs/api.md

build:
	cd frontend && npm run build

# Defaults target localhost. Pass reviewed tool flags through LOAD_ARGS.
load-test:
	$(PY) scripts/load_test.py $(LOAD_ARGS)

# Requires an explicit dedicated loopback OBS_DRILL_ADMIN_DSN.
recovery-drill:
	$(PY) scripts/recovery_drill.py --confirm-isolated
