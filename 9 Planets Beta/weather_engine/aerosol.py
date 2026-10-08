"""Deterministic aerosol and dust transport/settling."""
import numpy as np

def aerosol_optics(index):
    x=np.maximum(np.asarray(index,float),0); return {"aod":0.15*x,"single_scatter_albedo":np.clip(0.92-0.03*x,0.65,0.98),"absorption":0.02*x}
def dust_emission(soil_dryness,wind_speed,vegetation_fraction):
    dry=np.clip(1-np.asarray(soil_dryness,float),0,1); wind=np.maximum(np.asarray(wind_speed,float),0); veg=np.clip(np.asarray(vegetation_fraction,float),0,1)
    return np.maximum(0,0.012*dry*np.maximum(wind-4,0)**2*(1-veg)**1.7)
def dust_settling(column,dt,settling_speed=0.006): return np.maximum(0,np.asarray(column,float)*np.exp(-settling_speed*max(float(dt),0)/1000))
def dust_washout(column,rain_rate,dt):
    wash=1-np.exp(-0.002*np.maximum(np.asarray(rain_rate,float),0)*max(float(dt),0)); return np.maximum(0,np.asarray(column,float)*(1-wash))
def dust_visibility(aerosol_index): return np.exp(-0.7*np.maximum(np.asarray(aerosol_index,float),0))
def dust_solar_dimming(toa,aerosol_index,mu): return np.asarray(toa,float)*np.exp(-0.25*np.maximum(np.asarray(aerosol_index,float),0)/np.maximum(np.asarray(mu,float),0.1))
def dust_albedo_increment(dust_loading,snow_fraction): return 0.08*np.clip(np.asarray(dust_loading,float),0,4)*np.clip(np.asarray(snow_fraction,float),0,1)
def aerosol_cloud_seed(aerosol_index,rh): return np.clip(0.05*np.maximum(np.asarray(aerosol_index,float),0)*np.clip(np.asarray(rh,float),0,2),0,1)
def soot_darkening(snow_age_days,soot_loading): return np.clip(0.05*np.sqrt(np.maximum(np.asarray(snow_age_days,float),0))+0.02*np.maximum(np.asarray(soot_loading,float),0),0,0.35)
