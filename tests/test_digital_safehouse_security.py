"""Synthetic, offline regressions for the legacy DigitalSafehouse backup boundary.

These tests never touch the owner's Windows pilot, real data, or credentials.
"""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import zipfile

from project_guardian import digital_safehouse as mod


def setup(tmp_path):
    safehouse = mod.DigitalSafehouse(str(tmp_path / "encrypted"), str(tmp_path / "key"))
    document = tmp_path / "synthetic-secret.txt"
    document.write_text("Fictional private memory alpha", encoding="utf-8")
    return safehouse, document


def backup_files(tmp_path):
    return sorted(p.name for p in (tmp_path / "encrypted").iterdir())


def test_encrypted_backup_roundtrip_and_metadata_without_plaintext_archive(tmp_path):
    vault, data = setup(tmp_path)
    saved = vault.create_backup("sample", files=[str(data)], metadata={"origin": "synthetic"})
    assert saved and saved.endswith(".encrypted")
    assert Path(saved).is_file()
    assert b"Fictional private memory alpha" not in Path(saved).read_bytes()
    assert backup_files(tmp_path) == ["sample.encrypted"]
    assert vault.get_backup_metadata(saved) == {"origin": "synthetic"}
    assert backup_files(tmp_path) == ["sample.encrypted"]
    restored_dir = tmp_path / "restored"
    assert vault.restore_backup(saved, str(restored_dir)) is True
    assert (restored_dir / data.name).read_bytes() == data.read_bytes()
    assert backup_files(tmp_path) == ["sample.encrypted"]


def test_missing_encryption_dependency_fails_closed_without_creating_zip(tmp_path):
    vault, data = setup(tmp_path)
    with patch.object(mod, "CRYPTO_AVAILABLE", False):
        assert vault.create_backup("no-dependency", files=[str(data)]) is None
    with patch.object(vault, "_get_fernet", return_value=None):
        assert vault.create_backup("no-key", files=[str(data)]) is None
    assert backup_files(tmp_path) == []


def test_encryption_failure_leaves_no_zip_and_no_partial(tmp_path):
    vault, data = setup(tmp_path)
    class FailingCipher:
        def encrypt(self, payload):
            assert b"Fictional private memory alpha" in payload
            raise RuntimeError("synthetic encryption failure")
    with patch.object(vault, "_get_fernet", return_value=FailingCipher()):
        assert vault.create_backup("failure", files=[str(data)]) is None
    assert backup_files(tmp_path) == []


def test_encrypted_file_publish_failure_preserves_old_backup(tmp_path):
    vault, data = setup(tmp_path)
    old = vault.create_backup("same", files=[str(data)])
    old_bytes = Path(old).read_bytes()
    data.write_text("Fictional private memory revised", encoding="utf-8")
    with patch.object(mod.os, "replace", side_effect=PermissionError("synthetic Windows deny")):
        assert vault.create_backup("same", files=[str(data)]) is None
    assert Path(old).read_bytes() == old_bytes
    assert backup_files(tmp_path) == ["same.encrypted"]


def test_absent_duplicate_linked_and_oversized_sources_fail_closed(tmp_path):
    vault, data = setup(tmp_path)
    assert vault.create_backup("missing", files=[str(tmp_path / "missing.txt")]) is None
    assert vault.create_backup("duplicate", files=[str(data), str(data)]) is None
    assert vault.create_backup("../escape", files=[str(data)]) is None
    with patch.object(mod, "MAX_ARCHIVE_BYTES", 4):
        assert vault.create_backup("oversized", files=[str(data)]) is None
    assert backup_files(tmp_path) == []


def test_corrupt_ciphertext_does_not_leave_plaintext_zip_temp(tmp_path):
    vault, data = setup(tmp_path)
    bogus = tmp_path / "encrypted" / "broken.encrypted"
    bogus.write_bytes(b"not-valid-fernet")
    assert vault.restore_backup(str(bogus), str(tmp_path / "output")) is False
    assert vault.get_backup_metadata(str(bogus)) is None
    assert not (tmp_path / "encrypted" / "broken.zip.tmp").exists()
    assert backup_files(tmp_path) == ["broken.encrypted"]


def test_existing_plaintext_zip_is_read_only_legacy_compatible(tmp_path):
    vault, data = setup(tmp_path)
    legacy = tmp_path / "old.zip"
    with zipfile.ZipFile(legacy, "w") as archive:
        archive.writestr("synthetic.txt", "fictional old text")
        archive.writestr("_metadata.json", '{"legacy":true}')
    assert vault.get_backup_metadata(str(legacy)) == {"legacy": True}
    assert vault.restore_backup(str(legacy), str(tmp_path / "old-restored"))
    assert (tmp_path / "old-restored" / "synthetic.txt").read_text() == "fictional old text"
    assert backup_files(tmp_path) == []


def test_legacy_zip_traversal_and_duplicate_members_fail_without_writes(tmp_path):
    vault, _ = setup(tmp_path)
    for name, entries in (
        ("traversal", [("../escape.txt", "fictional")]),
        ("windows-separator", [("..\\escape.txt", "fictional")]),
        ("duplicate", [("same.txt", "a"), ("same.txt", "b")]),
    ):
        archive = tmp_path / (name + ".zip")
        with zipfile.ZipFile(archive, "w") as zipped:
            for path, text in entries:
                zipped.writestr(path, text)
        dest = tmp_path / ("out-" + name)
        assert vault.restore_backup(str(archive), str(dest)) is False
        assert not dest.exists()
    assert not (tmp_path / "escape.txt").exists()


def test_existing_restored_file_preserved_without_overwrite(tmp_path):
    vault, data = setup(tmp_path)
    saved = vault.create_backup("preserve", files=[str(data)])
    target = tmp_path / "out" / data.name
    target.parent.mkdir()
    target.write_text("Already on disk")
    assert vault.restore_backup(saved, str(target.parent), overwrite=False)
    assert target.read_text() == "Already on disk"
    assert vault.restore_backup(saved, str(target.parent), overwrite=True)
    assert target.read_bytes() == data.read_bytes()


def test_failed_key_read_does_not_replace_prior_key(tmp_path):
    vault, data = setup(tmp_path)
    key = tmp_path / "key"
    original = key.read_bytes()
    ordinary_open = open
    def fail_key(file, *args, **kwargs):
        if str(file) == str(key):
            raise PermissionError("synthetic access failure")
        return ordinary_open(file, *args, **kwargs)
    with patch("builtins.open", side_effect=fail_key):
        alternate = mod.DigitalSafehouse(str(tmp_path / "second"), str(key))
    assert alternate.encryption_key is None
    assert key.read_bytes() == original
    assert alternate.create_backup("key-read-error", files=[str(data)]) is None
