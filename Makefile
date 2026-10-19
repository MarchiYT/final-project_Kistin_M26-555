.PHONY: install run lint format build check update-rates test

install:
	uv sync

run:
	uv run project

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

build:
	uv build

check:
	uvx twine check dist/*

update-rates:
	uv run python -m valutatrade_hub.parser_service.scheduler

test:
	uv run python -m unittest discover -s tests -v
