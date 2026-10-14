from pathlib import Path

import pytest

from app import storage


PNG = b"\x89PNG\r\n\x1a\nminimal-test-image"


def test_validate_image_uses_magic_bytes(monkeypatch):
    monkeypatch.setenv("LAB_REPORT_MAX_IMAGE_BYTES", "32")
    assert storage.validate_image(PNG) == ("image/png", ".png")
    with pytest.raises(storage.InvalidImage):
        storage.validate_image(b"not an image")
    with pytest.raises(storage.InvalidImage):
        storage.validate_image(PNG + b"x" * 32)


def test_save_resolve_and_delete_original_image(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_REPORT_UPLOAD_DIR", str(tmp_path))
    image_url, mime = storage.save_original_image(PNG)
    filename = image_url.rsplit("/", 1)[-1]
    path, resolved_mime = storage.resolve_original_image(filename)
    assert mime == resolved_mime == "image/png"
    assert path is not None and path.read_bytes() == PNG
    assert Path(filename).stem != "minimal-test-image"
    assert storage.resolve_original_image("../secret.png") == (None, None)
    storage.delete_original_image(image_url)
    assert not path.exists()
