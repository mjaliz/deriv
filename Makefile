.PHONY: run validate install-playwright

run:
	python pipeline.py

validate:
	python validate.py

install-playwright:
	python -m playwright install chromium
