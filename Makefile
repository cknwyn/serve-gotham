.PHONY: install run seed test clean

install:
	py -m venv .venv
	.venv\Scripts\pip install -r requirements.txt

run:
	.venv\Scripts\uvicorn app.main:app --reload --port 8000

seed:
	.venv\Scripts\python -m app.seed

test:
	.venv\Scripts\pytest tests/ -v

clean:
	if exist *.db del /f *.db
	if exist .pytest_cache rmdir /s /q .pytest_cache
