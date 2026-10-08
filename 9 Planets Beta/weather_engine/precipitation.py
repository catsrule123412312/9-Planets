"""Deterministic cloud water, phase change, precipitation, and runoff."""
import numpy as np

def condensation_tendency(rh,T,p,dt):
    sat=np.ones_like(np.asarray(rh,float)); deficit=np.maximum(0,np.asarray(rh,float)-sat); return -0.18*deficit/np.maximum(float(dt),1)
def cloud_water_production(cape,humidity,cloud_fraction): return np.maximum(0,0.0004*np.asarray(cape)*np.asarray(humidity)+0.02*np.asarray(cloud_fraction))
def autoconversion(cloud_water,threshold=0.001):
    c=np.maximum(np.asarray(cloud_water,float),0); return np.maximum(0,(c-threshold))*0.4
def accretion(rain,cloud_water): return 0.08*np.maximum(np.asarray(rain),0)*np.maximum(np.asarray(cloud_water),0)
def precipitation_rate(condensation,cloud_water,T,dt):
    base=np.maximum(0,np.asarray(cloud_water,float)*18+np.maximum(np.asarray(condensation,float),0)*1e4)
    snow=np.asarray(T,float)<273.15; return np.where(snow,base*0.72,base)
def rain_evaporation(rain,rh,T,depth):
    dry=np.maximum(0,1-np.asarray(rh,float)); warm=np.maximum(0,(np.asarray(T,float)-273.15)/25); return np.maximum(0,np.asarray(rain,float)*0.08*dry*warm*np.asarray(depth,float)/1000)
def snowfall_rate(precip,T): return np.where(np.asarray(T,float)<273.15,np.asarray(precip,float)*0.8,0)
def sleet_rate(precip,T):
    T=np.asarray(T,float); return np.where((T>=271.15)&(T<=275.15),np.asarray(precip,float)*0.15,0)
def freezing_rain_rate(precip,T_surface): return np.where(np.asarray(T_surface,float)<273.15,np.asarray(precip,float)*0.18,0)
def infiltration_rate(rain,soil_moisture): return np.maximum(0,np.asarray(rain,float)*(1-0.55*np.asarray(soil_moisture,float)))
def runoff_rate(rain,soil_moisture,slope): return np.maximum(0,np.asarray(rain,float)*np.clip(np.asarray(soil_moisture,float)-0.8,0,1)*(0.5+2*np.asarray(slope,float)))
def snowmelt_rate(T,radiation,snowpack): return np.maximum(0,np.asarray(T,float)-273.15)*0.8 + np.maximum(0,np.asarray(radiation,float))/180*0.5*np.asarray(snowpack,float)
def graupel_rate(cape,updraft,rain): return np.maximum(0,(np.asarray(cape)-1000)/1500)*np.asarray(updraft)*0.02*np.asarray(rain)
def hail_rate(cape,shear,freezing_level): return np.maximum(0,(np.asarray(cape)-1800)/1200)*np.maximum(np.asarray(shear)-12,0)*np.clip((5000-np.asarray(freezing_level))/5000,0,1)
def precipitable_water_from_column(rh,z): return float(np.trapz(np.clip(np.asarray(rh),0,1.2)*0.02,np.asarray(z))/9.80665)
def runoff_accumulator(old,runoff,dt): return np.maximum(0,np.asarray(old,float)+np.asarray(runoff,float)*max(float(dt),0))
