"""Tripwires for 06-01 Task 2: boundary-write call sites route through get_write_target.

TRIPWIRES ONLY — not the DATA-01 verification of record (gruvax-rh7)
--------------------------------------------------------------------
Every test in this module reads source text. Source containing (or lacking) the
right characters is fully compatible with the bug class this suite once claimed
to exclude: a route can inject ``Depends(get_write_target)`` and still pass
``profile_id=DEFAULT_PROFILE_UUID`` to the query, or follow a correctly scoped
write with a default-profile cache reload one line later. Both shipped green
under these greps (the round-4 bug-hunt default-profile family).

They are kept because they are cheap and catch one honest regression shape —
someone reintroducing a ``Depends(get_event_bus)`` injection wholesale — and for
no other reason. The DATA-01 verification of record is behavioural:

  - tests/integration/test_nondefault_profile_scoping.py — end-to-end writes
    bound to profiles that are NOT the default (gruvax-seh).
  - tests/integration/test_06_01_profile_scoped_writes.py — query-level
    two-profile effect assertions (what moved, what didn't, rowcounts).

Do not add new source-text assertions here; add behavioural coverage in the
files above instead.
"""

from __future__ import annotations

from pathlib import Path
import re


def _read_src(path: str) -> str:
    return Path(path).read_text()


ADMIN_FILES = {
    "cubes": "src/gruvax/api/admin/cubes.py",
    "segments": "src/gruvax/api/admin/segments.py",
    "import_": "src/gruvax/api/admin/import_.py",
    "history": "src/gruvax/api/admin/history.py",
    "editing": "src/gruvax/api/admin/editing.py",
}


class TestNoGetEventBusInWriteRoutes:
    """None of the admin write/editing files may inject Depends(get_event_bus)."""

    def test_cubes_no_get_event_bus(self) -> None:
        src = _read_src(ADMIN_FILES["cubes"])
        assert "Depends(get_event_bus)" not in src, (
            "cubes.py must not use Depends(get_event_bus) — use Depends(get_write_target)"
        )

    def test_segments_no_get_event_bus(self) -> None:
        src = _read_src(ADMIN_FILES["segments"])
        assert "Depends(get_event_bus)" not in src, (
            "segments.py must not use Depends(get_event_bus) — use Depends(get_write_target)"
        )

    def test_import_no_get_event_bus(self) -> None:
        src = _read_src(ADMIN_FILES["import_"])
        assert "Depends(get_event_bus)" not in src, (
            "import_.py must not use Depends(get_event_bus) — use Depends(get_write_target)"
        )

    def test_history_no_get_event_bus(self) -> None:
        src = _read_src(ADMIN_FILES["history"])
        assert "Depends(get_event_bus)" not in src, (
            "history.py must not use Depends(get_event_bus) — use Depends(get_write_target)"
        )

    def test_editing_no_get_event_bus(self) -> None:
        src = _read_src(ADMIN_FILES["editing"])
        assert "Depends(get_event_bus)" not in src, (
            "editing.py must not use Depends(get_event_bus) — use Depends(get_write_target)"
        )


class TestGetWriteTargetCount:
    """Each admin write/editing file must use Depends(get_write_target)."""

    def test_cubes_uses_get_write_target(self) -> None:
        src = _read_src(ADMIN_FILES["cubes"])
        count = src.count("Depends(get_write_target)")
        assert count >= 2, (
            f"cubes.py must have at least 2 Depends(get_write_target) calls "
            f"(put_cube_boundary + bulk_write_cubes), got {count}"
        )

    def test_segments_uses_get_write_target(self) -> None:
        src = _read_src(ADMIN_FILES["segments"])
        count = src.count("Depends(get_write_target)")
        assert count >= 2, (
            f"segments.py must have at least 2 Depends(get_write_target) calls "
            f"(put_bin_cut + insert_cut), got {count}"
        )

    def test_import_uses_get_write_target(self) -> None:
        src = _read_src(ADMIN_FILES["import_"])
        count = src.count("Depends(get_write_target)")
        assert count >= 1, (
            f"import_.py must have at least 1 Depends(get_write_target) call, got {count}"
        )

    def test_history_uses_get_write_target(self) -> None:
        src = _read_src(ADMIN_FILES["history"])
        count = src.count("Depends(get_write_target)")
        assert count >= 1, (
            f"history.py must have at least 1 Depends(get_write_target) call, got {count}"
        )

    def test_editing_uses_get_write_target(self) -> None:
        src = _read_src(ADMIN_FILES["editing"])
        count = src.count("Depends(get_write_target)")
        assert count >= 1, (
            f"editing.py must have at least 1 Depends(get_write_target) call, got {count}"
        )

    def test_total_get_write_target_count_at_least_7(self) -> None:
        total = sum(_read_src(p).count("Depends(get_write_target)") for p in ADMIN_FILES.values())
        assert total >= 7, (
            f"Total Depends(get_write_target) calls across admin files must be >= 7, got {total}"
        )


class TestBoundaryNotFoundPresent:
    """All write paths (excluding editing.py — no DB write) must raise boundary_not_found."""

    def test_cubes_has_boundary_not_found(self) -> None:
        src = _read_src(ADMIN_FILES["cubes"])
        assert "boundary_not_found" in src, (
            "cubes.py must raise boundary_not_found on 0-row writes (D-10)"
        )

    def test_segments_has_boundary_not_found(self) -> None:
        src = _read_src(ADMIN_FILES["segments"])
        assert "boundary_not_found" in src, (
            "segments.py must raise boundary_not_found on 0-row writes (D-10)"
        )

    def test_import_has_boundary_not_found(self) -> None:
        src = _read_src(ADMIN_FILES["import_"])
        assert "boundary_not_found" in src, (
            "import_.py must raise boundary_not_found on 0-row writes (D-10)"
        )

    def test_history_has_boundary_not_found(self) -> None:
        src = _read_src(ADMIN_FILES["history"])
        assert "boundary_not_found" in src, (
            "history.py must raise boundary_not_found on 0-row writes (D-10)"
        )


class TestProfileIdPassedToWriteCalls:
    """write_boundary calls in admin files must pass a resolved profile_id argument."""

    def _find_write_boundary_calls(self, src: str) -> list[str]:
        """Find all write_boundary(...) call patterns in src."""
        # Match multi-line calls
        return re.findall(
            r"await write_boundary\([^)]+\)",
            src,
            re.DOTALL,
        )

    def test_cubes_write_boundary_passes_profile_id(self) -> None:
        src = _read_src(ADMIN_FILES["cubes"])
        calls = self._find_write_boundary_calls(src)
        assert calls, "cubes.py must have at least one write_boundary call"
        for call in calls:
            assert "profile_id" in call, (
                f"write_boundary call in cubes.py must pass profile_id: {call[:120]}"
            )

    def test_segments_write_boundary_passes_profile_id(self) -> None:
        src = _read_src(ADMIN_FILES["segments"])
        calls = self._find_write_boundary_calls(src)
        assert calls, "segments.py must have at least one write_boundary call"
        for call in calls:
            assert "profile_id" in call, (
                f"write_boundary call in segments.py must pass profile_id: {call[:120]}"
            )

    def test_import_write_boundary_passes_profile_id(self) -> None:
        src = _read_src(ADMIN_FILES["import_"])
        calls = self._find_write_boundary_calls(src)
        assert calls, "import_.py must have at least one write_boundary call"
        for call in calls:
            assert "profile_id" in call, (
                f"write_boundary call in import_.py must pass profile_id: {call[:120]}"
            )

    def test_history_write_boundary_passes_profile_id(self) -> None:
        src = _read_src(ADMIN_FILES["history"])
        calls = self._find_write_boundary_calls(src)
        assert calls, "history.py must have at least one write_boundary call"
        for call in calls:
            assert "profile_id" in call, (
                f"write_boundary call in history.py must pass profile_id: {call[:120]}"
            )
