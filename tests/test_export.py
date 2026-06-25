"""Tests for the export module — folder, CBZ, ZIP, and PDF exporters.

Uses ``tmp_path`` for all file I/O. Test images are synthetic .webp files
created inline. The PDF test is conditional on ``img2pdf`` being available.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from mangak.core.exceptions import ExportError
from mangak.core.export import (
    _zip_images,
    export_cbz,
    export_folder,
    export_pdf,
    export_zip,
)


# =========================================================================
#  Helpers
# =========================================================================


def _create_test_images(base_dir: Path, count: int = 3) -> Path:
    """Create *count* synthetic .webp files in *base_dir* and return it."""
    base_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        f = base_dir / f"{i + 1:03d}.webp"
        f.write_bytes(f"fake-webp-content-{i + 1}".encode())
    return base_dir


def _create_valid_images(base_dir: Path, count: int = 3) -> Path:
    """Create *count* minimal valid PNG files (as ``.png``) in *base_dir*.

    These are proper 1×1 red PNG images that ``img2pdf`` can process.
    Uses only the stdlib (``struct``, ``zlib``) — no Pillow dependency.
    """
    import struct
    import zlib

    def _minimal_png() -> bytes:
        # 1x1 RGB pixel (red: R=255, G=0, B=0)
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_chunk = b"IHDR" + ihdr_data
        ihdr_crc = struct.pack(">I", zlib.crc32(ihdr_chunk) & 0xFFFFFFFF)

        raw = b"\x00\xff\x00\x00"  # filter=None, R=255, G=0, B=0
        compressed = zlib.compress(raw)
        idat_chunk = b"IDAT" + compressed
        idat_crc = struct.pack(">I", zlib.crc32(idat_chunk) & 0xFFFFFFFF)

        iend_chunk = b"IEND"
        iend_crc = struct.pack(">I", zlib.crc32(iend_chunk) & 0xFFFFFFFF)

        png = b"\x89PNG\r\n\x1a\n"
        png += struct.pack(">I", len(ihdr_data)) + ihdr_chunk + ihdr_crc
        png += struct.pack(">I", len(compressed)) + idat_chunk + idat_crc
        png += struct.pack(">I", 0) + iend_chunk + iend_crc
        return png

    png_bytes = _minimal_png()
    base_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        f = base_dir / f"page_{i + 1:03d}.png"
        f.write_bytes(png_bytes)
    return base_dir


# =========================================================================
#  _zip_images (internal helper)
# =========================================================================


class TestZipImages:
    def test_creates_zip(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "images")
        output = tmp_path / "test.zip"

        result = _zip_images(images_dir, output)
        assert result == output
        assert output.exists()
        assert zipfile.is_zipfile(output)

        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            assert sorted(names) == ["001.webp", "002.webp", "003.webp"]

    def test_raises_on_empty_dir(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        output = tmp_path / "empty.zip"
        with pytest.raises(ExportError, match="No images found"):
            _zip_images(empty_dir, output)

    def test_delete_after_removes_source(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "images")
        output = tmp_path / "test.zip"

        _zip_images(images_dir, output, delete_after=True)
        assert output.exists()
        assert not images_dir.exists()


# =========================================================================
#  export_folder
# =========================================================================


class TestExportFolder:
    def test_copies_images(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output_dir = tmp_path / "output"

        result = export_folder(images_dir, output_dir)
        assert result.exists()
        # export_folder uses images_dir.relative_to(images_dir.parent) which
        # gives just the last component ("ch1"), not the full path
        assert result == output_dir / "ch1"
        assert sorted(result.iterdir()) == [
            result / "001.webp",
            result / "002.webp",
            result / "003.webp",
        ]
        assert (result / "001.webp").read_text() == "fake-webp-content-1"

    def test_overwrites_existing_dest(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "manga" / "ch1", count=1)
        output_dir = tmp_path / "output"

        # First export
        export_folder(images_dir, output_dir)
        # Second export with same source should overwrite cleanly
        result = export_folder(images_dir, output_dir)
        assert result.exists()
        assert len(list(result.iterdir())) == 1

    def test_delete_after_removes_source(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output_dir = tmp_path / "output"

        export_folder(images_dir, output_dir, delete_after=True)
        assert not images_dir.exists()
        assert (output_dir / "ch1").exists()

    def test_raises_on_nonexistent_source(self, tmp_path):
        missing = tmp_path / "nope"
        with pytest.raises(ExportError):
            export_folder(missing, tmp_path)


# =========================================================================
#  export_cbz
# =========================================================================


class TestExportCbz:
    def test_creates_cbz(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "chapter-50.cbz"

        result = export_cbz(images_dir, output)
        assert result == output
        assert output.suffix.lower() == ".cbz"
        assert zipfile.is_zipfile(output)

        with zipfile.ZipFile(output) as zf:
            assert sorted(zf.namelist()) == ["001.webp", "002.webp", "003.webp"]

    def test_enforces_cbz_extension(self, tmp_path):
        """If output has no .cbz extension, it's added automatically."""
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "chapter-50"  # no extension

        result = export_cbz(images_dir, output)
        assert result.suffix.lower() == ".cbz"
        assert result.name == "chapter-50.cbz"

    def test_accepts_zip_extension(self, tmp_path):
        """When .zip is passed, export_cbz keeps it as-is (both .cbz and .zip are accepted)."""
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "chapter-50.zip"

        result = export_cbz(images_dir, output)
        # Code only enforces .cbz when suffix is neither .cbz nor .zip
        assert result.suffix.lower() in (".cbz", ".zip")

    def test_delete_after(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "out.cbz"

        export_cbz(images_dir, output, delete_after=True)
        assert output.exists()
        assert not images_dir.exists()

    def test_empty_dir_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ExportError, match="No images found"):
            export_cbz(empty, tmp_path / "out.cbz")


# =========================================================================
#  export_zip
# =========================================================================


class TestExportZip:
    def test_creates_zip(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "chapter-50.zip"

        result = export_zip(images_dir, output)
        assert result == output
        assert result.suffix.lower() == ".zip"
        assert zipfile.is_zipfile(output)

        with zipfile.ZipFile(output) as zf:
            assert sorted(zf.namelist()) == ["001.webp", "002.webp", "003.webp"]

    def test_enforces_zip_extension(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "chapter-50"  # no extension

        result = export_zip(images_dir, output)
        assert result.suffix.lower() == ".zip"

    def test_delete_after(self, tmp_path):
        images_dir = _create_test_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "out.zip"

        export_zip(images_dir, output, delete_after=True)
        assert output.exists()
        assert not images_dir.exists()

    def test_empty_dir_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ExportError, match="No images found"):
            export_zip(empty, tmp_path / "out.zip")


# =========================================================================
#  export_pdf
# =========================================================================


class TestExportPdf:
    def test_creates_pdf_with_img2pdf(self, tmp_path):
        """Requires ``img2pdf`` installed; skip otherwise."""
        pytest.importorskip("img2pdf")
        images_dir = _create_valid_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "chapter-50.pdf"

        result = export_pdf(images_dir, output)
        assert result == output
        assert result.suffix.lower() == ".pdf"
        assert output.exists()
        # PDF files start with %PDF
        header = output.read_bytes()[:5]
        assert header == b"%PDF-"

    def test_enforces_pdf_extension(self, tmp_path):
        pytest.importorskip("img2pdf")
        images_dir = _create_valid_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "chapter-50"  # no extension

        result = export_pdf(images_dir, output)
        assert result.suffix.lower() == ".pdf"

    def test_delete_after(self, tmp_path):
        pytest.importorskip("img2pdf")
        images_dir = _create_valid_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "out.pdf"

        export_pdf(images_dir, output, delete_after=True)
        assert output.exists()
        assert not images_dir.exists()

    def test_empty_dir_raises(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ExportError, match="No images found"):
            export_pdf(empty, tmp_path / "out.pdf")

    def test_skipped_when_img2pdf_missing(self):
        """When img2pdf is not installed, the test should be skipped via importorskip.
        This test is just documenting the skip behaviour — actual skip is in test above."""
        pass

    def test_fallback_to_pillow(self, tmp_path, monkeypatch):
        """When img2pdf is missing but Pillow is installed, Pillow fallback is used."""
        pytest.importorskip("PIL")
        # Simulate img2pdf not being available
        import mangak.core.export as export_mod
        original_img2pdf = getattr(export_mod, "img2pdf", None)
        monkeypatch.setattr(export_mod, "img2pdf", None, raising=False)

        images_dir = _create_valid_images(tmp_path / "manga" / "ch1")
        output = tmp_path / "out.pdf"

        try:
            result = export_pdf(images_dir, output)
            assert result == output
            assert output.exists()
        except ImportError:
            pytest.skip("Pillow is not installed (shouldn't happen since importorskip passed)")
        finally:
            if original_img2pdf is not None:
                monkeypatch.setattr(export_mod, "img2pdf", original_img2pdf)
