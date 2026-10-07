# Requires uv (https://docs.astral.sh/uv/).
.PHONY: setup ingest status build analyze test lint

setup:
	uv sync

ingest:
	uv run nicu ingest ibge
	uv run nicu ingest cnes
	uv run nicu ingest sinasc

status:
	uv run nicu status

build:
	uv run nicu build

analyze:
	uv run nicu analyze

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .
