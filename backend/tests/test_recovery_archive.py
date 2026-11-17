"""The recovery container's Python3.11 must safely restore files without newer tar APIs."""
import io
from pathlib import Path
import sys
import tarfile
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from verify_restore import extract_backup

def archive_with(name, body=b'synthetic private file', link=False):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        item = tarfile.TarInfo(name)
        if link:
            item.type = tarfile.SYMTYPE
            item.linkname = '../../outside'
            archive.addfile(item)
        else:
            item.size = len(body)
            archive.addfile(item, io.BytesIO(body))
    buffer.seek(0)
    return tarfile.open(fileobj=buffer)

def test_private_files_restore_under_the_selected_directory(tmp_path):
    with archive_with('private_media/বাংলা.txt', 'Synthetic বাংলা'.encode()) as archive:
        extract_backup(archive, tmp_path / 'restore')
    assert (tmp_path / 'restore/private_media/বাংলা.txt').read_text() == 'Synthetic বাংলা'

def test_archive_cannot_write_outside_restore_directory(tmp_path):
    with archive_with('../outside.txt') as archive:
        with pytest.raises(ValueError):
            extract_backup(archive, tmp_path / 'restore')
    assert not (tmp_path / 'outside.txt').exists()

def test_archive_cannot_create_symlinks(tmp_path):
    with archive_with('private_media/link', link=True) as archive:
        with pytest.raises(ValueError):
            extract_backup(archive, tmp_path / 'restore')
    assert not (tmp_path / 'restore/private_media/link').exists()
