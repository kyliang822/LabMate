PYTHON ?= python3

.PHONY: migrate test-unit test-async check-local check-async check-security check
migrate:
	$(PYTHON) -m scripts.migrate

test-unit:
	$(PYTHON) -m pytest -q tests/unit

test-async:
	$(PYTHON) -m pytest -q tests/unit tests/integration

check-local:
	$(PYTHON) -m ruff check backend worker scripts tests ai_service mcp_server
	$(MAKE) test-unit PYTHON=$(PYTHON)
	npm --prefix web run build

check-async: check-local
	$(MAKE) test-async PYTHON=$(PYTHON)

check-security:
	$(PYTHON) -m scripts.check_security

# TEST-04 full-project gate must not succeed on a partial implementation.
check: check-async
	@echo 'BLOCKED: remaining business and AI contract/evaluation gates are not implemented.'
	@exit 1
