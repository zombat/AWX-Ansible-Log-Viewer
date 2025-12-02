PY=python3
FILE?=example.log

.PHONY: install run dev clean

install:
	$(PY) -m pip install -r requirements.txt

run:
	$(PY) awx_log_view.py $(FILE)

dev:
	clear && $(PY) awx_log_view.py $(FILE)

clean:
	rm -rf __pycache__ debug.log .pytest_cache .venv
