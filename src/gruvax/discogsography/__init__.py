"""DiscogsographyClient package — typed HTTP wrapper over the discogsography v2 API.

Exports (added by Plan 02 Task 1 and Task 3):
  - ``DiscogsographyClient``: async httpx wrapper with stamina retry semantics.
  - ``DiscogsographyError`` family: typed exceptions consumed by sync_profile.
  - ``redact_dscg_tokens``: structlog processor masking dscg_* PAT substrings.
"""
