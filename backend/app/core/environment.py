from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from app.config import ScenarioConfig
from app.core.physics import Conditions

@dataclass
class EnvTraces:
    dt_s:int; n_steps:int; traffic:dict[str,np.ndarray]; temp_c:dict[str,np.ndarray]; dtemp_dt:dict[str,np.ndarray]; wind_ms:dict[str,np.ndarray]
    def conditions(self,link_id:str,t:int)->Conditions:
        t=min(max(t,0),self.n_steps-1)
        return Conditions(float(self.traffic[link_id][t]),float(self.temp_c[link_id][t]),float(self.dtemp_dt[link_id][t]),float(self.wind_ms[link_id][t]))
    def trend(self,series:dict[str,np.ndarray],link_id:str,t:int,lag:int=5)->float:
        t=min(max(t,0),self.n_steps-1);return float(series[link_id][t]-series[link_id][max(t-lag,0)])

def _ou(rng:np.random.Generator,n:int,theta:float,sigma:float,dt_h:float)->np.ndarray:
    x=np.zeros(n)
    for i in range(1,n):x[i]=x[i-1]-theta*x[i-1]*dt_h+sigma*np.sqrt(dt_h)*rng.standard_normal()
    return x

def generate_env(link_ids:list[str],duration_h:float,dt_s:int,seed:int,sc:ScenarioConfig)->EnvTraces:
    rng=np.random.default_rng(seed);n=int(duration_h*3600/dt_s)
    if n<2:raise ValueError("duration must include at least two time steps")
    dt_h=dt_s/3600;t_h=np.arange(n)*dt_h;traffic={};temp={};dtemp={};wind={}
    for lid in link_ids:
        load=sc.traffic_base+sc.traffic_amp*np.cos(2*np.pi*(t_h-sc.traffic_peak_hour)/24)+.05*_ou(rng,n,2,.6,dt_h)
        for _ in range(sc.traffic_spike_count):
            start=int(rng.integers(0,max(n-1,1)));width=int(rng.integers(max(600//dt_s,1),max(1800//dt_s,2)));load[start:start+width]+=sc.traffic_spike_height
        traffic[lid]=np.clip(load,0,1)
        T=sc.temp_mean_c+rng.normal()+sc.temp_amp_c*np.cos(2*np.pi*(t_h-sc.temp_peak_hour)/24)+.5*_ou(rng,n,1,1,dt_h)
        v=sc.wind_base_ms+np.abs(_ou(rng,n,.8,2,dt_h))
        if sc.storm_enabled:
            w=sc.storm_duration_h/4;g=np.exp(-.5*((t_h-sc.storm_center_h)/w)**2)
            T=T-sc.storm_temp_drop_c*g;v=v+sc.storm_wind_peak_ms*g
        temp[lid]=T;dtemp[lid]=np.gradient(T,dt_h);wind[lid]=np.clip(v,0,None)
    return EnvTraces(dt_s,n,traffic,temp,dtemp,wind)
