.PHONY: run test test-unit test-e2e eval lint

# NOTE: `python -m pokedex` does not exist until Task 9 of the reorg. Until
# then `make run` will fail with "No module named pokedex" — that failure is
# expected and is the reminder that Task 9 is unfinished. Use
# `.venv/bin/python app.py` to run the app in the meantime.
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
