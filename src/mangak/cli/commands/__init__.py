"""CLI command modules for the MangaK Downloader."""

from mangak.cli.commands.info import info_cmd
from mangak.cli.commands.search import search_cmd
from mangak.cli.commands.download import download_cmd
from mangak.cli.commands.history import history_cmd
from mangak.cli.commands.settings import settings_cmd

__all__ = [
    "info_cmd",
    "search_cmd",
    "download_cmd",
    "history_cmd",
    "settings_cmd",
]
