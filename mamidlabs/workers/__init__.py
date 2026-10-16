"""JSON stdin/stdout workers.

Each ``*.py`` file here keeps the one-shot contract from the Windows edition: one
JSON request on stdin, one JSON response on stdout. They are executed **as
scripts** by :class:`mamidlabs.core.runner.WorkerRunner` (some have hyphens in
their names, so they are never imported), each inside the virtual environment
that owns its dependencies (``app``, ``imagegen``, ``asr``, ``ocr``).

This ``__init__.py`` only exists so the directory is treated as package data
(the workers ship inside the installed package); nothing here is imported.
"""
