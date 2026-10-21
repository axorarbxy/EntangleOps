from __future__ import annotations
from app.config import settings

def sequence_available()->bool:
    if not settings.enable_sequence:return False
    try:import sequence  # noqa: F401
    except ImportError:return False
    return False
def cross_check_link(length_km:float,band:str)->dict:
    return {"available":False,"analytic_rate":0.0,"sequence_rate":None,"note":"Optional SeQUeNCe integration is not configured; analytic core remains available."}
