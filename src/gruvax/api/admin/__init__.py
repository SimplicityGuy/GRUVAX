"""Admin API sub-package for GRUVAX.

Provides the ``create_admin_router()`` factory imported by ``app.py``.
Routers are imported inside the factory function (not at module level) to
mirror the circular-import guard pattern established in ``app.py``.
"""
