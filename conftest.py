# Repo-root conftest.py — anchors pytest rootdir to the repo root so that
# the `pythonpath = ["."]` setting in pyproject.toml applies consistently
# to every pytest run, making `from fixtures.synth_collection import ...`
# importable. This file intentionally has no fixtures — all shared fixtures
# live in tests/conftest.py.
