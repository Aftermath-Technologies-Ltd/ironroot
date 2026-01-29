# Contributing to IRONROOT

## Quality Rules

All code must pass:
- ruff (linting)
- black (formatting)
- mypy (type checking)
- pytest with 95%+ coverage

## Local Development

```bash
# install dev dependencies
pip install -e ".[dev]"

# run quality checks
ruff check src/ tests/
black --check src/ tests/
mypy src/

# run tests
pytest

# start services
./scripts/dev_up.sh
```

## Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

## Code Style

- Comments: lowercase, explain why not what
- Docstrings: concise purpose only
- Types: all public functions must have type hints
- Tests: part of the feature, not an afterthought
