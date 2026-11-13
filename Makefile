.DEFAULT_GOAL := help
.PHONY: help sync data test lint format demo clean

help:            ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

sync:            ## create .venv and install locked dependencies
	uv sync --locked

data:            ## regenerate the synthetic HR feeds and access export
	uv run iam-generate-data

test:            ## run the automated tests
	uv run pytest

lint:            ## lint + format check
	uv run ruff check .
	uv run ruff format --check .

format:          ## auto-fix lint and formatting
	uv run ruff check . --fix
	uv run ruff format .

demo: data       ## offline walk-through: day 0 -> day 30 -> access review -> remediation -> re-review
	rm -rf state out
	uv run iam-jml --hr-feed data/hr_feed_day0.csv  --as-of 2026-09-30 --apply
	uv run iam-jml --hr-feed data/hr_feed_day30.csv --as-of 2026-10-30 --apply
	uv run iam-access-review
	uv run iam-remediate
	uv run iam-access-review --access out/app_access_export_remediated.csv --out out/after

clean:           ## remove generated state and caches
	rm -rf state out .pytest_cache .ruff_cache
