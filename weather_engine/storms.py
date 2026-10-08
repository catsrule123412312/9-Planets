"""Deterministic storm object diagnosis. No random event sampling."""
from dataclasses import dataclass
import numpy as np
@dataclass
class StormDiagnosis:
    convective: bool
    organized: bool
    rotating: bool
    severe: bool
    supercell: bool
    score: float
    kind: str

def diagnose_storm(cape,cin,shear,vorticity,convergence,lcl_m,precipitable_water,surface_temp_k):
    score=max(0,float(cape))/500 + max(0,float(shear))/8 + max(0,float(convergence))*3 + max(0,float(precipitable_water))*2
    conv=float(cape)>400 and float(convergence)>0.02 and float(precipitable_water)>20
    organized=conv and float(shear)>10
    rotating=organized and abs(float(vorticity))>0.00025
    severe=organized and float(cape)>1800 and float(shear)>17
    supercell=severe and rotating and float(lcl_m)<2200
    if supercell: kind='supercell'
    elif severe: kind='severe_thunderstorm'
    elif organized: kind='organized_thunderstorm'
    elif conv: kind='thunderstorm'
    else: kind='none'
    return StormDiagnosis(conv,organized,rotating,severe,supercell,score,kind)
def storm_intensity(s):
    if s.supercell:return 'violent'
    if s.severe:return 'severe'
    if s.organized:return 'heavy'
    if s.convective:return 'moderate'
    return 'none'
def downdraft_outflow(cape,precip): return np.clip(0.6*np.sqrt(np.maximum(cape,0))+1.5*np.sqrt(np.maximum(precip,0)),0,65)
def cold_pool_strength(precip,environmental_density=1.2): return np.maximum(0,np.asarray(precip,float))*0.65*np.asarray(environmental_density,float)
def gust_front_speed(cold_pool,depth): return np.sqrt(np.maximum(0,2*np.asarray(cold_pool)*np.maximum(np.asarray(depth),20)))
def storm_lifetime(cape,shear,moisture): return np.clip(240+0.08*np.asarray(cape)+8*np.asarray(shear)+4*np.asarray(moisture),120,7200)
def storm_radius(cape,depth): return np.clip(100+0.3*np.sqrt(np.maximum(cape,0))*np.sqrt(np.maximum(depth,100)),100,50000)
def lightning_flash_rate(cape,cloud_depth,precip): return np.maximum(0,0.004*(np.asarray(cape)-500)+0.8*np.asarray(cloud_depth)/1000+0.12*np.asarray(precip))
def storm_track_velocity(u,v,steering_depth=6000): return np.asarray(u,float)*0.8,np.asarray(v,float)*0.8
def storm_growth_rate(cape,moisture,shear): return 0.0002*np.maximum(cape,0)*(0.5+moisture)*(1+0.03*shear)
def storm_decay_rate(rain,cape): return 0.00002*np.maximum(rain,0)+0.000001*np.maximum(500-cape,0)
