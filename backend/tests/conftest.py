from __future__ import annotations
from pathlib import Path
import sys

_root=Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:sys.path.insert(0,str(_root))
_backend=_root/"backend"
if str(_backend) not in sys.path:sys.path.insert(0,str(_backend))
