"""
Export downloaded images to various formats.

Supported formats:
  - ``folder`` — Raw .webp images in a directory
  - ``cbz`` — ZIP archive with .cbz extension (Comic Book ZIP)
  - ``zip`` — Standard ZIP archive
  - ``pdf`` — Lossless PDF via img2pdf (Pillow pipeline fallback)
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from mangak.core.exceptions import ExportError


def export_folder(
    images_dir: Path,
    output_dir: Path,
    delete_after: bool = False,
) -> Path:
    """
    Export images by copying the entire *images_dir* to *output_dir*.

    The output directory structure preserves ``{manga_slug}/{chapter_slug}/``.

    Returns the path to the exported directory.
    """
    try:
        dest = output_dir / images_dir.relative_to(images_dir.parent)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(images_dir, dest)
    except (OSError, ValueError) as exc:
        raise ExportError(f"Folder export failed: {exc}") from exc

    if delete_after:
        shutil.rmtree(images_dir, ignore_errors=True)

    return dest


def export_cbz(
    images_dir: Path,
    output_path: Path,
    delete_after: bool = False,
) -> Path:
    """
    Compress images into a Comic Book ZIP (.cbz) archive.

    *output_path* should have the ``.cbz`` extension (it is enforced).

    Returns the path to the created archive.
    """
    if output_path.suffix.lower() not in (".cbz", ".zip"):
        output_path = output_path.with_suffix(".cbz")

    return _zip_images(images_dir, output_path, delete_after)


def export_zip(
    images_dir: Path,
    output_path: Path,
    delete_after: bool = False,
) -> Path:
    """
    Compress images into a standard ZIP archive.

    *output_path* should have the ``.zip`` extension (it is enforced).

    Returns the path to the created archive.
    """
    if output_path.suffix.lower() != ".zip":
        output_path = output_path.with_suffix(".zip")

    return _zip_images(images_dir, output_path, delete_after)


def export_pdf(
    images_dir: Path,
    output_path: Path,
    delete_after: bool = False,
    progress_callback=None,
) -> Path:
    """
    Create a PDF from the images in *images_dir*.

    Each page is fitted to the image dimensions so there's no white border.
    Uses ``img2pdf`` (preferred) with a ``Pillow`` fallback pipeline.

    *progress_callback* is called as ``f(current, total)`` after each image.
    """
    if output_path.suffix.lower() != ".pdf":
        output_path = output_path.with_suffix(".pdf")

    images = sorted(images_dir.iterdir())

    if not images:
        raise ExportError("No images found to export to PDF")

    try:
        import img2pdf

        # Pass file paths directly — img2pdf reads dimensions and creates
        # one page per image sized exactly to the image (no white borders)
        pdf_data = img2pdf.convert(
            [str(p) for p in images],
        )
        output_path.write_bytes(pdf_data)

    except ImportError:
        # Fallback: Pillow pipeline
        try:
            from PIL import Image

            first = None
            extra_images = []
            for img_path in images:
                try:
                    im = Image.open(img_path).convert("RGB")
                    if first is None:
                        first = im
                    else:
                        extra_images.append(im)
                except Exception as exc:
                    raise ExportError(
                        f"Pillow failed to open {img_path}: {exc}"
                    ) from exc

            if first is None:
                raise ExportError("No valid images found for PDF export")

            first.save(
                str(output_path),
                save_all=True,
                append_images=extra_images,
                format="PDF",
            )
        except ImportError as exc:
            raise ExportError(
                "PDF export requires either 'img2pdf' or 'Pillow'. "
                f"Neither is available: {exc}"
            ) from exc

    except Exception as exc:
        raise ExportError(f"PDF export failed: {exc}") from exc

    if delete_after:
        shutil.rmtree(images_dir, ignore_errors=True)

    return output_path


# ──────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────


def _zip_images(
    images_dir: Path,
    output_path: Path,
    delete_after: bool = False,
) -> Path:
    """Compress images from *images_dir* into a ZIP archive at *output_path*."""
    images = sorted(images_dir.iterdir())

    if not images:
        raise ExportError("No images found to archive")

    try:
        with zipfile.ZipFile(
            str(output_path), "w", zipfile.ZIP_DEFLATED
        ) as zf:
            for img_path in images:
                arcname = img_path.name
                zf.write(str(img_path), arcname=arcname)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ExportError(f"ZIP/CBZ export failed: {exc}") from exc

    if delete_after:
        shutil.rmtree(images_dir, ignore_errors=True)

    return output_path
