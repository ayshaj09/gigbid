.PHONY: install dev test lint eval eval-rag eval-decisions demo graphs snapshots seed
install:
	python -m pip install -e ".[dev]"

dev:
	uvicorn apps.api.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check .

eval: eval-rag eval-decisions

eval-rag:
	python -m evals.runners.rag_eval --dataset $${DATASET:-fixtures} --variants all --ablate $${ABLATE:-v8_corrective}

eval-decisions:
	python -m evals.runners.decision_eval --dataset $${DATASET:-fixtures} --fail-on-thresholds

demo:
	python -m dev.demo

graphs:
	python -m dev.render_graphs

snapshots:
	UPDATE_SNAPSHOTS=1 pytest -q tests/contract && python dev/tools_table.py

seed:
	@echo "Fixtures live in data/fixtures; instructor personas go in data/personas/<persona>/"
