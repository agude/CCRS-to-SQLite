# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog][keepachangelog], and this project
adheres to [Semantic Versioning][semver].

[keepachangelog]: https://keepachangelog.com/en/1.1.0/
[semver]: https://semver.org/spec/v2.0.0.html

## [Unreleased]

### Added

- Repo scaffolding: uv + hatchling packaging, ruff, mypy strict, pytest with
  a 90% coverage gate, a `justfile` holding the one definition of each
  check, a pre-commit hook that calls it, and CI over CPython 3.11–3.14 and
  PyPy.
- `ccrs_to_sqlite` console script with the argument surface from `plan.md`
  §5. Conversion itself is not implemented yet.
