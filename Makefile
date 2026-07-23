.PHONY: init install test lint typecheck check api
init:
	python scripts/init_dirs.py
install:
	python -m pip install -e ".[dev]"
test:
	pytest
lint:
	ruff check .
typecheck:
	mypy src
check: test lint typecheck
api:
	uvicorn cleanroom.api.app:app --host 127.0.0.1 --port 8000
