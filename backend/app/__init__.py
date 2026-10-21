from __future__ import annotations
from pathlib import Path
import sys

_HERE=Path(__file__).resolve()
for _package in ("security","monitoring"):
    for _candidate in (_HERE.parents[1]/_package,_HERE.parents[2]/_package):
        if _candidate.is_dir():
            _parent=str(_candidate.parent)
            if _parent not in sys.path:sys.path.insert(0,_parent)
            break
