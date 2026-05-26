.PHONY: install example test lint clean

install:
	pip install -e ".[dev]"

example:
	python -m ai_visibility run \
		--name "Dra. Mariana Costa" \
		--specialty "Dermatologia" \
		--city "São Paulo" \
		--state "SP" \
		--neighborhood "Moema" \
		--output ./examples/dra_mariana_costa

test:
	pytest -v

clean:
	rm -rf .cache/ __pycache__/ *.egg-info/ .pytest_cache/ dist/ build/
