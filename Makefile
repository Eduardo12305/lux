.PHONY: setup run test lint format clean install

install:
	pip install -e ".[dev]"

setup: install
	@echo "Lux setup completo. Execute 'make run' para iniciar."

run:
	python -m lux.main

gateway:
	python -m lux.main --gateway

test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ -v --cov=lux --cov-report=term

lint:
	python -m ruff check lux/ tests/

format:
	python -m ruff format lux/ tests/

typecheck:
	python -m mypy lux/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache

services-up:
	docker-compose up -d qdrant redis

services-down:
	docker-compose down

doctor:
	python -m lux.main --doctor
