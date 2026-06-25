"""
MangaK Downloader — A manga downloader for mangak.io.

Two interfaces share this core library:
  - CLI (Typer + Rich) via ``mangak``
  - GUI (PyQt6) via ``mangak-gui`` or ``python -m mangak gui``

Core library exports (via ``from mangak import ...``):
  Manga, MangaKClient, Settings, DownloadQueue,
  export_folder, export_cbz, export_zip, export_pdf,
  DownloadDB, Colors
"""

from mangak.core import *

__version__ = "1.0.0"
