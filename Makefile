PY=python3
FILE?=example.log

.PHONY: install run dev clean

install:
	$(PY) -m pip install -e .

run:
	ansible-logviewer $(FILE)

dev:
	clear && $(PY) -m ansible_logviewer.cli $(FILE)

clean:
	rm -rf __pycache__ debug.log .pytest_cache .venv *.egg-info build dist
