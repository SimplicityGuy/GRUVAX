"""Backward-compatible test import path for the canonical fake-discogsography factory.

Source of truth lives at ``src/gruvax/_internal/fake_discogsography.py`` (D-15 mandate:
ONE fake-discogsography FastAPI fixture). This shim exists so existing test imports
under ``tests.fixtures.fake_discogsography`` continue to resolve.
"""

from gruvax._internal.fake_discogsography import create_fake_app


__all__ = ["create_fake_app"]
