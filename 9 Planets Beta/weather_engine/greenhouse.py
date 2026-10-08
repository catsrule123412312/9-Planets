"""Deterministic greenhouse gas state and retention diagnostics."""
from dataclasses import dataclass
import numpy as np
from .radiation import gas_absorption_coefficient, water_vapor_optical_depth, cloud_optical_depth, aerosol_optical_depth
@dataclass
class GreenhouseRetention:
    total_optical_depth: np.ndarray
    retained_fraction: np.ndarray
    co2_component: np.ndarray
    ch4_component: np.ndarray
    n2o_component: np.ndarray
    water_component: np.ndarray
    cloud_component: np.ndarray
    aerosol_component: np.ndarray

def greenhouse_retention(co2_ppm,ch4_ppb,n2o_ppb,water_vapor,cloud_fraction,pressure_hpa):
    gas=gas_absorption_coefficient(co2_ppm,ch4_ppb,n2o_ppb,pressure_hpa)
    co2=gas*0.63; ch4=gas*0.25; n2o=gas*0.12
    water=water_vapor_optical_depth(water_vapor,pressure_hpa)
    cloud=cloud_optical_depth(cloud_fraction,np.zeros_like(cloud_fraction))
    aerosol=aerosol_optical_depth(0.15)
    tau=np.maximum(0,gas+water+cloud+aerosol)
    retained=1-np.exp(-tau)
    return GreenhouseRetention(tau,retained,co2,ch4,n2o,water,cloud,aerosol)

def forcing_co2_delta(co2_ppm,reference=280): return 5.35*np.log(np.maximum(np.asarray(co2_ppm,float),1)/reference)
def forcing_ch4_delta(ch4_ppb,reference=722): return 0.036*(np.sqrt(np.maximum(ch4_ppb,0))-np.sqrt(reference))
def forcing_n2o_delta(n2o_ppb,reference=270): return 0.12*(np.sqrt(np.maximum(n2o_ppb,0))-np.sqrt(reference))
def water_vapor_feedback(surface_temperature_k): return 0.055*np.exp(0.07*(np.asarray(surface_temperature_k,float)-288.15))
def greenhouse_emissivity(tau): return np.clip(1-np.exp(-np.maximum(np.asarray(tau,float),0)),0,0.98)
def infrared_window_fraction(tau): return np.clip(np.exp(-0.7*np.maximum(np.asarray(tau,float),0)),0,1)
def stratospheric_adjustment(co2_ppm): return 0.3*np.log(np.maximum(np.asarray(co2_ppm,float),1)/280)
def radiative_feedback_kernel(tau,T):
    T=np.maximum(np.asarray(T,float),150); tau=np.maximum(np.asarray(tau,float),0)
    return 4*5.670374419e-8*T**3*np.exp(-tau)
def gas_lifetime_sink(value,reference,lifetime_s,dt):
    value=np.asarray(value,float); ref=float(reference); f=np.exp(-max(float(dt),0)/max(float(lifetime_s),1)); return ref+(value-ref)*f

def methane_oxidation(ch4_ppb,dt): return np.maximum(0,np.asarray(ch4_ppb,float))*np.exp(-max(0,float(dt))/(9.0*365.25*86400))
def nitrous_sink(n2o_ppb,dt): return np.maximum(0,np.asarray(n2o_ppb,float))*np.exp(-max(0,float(dt))/(114*365.25*86400))
def co2_ocean_sink(co2_ppm,ocean_temperature_k,dt):
    thermal=np.exp(-0.045*(np.asarray(ocean_temperature_k,float)-288.15)); return np.maximum(0,np.asarray(co2_ppm,float))*np.exp(-0.000002*thermal*max(0,float(dt)))
def land_carbon_sink(co2_ppm,veg_fraction,soil_moisture,dt):
    sink=1e-8*np.asarray(veg_fraction,float)*np.clip(np.asarray(soil_moisture,float),0,1)*np.maximum(co2_ppm,0); return np.maximum(0,np.asarray(co2_ppm,float)-sink*max(0,float(dt)))
