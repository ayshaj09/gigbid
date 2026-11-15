.PHONY: data data-inspect label-pool labels install dev api web e2e worker test lint eval eval-rag eval-decisions demo graphs snapshots seed openapi experiments
install:
	python -m pip install -e ".[dev,worker,experiments]"
	cd apps/web && npm install

dev api:
	uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && NEXT_PUBLIC_API_URL=$${NEXT_PUBLIC_API_URL:-http://localhost:8000} npm run dev

e2e:
	cd apps/web && npm run test:e2e

worker:
	python -m worker.main --loop

openapi:
	python -c "import json; from apps.api.main import app; json.dump(app.openapi(), open('apps/web/openapi.json','w'), indent=1)"
	cd apps/web && npm run gen:api

experiments:
	@echo "MODEL_PROFILE=open python -m evals.runners.architecture_compare --dataset $$DATASET --limit 50"
	@echo "MODEL_PROFILE=open python -m evals.runners.tool_granularity"
	@echo "python -m evals.runners.judge export --results <decision results json>  (then label, then calibrate)"
	@echo "python -m evals.runners.gigsim_outcomes --dataset $$DATASET ;  python -m evals.runners.ab_test --dataset $$DATASET"

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

data-inspect:
	python -m datapipe.inspect

data:
	python -m datapipe.build

label-pool:
	for p in ai_engineer web_fullstack data_analyst; do python -m datapipe.pool --persona $$p --n $${N:-30}; done

labels:
	for p in ai_engineer web_fullstack data_analyst; do python -m datapipe.apply_labels --persona $$p; done
