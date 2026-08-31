.PHONY: run test test-unit test-e2e eval ingest facts

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

# Optional: Coach answers fact questions without it, paying one Coveo call per
# Pokemon per process. ~1023 rate-limited calls, roughly four minutes.
facts:
	.venv/bin/python scripts/ingest/build_facts.py
