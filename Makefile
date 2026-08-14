.DEFAULT_GOAL := help
.PHONY: help install check lint format types test parse clean

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies
	uv sync --all-extras

check: lint types test parse  ## Run every gate CI runs

lint:  ## Lint
	uv run ruff check .

format:  ## Format the codebase
	uv run ruff format .

types:  ## Type check
	uv run mypy

test:  ## Run the test suite
	uv run pytest -q

parse:  ## Parse kept's own specification
	uv run kept parse

clean:  ## Remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
