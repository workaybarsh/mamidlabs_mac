"""Make the repository root importable so tests can ``import mamidlabs``."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
