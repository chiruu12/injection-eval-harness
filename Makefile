PY := ./.venv/bin/python

.PHONY: setup fetch table test report clean

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

clean:
	rm -rf results/*.json
