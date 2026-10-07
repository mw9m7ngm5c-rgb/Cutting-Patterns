"""Sawing simulation engine.

Standalone: no web framework, no database, no file access. Everything is
driven by the plain dataclasses in :mod:`engine.model`.

Units inside the engine: millimetres across the log, millimetres along it
(integers, to keep length arithmetic exact). The dataclasses in
``model`` carry the units people type (cm, m, mm/m) and convert once.
"""
