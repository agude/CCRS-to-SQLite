# Task runner for ccrs_to_sqlite. See the project-standards skill for the verb
# contract: lint is read-only and total, format is its mutating twin, and
# check is the full gate that CI runs.

# Default: list available recipes
default:
    @just --list

# Install dependencies
sync:
    uv sync --dev

# All read-only static checks
lint:
    uv run ruff check .
    uv run ruff format --check .

# Apply formatting and safe lint fixes
format:
    uv run ruff format .
    uv run ruff check --fix .

# Type check
# New repos: include tests/. Migrating an existing repo: start with the
# package alone — widening to tests usually surfaces real errors that
# belong in their own change.
type-check:
    uv run mypy src/ccrs_to_sqlite/ tests/

# Run tests
test *args:
    uv run pytest -vv {{ args }}

# Everything CI runs
check: lint type-check test

# Rewrite the checked-in DDL snapshot after a deliberate schema change. The
# diff it produces is the review; nothing else in the suite catches a rename.
schema-snapshot:
    uv run python -c "import sys; sys.path.insert(0, 'tests'); \
      from test_schema import SCHEMA_SNAPSHOT, rendered_schema; \
      SCHEMA_SNAPSHOT.write_text(rendered_schema(), encoding='utf-8')"
    @echo "Wrote tests/data/schema.sql. Review the diff before committing."

# Build the package
build:
    uv build

# Remove build and cache artifacts
clean:
    rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache .mypy_cache

# Install the pre-commit hook into this clone
hooks-install:
    @mkdir -p .git/hooks
    @cp bin/pre-commit.sh .git/hooks/pre-commit
    @chmod +x .git/hooks/pre-commit
    @echo "Pre-commit hook installed."
