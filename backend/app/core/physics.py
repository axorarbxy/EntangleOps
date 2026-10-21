from __future__ import annotations
import math
from dataclasses import dataclass

ALPHA_DB_PER_KM = {"C": 0.20, "O": 0.35}
RAMAN_K = {"C": 4e-3, "O": 1.5e-4}
W0, A_TEMP, A_WIND, BURIED_LOSS_PER_KM, SWAP_W, SWAP_P = 0.97, 0.020, 0.010, 0.0005, 0.98, 0.5
BANDS = ("C", "O")

@dataclass(frozen=True)
class LinkParams:
    link_id: str
    u: str
    v: str
    length_km: float
    aerial_fraction: float
    modes: int = 4
    source_rate_hz: float = 2000.0
    channels: int = 3

@dataclass(frozen=True)
class Conditions:
    traffic_load: float
    temp_c: float
    dtemp_dt_c_per_h: float
    wind_ms: float

def transmittance(length_km: float, band: str) -> float:
    if band not in BANDS: raise ValueError(f"unknown band: {band}")
    return 10.0 ** (-ALPHA_DB_PER_KM[band] * length_km / 10.0)

def snr_factor(length_km: float, band: str, load: float) -> float:
    eta=transmittance(length_km,band); noise=RAMAN_K[band]*max(load,0.0)*length_km
    return eta/(eta+noise)

def env_visibility(link: LinkParams, c: Conditions) -> float:
    aerial=link.length_km*link.aerial_fraction; buried=link.length_km-aerial
    penalty=(A_TEMP*abs(c.dtemp_dt_c_per_h)+A_WIND*max(c.wind_ms,0.0))*aerial/50+BURIED_LOSS_PER_KM*buried
    return math.exp(-penalty)

def link_werner(link: LinkParams, band: str, c: Conditions) -> float: return W0*snr_factor(link.length_km,band,c.traffic_load)*env_visibility(link,c)
def werner_to_fidelity(w: float) -> float: return 0.25+0.75*w
def fidelity_to_werner(f: float) -> float: return (f-0.25)/0.75
def link_fidelity(link: LinkParams, band: str, c: Conditions) -> float: return werner_to_fidelity(link_werner(link,band,c))
def link_rate(link: LinkParams, band: str) -> float: return link.source_rate_hz*transmittance(link.length_km,band)*link.modes

def path_metrics(hops: list[tuple[LinkParams,str,Conditions]]) -> tuple[float,float]:
    if not hops: raise ValueError("empty path")
    w=1.0; rate=float("inf")
    for link,band,cond in hops:
        w*=link_werner(link,band,cond); rate=min(rate,link_rate(link,band))
    return werner_to_fidelity(w*SWAP_W**(len(hops)-1)),rate*SWAP_P**(len(hops)-1)
