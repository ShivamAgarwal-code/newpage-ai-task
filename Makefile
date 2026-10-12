# Meridian usage connector — one-touch dev commands.
# Windows users without make: the commands below map 1:1 to the README steps.

PY ?= python
SERVICE_PY ?= service/.venv/bin/python
PORT ?= 8000
ENV ?= prod

.PHONY: setup setup-service setup-connector test test-service test-connector \
        provision check serve demo clean

setup: setup-service setup-connector provision ## install everything + render manifests

setup-service:
	cd service && $(PY) -m venv .venv && .venv/bin/pip install -e ".[dev]"

setup-connector:
	cd connector && npm ci && npm run build

provision: ## render permissions + host configs for all environments
	$(PY) provisioning/render.py

check: ## CI gate: provisioning renders cleanly with no drift
	$(PY) provisioning/render.py --check

test: test-service test-connector check ## run the whole test suite + provisioning check

test-service:
	cd service && .venv/bin/pytest -q

test-connector:
	cd connector && npm run typecheck && npm test

serve: ## run the Part A service + admin page on :$(PORT)
	cd service && MERIDIAN_ENV=$(ENV) .venv/bin/uvicorn meridian_service.api:app --port $(PORT)

demo: ## print the Part B transcript (service must be running)
	cd connector && node scripts/transcript.mjs priya.nair@meridianls.example $(ENV)

clean:
	rm -rf connector/dist connector/node_modules service/.venv service/*.egg-info
	rm -f service/.capabilities.*.sqlite3
