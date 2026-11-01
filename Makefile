.PHONY: setup db test eval run clean

PY ?= python3
USER ?= E024
Q ?= What is the daily meal ceiling in London?

setup:
	$(PY) -m pip install -r requirements.txt
	$(MAKE) db

db:
	$(PY) scripts/build_db.py

test:
	$(PY) -m pytest -q

eval:
	$(PY) evals/runner.py

run:
	$(PY) cli.py --user $(USER) "$(Q)"

clean:
	rm -f EVAL_REPORT.md
	find . -name __pycache__ -type d -exec rm -rf {} +
