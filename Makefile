PY := ./.venv/bin/python

.PHONY: setup fetch table test report verify lint format docker clean

setup:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[dev]"

fetch:
	$(PY) -m injection_eval.fetch

table:
	$(PY) -m injection_eval.run

report:
	$(PY) -m injection_eval.report

test:
	$(PY) -m pytest -q tests

verify:
	$(PY) scripts/check_determinism.py --regenerate --twice

lint:
	uvx ruff@0.9.4 check src tests scripts

format:
	uvx ruff@0.9.4 format src tests scripts
	uvx ruff@0.9.4 check --fix src tests scripts

docker:
	docker build -t injection-eval .
	docker run --rm -v "$$PWD/results:/app/results" \
		-v "$$HOME/.cache/huggingface:/root/.cache/huggingface" injection-eval

clean:
	rm -rf results/*.json
