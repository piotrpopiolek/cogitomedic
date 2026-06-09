"""Pytest hook for mutmut: prefer mutated sources under ``mutants/`` when present."""

from __future__ import annotations

import sys
from pathlib import Path

_here = Path(__file__).resolve()
if "mutants" in _here.parts:
    _mutants_root = _here.parents[2]
    _root_str = str(_mutants_root)
    if _root_str not in sys.path:
        sys.path.insert(0, _root_str)
