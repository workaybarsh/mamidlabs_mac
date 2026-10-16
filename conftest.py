"""Make the repository root importable so tests can ``import mamidlabs``.

The interface language is process-global (:mod:`mamidlabs.core.i18n`), so a test
that switches it must not leak into the next one; the autouse fixture below
resets it to the source language before and after every test.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def _default_language():
    from mamidlabs.core import i18n

    i18n.set_language(i18n.DEFAULT_LANGUAGE)
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)
