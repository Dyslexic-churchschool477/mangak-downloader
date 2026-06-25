"""Pytest configuration for the MangaK Downloader test suite."""
import sys
from pathlib import Path

# Add src/ to the Python path so `import mangak` works
_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_src))
