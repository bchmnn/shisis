.PHONY: format lint

lint:
	ruff check ./shisis
	pyright ./shisis
	mypy --check-untyped-defs ./shisis
	pylint ./shisis

format:
	isort ./shisis
	black ./shisis

