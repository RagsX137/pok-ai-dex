.PHONY: run test test-unit test-e2e eval ingest

run:
	.venv/bin/python -m pokedex

test:
	.venv/bin/python -m pytest

test-unit:
	.venv/bin/python -m pytest tests/unit -v

test-e2e:
	.venv/bin/python -m pytest tests/e2e -v

eval:
	.venv/bin/python -m eval_harness run --label $(LABEL)

ingest:
	.venv/bin/python scripts/ingest/scrape_pokedex.py
	.venv/bin/python scripts/ingest/scrape_images.py
