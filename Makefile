PYTHON ?= python3

.PHONY: migrate test-async check-async check
migrate:
	$(PYTHON) -m scripts.migrate

test-async:
	$(PYTHON) -m pytest -q tests/unit/test_async_validation.py tests/integration/test_async_foundation.py

check-async:
	$(PYTHON) -m ruff check backend/app/main.py backend/app/async_tasks scripts tests/unit/test_async_validation.py tests/integration/test_async_foundation.py
	$(MAKE) test-async PYTHON=$(PYTHON)

# TEST-04 full-project gate must not succeed on a partial implementation.
check: check-async
	@echo 'BLOCKED: frontend/build, remaining business integration and AI contract gates are not implemented.'
	@exit 1
