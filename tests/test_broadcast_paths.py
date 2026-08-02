"""Unit tests for the signed-PSBT path containment guard."""

import sys
from pathlib import Path

import pytest

from coldcard_panic_drain.broadcast.paths import signed_path_under_output


def test_accepts_simple_relative_path(tmp_path: Path):
    resolved = signed_path_under_output(tmp_path, "signed.psbt")
    assert resolved == (tmp_path / "signed.psbt").resolve()


def test_accepts_nested_relative_path(tmp_path: Path):
    resolved = signed_path_under_output(tmp_path, "psbts_signed/coin-1.psbt")
    assert resolved == (tmp_path / "psbts_signed" / "coin-1.psbt").resolve()


def test_rejects_empty_path(tmp_path: Path):
    with pytest.raises(ValueError, match="missing"):
        signed_path_under_output(tmp_path, "")


def test_rejects_whitespace_only_path(tmp_path: Path):
    with pytest.raises(ValueError, match="missing"):
        signed_path_under_output(tmp_path, "   ")


def test_rejects_absolute_path(tmp_path: Path):
    with pytest.raises(ValueError, match="relative"):
        signed_path_under_output(tmp_path, "/etc/passwd")


def test_rejects_dotdot_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="escapes"):
        signed_path_under_output(tmp_path, "../outside.psbt")


def test_rejects_nested_dotdot_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="escapes"):
        signed_path_under_output(tmp_path, "psbts_signed/../../outside.psbt")


def test_rejects_bare_parent_reference(tmp_path: Path):
    with pytest.raises(ValueError, match="escapes"):
        signed_path_under_output(tmp_path, "..")


def test_dot_resolves_to_output_dir_itself(tmp_path: Path):
    resolved = signed_path_under_output(tmp_path, ".")
    assert resolved == tmp_path.resolve()


def test_internal_dotdot_that_stays_inside_is_allowed(tmp_path: Path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    resolved = signed_path_under_output(tmp_path, "a/b/../signed.psbt")
    assert resolved == (tmp_path / "a" / "signed.psbt").resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin privileges on Windows")
def test_rejects_symlink_escaping_output_dir(tmp_path: Path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside_target = tmp_path / "outside.psbt"
    outside_target.write_bytes(b"psbt")
    (output_dir / "evil-link.psbt").symlink_to(outside_target)

    with pytest.raises(ValueError, match="escapes"):
        signed_path_under_output(output_dir, "evil-link.psbt")


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin privileges on Windows")
def test_rejects_symlinked_directory_escaping_output_dir(tmp_path: Path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "signed.psbt").write_bytes(b"psbt")
    (output_dir / "link-dir").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes"):
        signed_path_under_output(output_dir, "link-dir/signed.psbt")


def test_backslash_is_not_treated_as_separator_on_posix(tmp_path: Path):
    """On POSIX, a Windows-style traversal string is a literal filename, not an escape."""
    if sys.platform == "win32":
        pytest.skip("backslash is a path separator on Windows")
    resolved = signed_path_under_output(tmp_path, "..\\..\\evil.psbt")
    assert resolved == tmp_path.resolve() / "..\\..\\evil.psbt"
    assert resolved.parent == tmp_path.resolve()
